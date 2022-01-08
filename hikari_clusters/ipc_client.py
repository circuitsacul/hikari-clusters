# MIT License
#
# Copyright (c) 2021 TrigonDev
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

import asyncio
import json
import pathlib
import ssl
from typing import Any, Iterable

from websockets import client
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK

from . import close_codes, exceptions, log, payload
from .callbacks import CallbackHandler, NoResponse
from .commands import CommandHandler
from .events import EventGroup, EventHandler
from .info_classes import ClusterInfo, ServerInfo
from .task_manager import TaskManager

__all__ = ("IpcClient",)


class IpcClient:
    """A connection to a :class:`~ipc_server.IpcServer`.

    Parameters
    ----------
    uri : str
        The uri of the ipc server.
    token : str
        The token required by the ipc server.
    logger : :class:`~log.Logger`
        The logger used by the clients parent.
    reconnect : bool
        Whether or not to try to reconnect after disconnection, by default
        True.
    cmd_kwargs : dict[str, Any], optional
        Command arguments to pass to :class:`~commands.CommandHandler`, by
        default None.
    event_kwargs : dict[str, Any], optional
        Event arguments to pass to :class:`~events.EventHandler`, by
        default None.
    certificate_path : pathlib.Path, optional
        Required for secure (wss) connections, by default None.
    """

    def __init__(
        self,
        uri: str,
        token: str,
        logger: log.Logger,
        reconnect: bool = True,
        cmd_kwargs: dict[str, Any] | None = None,
        event_kwargs: dict[str, Any] | None = None,
        certificate_path: pathlib.Path | None = None,
    ) -> None:
        self.logger = logger
        self.tasks = TaskManager(logger)

        cmd_kwargs = cmd_kwargs or {}
        event_kwargs = event_kwargs or {}
        cmd_kwargs["_ipc_client"] = self
        event_kwargs["_ipc_client"] = self

        self.callbacks = CallbackHandler()
        self.commands = CommandHandler(self, cmd_kwargs)
        self.events = EventHandler(logger, event_kwargs)

        self.events.include(_E)

        self.uri = uri
        self.token = token
        self.reconnect = reconnect

        self.ssl_context: ssl.SSLContext | None
        if certificate_path is not None:
            self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self.ssl_context.load_verify_locations(certificate_path)
        else:
            self.ssl_context = None

        self.client_uids: set[int] = set()
        """A set of all IPC uids representing every connected client."""
        self.brain_uid: int | None = None
        """The IPC uid of the brain's client."""
        self.servers: dict[int, ServerInfo] = {}
        """Maps the IPC uids for each server to its ServerInfo class."""
        self.clusters: dict[int, ClusterInfo] = {}
        """Maps the IPC uids for each cluster to its ClusterInfo class."""
        self.clusters_by_cluster_id: dict[int, ClusterInfo] = {}
        """Maps the cluster id for each cluster to its ClusterInfo class."""

        self._ws: client.WebSocketClientProtocol | None = None
        self.uid: int | None = None

        self.stop_future: asyncio.Future | None = None
        self.ready_future: asyncio.Future | None = None

    @property
    def server_uids(self) -> set[int]:
        """A set of all IPC uids representing every connected server."""

        return set(self.servers.keys())

    @property
    def cluster_uids(self) -> set[int]:
        """A set of all IPC uids representing every connected cluster."""

        return set(self.clusters.keys())

    def all_shards(self) -> set[int]:
        """Get all shard ids.

        Excludes shard_ids from clusters that aren't ready yet.
        """

        all_shards: set[int] = set()
        for c in self.clusters.values():
            if not c.ready:
                continue
            if c.server_uid not in self.servers:
                continue
            if c.uid not in self.servers[c.server_uid].cluster_uids:
                continue
            all_shards.update(c.shard_ids)
        return all_shards

    @staticmethod
    def get_uri(host: str, port: int, use_wss: bool = False) -> str:
        """Utility for converting a host and port to a uri.

        Parameters
        ----------
        host : str
            The host (e.g. "localhost")
        port : int
            The port (e.g. 1234)
        use_wss : bool
            Whether or not to use wss (secure websocket).
            If set to True, both the Client and the Server
            must be using a certificate. By default False.

        Returns
        -------
        str
            The uri (e.g. "ws://localhost:1234")
        """

        return ("wss" if use_wss else "ws") + f"://{host}:{port}"

    async def start(self) -> None:
        """Start the ipc client.

        Creates the tasks that will connect to the server
        and deal with received messages. Just because this
        method returns does not mean the client is ready.
        Use :meth:`~IpcClient.wait_until_ready` for this.
        """

        self.stop_future = asyncio.Future()
        self.ready_future = asyncio.Future()

        def _stop(*args, **kwargs) -> None:
            self.stop()

        self.tasks.create_task(self._start()).add_done_callback(_stop)

    def stop(self) -> None:
        """Tell the client to stop."""

        if self.stop_future is not None and not self.stop_future.done():
            self.stop_future.set_result(None)
        if self.ready_future is not None and not self.ready_future.done():
            self.ready_future.cancel()

    async def close(self) -> None:
        """Disconnect and close the client."""

        self.tasks.cancel_all()
        await self.tasks.wait_for_all()

    async def wait_until_ready(self) -> None:
        """Wait until the client is either ready or shutting down."""

        assert self.ready_future is not None
        await self.ready_future

    async def join(self) -> None:
        """Wait until the client is shutting down."""

        assert self.stop_future is not None
        await self.stop_future

    async def send_not_found_response(
        self, to: Iterable[int], callback: int
    ) -> None:
        """Respond to a command saying that the command was not found.

        Parameters
        ----------
        to : Iterable[int]
            The clients to send the response to.
        callback : int
            The command callback (:attr:`~payload.Command.callback`)
        """

        await self._send(to, payload.ResponseNotFound(callback))

    async def send_ok_response(
        self, to: Iterable[int], callback: int, data: payload.DATA = None
    ) -> None:
        """Respond that the command *function* finished without any problems.

        Does not necessarily mean that the command itself finished correctly.

        Parameters
        ----------
        to : Iterable[int]
            The clients to send the response to.
        callback : int
            The command callback (:attr:`~payload.Command.callback`)
        data : payload.DATA, optional
            The data to send with the response, by default None
        """

        await self._send(to, payload.ResponseOk(callback, data))

    async def send_tb_response(
        self, to: Iterable[int], callback: int, tb: str
    ) -> None:
        """Respond that the command function raised an exception.

        Parameters
        ----------
        to : Iterable[int]
            The clients to send the response to.
        callback : int
            The command callback (:attr:`~payload.Command.callback`)
        tb : str
            The exception traceback.
        """

        await self._send(to, payload.ResponseTraceback(callback, tb))

    async def send_event(
        self, to: Iterable[int], name: str, data: payload.DATA = None
    ) -> None:
        """Dispatch an event.

        Events are like commands, except that no responses are sent.

        Parameters
        ----------
        to : Iterable[int]
            The clients to send the event to.
        name : str
            The name of the event
        data : payload.DATA, optional
            The data to send with the event, by default None
        """

        await self._send(to, payload.Event(name, data))

    async def send_command(
        self, to: Iterable[int], name: str, data: payload.DATA = None
    ) -> dict[int, payload.RESPONSE | NoResponse]:
        """Tell other clients to do something, then wait for their response.

        Parameters
        ----------
        to : Iterable[int]
            The clients to send the command to.
        name : str
            The name of the command.
        data : payload.DATA, optional
            The data to send with the command, by default None

        Returns
        -------
        dict[int, payload.RESPONSE | :class:`~callbacks.NoResponse`]
            A dictionary that maps the clients uid to their response,
            if any.
        """

        with self.callbacks.callback(to) as cb:
            await self._send(to, payload.Command(name, cb.key, data))
            await cb.wait()
        return cb.resps

    async def _start(self) -> None:
        self.logger.debug("Attempting connection to IPC...")
        assert self.ready_future
        async for ws in client.connect(self.uri, ssl=self.ssl_context):
            reconnect = self.reconnect
            await self._handshake(ws)
            self._ws = ws
            self.ready_future.set_result(None)
            self.logger.info(f"Connected successfully as {self.uid}.")
            try:
                await self._recv_loop(ws)
            except ConnectionClosedOK:
                pass
            except ConnectionClosed as e:
                if e.code == close_codes.INVALID_TOKEN:
                    raise exceptions.InvalidIpcToken
            except asyncio.CancelledError:
                reconnect = False
            finally:
                self._ws = None
                self.ready_future = asyncio.Future()
                self.logger.info("Disconnected.")

                self.client_uids.clear()
                self.clusters_by_cluster_id.clear()
                self.clusters.clear()
                self.servers.clear()

                if reconnect:
                    self.logger.info("Attempting reconnection...")
                else:
                    return

    async def _handshake(self, ws: client.WebSocketClientProtocol) -> None:
        self.logger.debug("Attempting handshake...")
        await ws.send(json.dumps({"token": self.token}))
        data: dict[str, Any] = json.loads(await ws.recv())
        self.uid = data["uid"]
        self.client_uids = set(data["client_uids"])
        self.logger.debug(f"Handshake successful, uid {self.uid}")

    def _update_clients(self, client_uids: set[int]) -> None:
        self.client_uids = client_uids
        for sid in list(self.servers.keys()):
            if sid not in self.client_uids:
                del self.servers[sid]

        to_remove: list[int] = []  # a list of cluster ids to remove

        for cid, c in list(self.clusters.items()):
            if cid not in self.client_uids:
                to_remove.append(c.cluster_id)
                del self.clusters[cid]

        for cid in to_remove:
            if cid in self.clusters_by_cluster_id:
                del self.clusters_by_cluster_id[cid]
            else:
                self.logger.warn("Something's up with clusters_by_cluster_id.")

    async def _recv_loop(self, ws: client.WebSocketClientProtocol) -> None:
        async for msg in ws:
            self.logger.debug(f"Received message: {msg!s}")
            data: dict[str, Any] = json.loads(msg)
            if data.get("internal", False):
                self._update_clients(set(data["client_uids"]))
            else:
                self.tasks.create_task(self._handle_message(data))

    async def _handle_message(self, data: dict[str, Any]) -> None:
        pl: payload.Payload[Any] = payload.deserialize_payload(data)
        if isinstance(pl.data, payload.Command):
            await self.commands.handle_command(pl)
        elif isinstance(pl.data, payload.Event):
            await self.events.handle_event(pl)
        else:
            self.callbacks.handle_response(pl)

    async def _send(
        self, to: Iterable[int], pl_data: payload.PAYLOAD_DATA
    ) -> None:
        assert self.uid is not None
        pl = payload.Payload(
            pl_data.opcode,
            self.uid,
            list(to),
            pl_data,
        )
        await self._raw_send(json.dumps(pl.serialize()))

    async def _raw_send(self, msg: str) -> None:
        assert self._ws is not None
        await self._ws.send(msg)


_E = EventGroup()


@_E.add("set_brain_uid")
async def set_brain_uid(pl: payload.EVENT, _ipc_client: IpcClient) -> None:
    assert pl.data.data is not None
    uid = pl.data.data["uid"]
    _ipc_client.logger.debug(f"Setting brain uid to {uid}.")
    _ipc_client.brain_uid = pl.data.data["uid"]


@_E.add("set_cluster_info")
async def update_cluster_info(
    pl: payload.EVENT, _ipc_client: IpcClient
) -> None:
    assert pl.data.data is not None
    cinfo = ClusterInfo(**pl.data.data)
    _ipc_client.logger.debug(
        f"Updating info for Cluster {cinfo.cluster_id} ({cinfo.uid})"
    )
    _ipc_client.clusters_by_cluster_id[cinfo.cluster_id] = cinfo
    _ipc_client.clusters[cinfo.uid] = cinfo


@_E.add("set_server_info")
async def update_server_info(
    pl: payload.EVENT, _ipc_client: IpcClient
) -> None:
    assert pl.data.data is not None
    sinfo = ServerInfo(**pl.data.data)
    _ipc_client.logger.debug(f"Updating info for Server {sinfo.uid}")
    _ipc_client.servers[sinfo.uid] = sinfo

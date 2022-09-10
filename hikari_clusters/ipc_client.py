from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import ssl
from typing import Any, Collection, Iterable, TypeVar, Union, cast

from websockets.exceptions import ConnectionClosed, ConnectionClosedOK
from websockets.legacy import client

from . import close_codes, exceptions, payload
from .callbacks import CallbackHandler, NoResponse
from .commands import CommandHandler
from .events import EventGroup, EventHandler
from .info_classes import BaseInfo, BrainInfo, ClusterInfo, ServerInfo
from .ipc_base import IpcBase
from .task_manager import TaskManager

_BI_T = TypeVar("_BI_T", bound=BaseInfo)
_LOG = logging.getLogger(__name__)
_LOG.setLevel(logging.INFO)

__all__ = ("IpcClient",)

_TO = Union[Iterable[Union[BaseInfo, int]], BaseInfo, int]


def _parse_to(to: _TO) -> set[int]:
    return set(map(int, to)) if isinstance(to, Iterable) else {int(to)}


class IpcClient(IpcBase):
    """A connection to a :class:`~ipc_server.IpcServer`.

    Parameters
    ----------
    uri : str
        The uri of the ipc server.
    token : str
        The token required by the ipc server.
    reconnect : bool
        Whether or not to try to reconnect after disconnection, by default
        True.
    certificate_path : pathlib.Path, optional
        Required for secure (wss) connections, by default None.
    """

    def __init__(
        self,
        uri: str,
        token: str,
        reconnect: bool = True,
        certificate_path: pathlib.Path | None = None,
    ) -> None:
        self.tasks = TaskManager()

        self.callbacks = CallbackHandler(self)
        self.commands = CommandHandler(self, {"_ipc_client": self})
        self.events = EventHandler({"_ipc_client": self})

        self.events.include(_E)

        self.uri = uri
        self.token = token
        self.reconnect = reconnect

        self.certificate_path = certificate_path
        self.ssl_context: ssl.SSLContext | None
        if certificate_path is not None:
            self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            self.ssl_context.load_verify_locations(certificate_path)
        else:
            self.ssl_context = None

        self.client_uids: set[int] = set()
        """A set of all IPC uids representing every connected client."""
        self.clients: dict[int, dict[int, BaseInfo]] = {}

        self._ws: client.WebSocketClientProtocol | None = None
        self.uid: int | None = None

        self.stop_future: asyncio.Future[None] | None = None
        self.ready_future: asyncio.Future[None] | None = None

    @property
    def servers(self) -> dict[int, ServerInfo]:
        """Shorthand for IpcClient.get_clients(ServerInfo)"""

        return self.get_clients(ServerInfo)

    @property
    def clusters(self) -> dict[int, ClusterInfo]:
        """Shorthand for IpcClient.get_clients(ClusterInfo)"""

        return self.get_clients(ClusterInfo)

    @property
    def brain(self) -> BrainInfo | None:
        """The IPC UID of the brain."""

        brains = self.get_clients(BrainInfo)
        if not brains:
            return None
        elif len(brains) > 1:
            _LOG.warning("More than one brain connected.")
        return brains[max(brains.keys())]

    def get_clients(self, client: type[_BI_T]) -> dict[int, _BI_T]:
        return cast(
            "dict[int, _BI_T]", self.clients.get(client._info_class_id, {})
        )

    def all_shards(self) -> set[int]:
        """Get all shard ids.

        Excludes shard_ids from clusters that aren't ready yet.
        """

        all_shards: set[int] = set()
        for c in self.clusters.values():
            servers = self.servers
            if not (
                c.ready
                and c.server_uid in servers
                and c.uid in servers[c.server_uid].cluster_uids
            ):
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

        def _stop(*args: Any, **kwargs: Any) -> None:
            self.stop()

        self.tasks.create_task(self._start()).add_done_callback(_stop)

    async def send_not_found_response(self, to: _TO, callback: int) -> None:
        """Respond to a command saying that the command was not found.

        Parameters
        ----------
        to : Iterable[int | BaseInfo]
            The clients to send the response to.
        callback : int
            The command callback (:attr:`~payload.Command.callback`)
        """

        await self._send(_parse_to(to), payload.ResponseNotFound(callback))

    async def send_ok_response(
        self, to: _TO, callback: int, data: payload.DATA = None
    ) -> None:
        """Respond that the command *function* finished without any problems.

        Does not necessarily mean that the command itself finished correctly.

        Parameters
        ----------
        to : Iterable[int | BaseInfo]
            The clients to send the response to.
        callback : int
            The command callback (:attr:`~payload.Command.callback`)
        data : payload.DATA, optional
            The data to send with the response, by default None
        """

        await self._send(_parse_to(to), payload.ResponseOk(callback, data))

    async def send_tb_response(self, to: _TO, callback: int, tb: str) -> None:
        """Respond that the command function raised an exception.

        Parameters
        ----------
        to : Iterable[int | BaseInfo]
            The clients to send the response to.
        callback : int
            The command callback (:attr:`~payload.Command.callback`)
        tb : str
            The exception traceback.
        """

        await self._send(
            _parse_to(to), payload.ResponseTraceback(callback, tb)
        )

    async def send_event(
        self, to: _TO, name: str, data: payload.DATA = None
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

        await self._send(_parse_to(to), payload.Event(name, data))

    async def send_command(
        self,
        to: _TO,
        name: str,
        data: payload.DATA = None,
        timeout: float = 3.0,
    ) -> dict[int, payload.RESPONSE | NoResponse]:
        """Tell other clients to do something, then wait for their response.

        Parameters
        ----------
        to : Iterable[int | BaseInfo]
            The clients to send the command to.
        name : str
            The name of the command.
        data : payload.DATA, optional
            The data to send with the command, by default None
        timeout : int, optional
            How long to wait for responses, by default 3 seconds.

        Returns
        -------
        dict[int, payload.RESPONSE | :class:`~callbacks.NoResponse`]
            A dictionary that maps the clients uid to their response,
            if any.
        """

        to = _parse_to(to)
        with self.callbacks.callback(to) as cb:
            await self._send(to, payload.Command(name, cb.key, data))
            await cb.wait(timeout)
        return cb.resps

    async def _start(self) -> None:
        _LOG.debug("Attempting connection to IPC...")
        assert self.ready_future
        async for ws in client.connect(self.uri, ssl=self.ssl_context):
            reconnect = self.reconnect
            await self._handshake(ws)
            self._ws = ws
            self.ready_future.set_result(None)
            _LOG.info(f"Connected successfully as {self.uid}.")
            try:
                await self._recv_loop(ws)
            except ConnectionClosedOK:
                pass
            except ConnectionClosed as e:
                if e.code == close_codes.INVALID_TOKEN:
                    raise exceptions.InvalidIpcToken from e
            except asyncio.CancelledError:
                reconnect = False
            finally:
                self._ws = None
                self.ready_future = asyncio.Future()
                _LOG.info("Disconnected.")

                self.client_uids.clear()
                self.clients.clear()

                if reconnect:
                    _LOG.info("Attempting reconnection...")
                else:
                    return

    async def _handshake(self, ws: client.WebSocketClientProtocol) -> None:
        _LOG.debug("Attempting handshake...")
        await ws.send(json.dumps({"token": self.token}))
        data: dict[str, Any] = json.loads(await ws.recv())
        self.uid = data["uid"]
        self.client_uids = set(data["client_uids"])
        _LOG.debug(f"Handshake successful, uid {self.uid}")

    def _update_clients(self, client_uids: set[int]) -> None:
        if self.client_uids.difference(client_uids):
            self.callbacks.handle_disconnects()

        self.client_uids = client_uids
        for sid in list(self.servers.keys()):
            if sid not in self.client_uids:
                del self.servers[sid]

        for cid, c in list(self.clusters.items()):
            if cid in self.client_uids:
                continue
            del self.clusters[cid]

    async def _recv_loop(self, ws: client.WebSocketClientProtocol) -> None:
        async for msg in ws:
            _LOG.debug(f"Received message: {msg!s}")
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
        self, to: Collection[int], pl_data: payload.PAYLOAD_DATA
    ) -> None:
        assert self.uid is not None
        pl = payload.Payload(
            pl_data.opcode, self.uid, list(map(int, to)), pl_data
        )
        await self._raw_send(json.dumps(pl.serialize()))

    async def _raw_send(self, msg: str) -> None:
        assert self._ws is not None
        await self._ws.send(msg)


_E = EventGroup()


@_E.add("set_info_class")
async def set_info_class(pl: payload.EVENT, _ipc_client: IpcClient) -> None:
    assert pl.data.data is not None
    info = BaseInfo.fromdict(pl.data.data)
    _LOG.debug("Setting info class {info}.")
    _ipc_client.clients.setdefault(info._info_class_id, {})[info.uid] = info

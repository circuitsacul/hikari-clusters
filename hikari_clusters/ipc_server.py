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
import traceback
from typing import Any, Iterable

from websockets import server
from websockets.exceptions import ConnectionClosedOK

from . import close_codes, log, payload
from .task_manager import TaskManager

__all__ = ("IpcServer",)

LOG = log.Logger("Ipc Server")


class IpcServer:
    """An ipc server.

    Allows for communication between :class:`~ipc_client.IpcClient`s
    and ensures that all the connected clients have the proper
    token.

    Parameters
    ----------
    host : str
        The host to launch the server on.
    port : int
        The port to launch the server on.
    token : str
        The token to require from connecting clients.
    certificate_path : pathlib.Path, optional
        The path to a self-signed certificate. Optional,
        but necessary if you want a secure connection.
        Highly recommended. By default None.
    """

    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        certificate_path: pathlib.Path | None = None,
    ) -> None:
        self.tasks = TaskManager(LOG)

        self.host = host
        self.port = port
        self.token = token

        self.ssl_context: ssl.SSLContext | None
        if certificate_path is not None:
            self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self.ssl_context.load_cert_chain(certificate_path)
        else:
            self.ssl_context = None

        self.stop_future: asyncio.Future | None = None
        self.ready_future: asyncio.Future | None = None

        self.clients: dict[int, server.WebSocketServerProtocol] = {}
        self._current_uid: int = 0

        self.main_task: asyncio.Task | None = None

    @property
    def _next_uid(self) -> int:
        self._current_uid += 1
        return self._current_uid

    async def start(self) -> None:
        """Start the server.

        Returns as soon as the tasks have been started. Returning
        does not mean that the server has started."""

        self.stop_future = asyncio.Future()
        self.ready_future = asyncio.Future()

        self.tasks.create_task(self._send_client_uids_loop())
        self.tasks.create_task(self._start(), allow_cancel=False)

    def stop(self) -> None:
        """Tells the server to stop."""

        if self.stop_future is not None and not self.stop_future.done():
            self.stop_future.set_result(None)
        if self.ready_future is not None and not self.ready_future.done():
            self.ready_future.cancel()

    async def close(self) -> None:
        """Shuts the server down."""

        self.tasks.cancel_all()
        await self.tasks.wait_for_all()

    async def wait_until_ready(self) -> None:
        """Wait until the server is ready or shutting down."""

        assert self.ready_future is not None
        await self.ready_future

    async def join(self) -> None:
        """Wait until the server is shutting down."""

        assert self.stop_future is not None
        await self.stop_future

    async def _serve(
        self, ws: server.WebSocketServerProtocol, path: str
    ) -> None:
        LOG.debug("Client connected.")
        try:
            uid = await self._handshake(ws)
            if uid is None:
                return
            self.clients[uid] = ws

            LOG.info(f"Client connected as {uid}")

            try:
                while True:
                    try:
                        msg = await ws.recv()
                        LOG.debug(f"Received message: {msg!s}")
                        pl = payload.deserialize_payload(json.loads(msg))
                        await self._dispatch(pl.recipients, msg)
                    except ConnectionClosedOK:
                        break
            finally:
                del self.clients[uid]

        except Exception:
            LOG.error(f"Exception in handler for client {uid}:")
            LOG.error(traceback.format_exc())

        finally:
            LOG.info(f"Client {uid} disconnected.")

    async def _start(self) -> None:
        LOG.debug("Server starting up...")
        assert self.ready_future
        assert self.stop_future
        async with server.serve(
            self._serve, self.host, self.port, ssl=self.ssl_context
        ):
            LOG.debug("Server started.")
            self.ready_future.set_result(None)
            await self.stop_future
            LOG.debug("Stopping...")
        LOG.debug("Server exitted.")

    async def _handshake(
        self, ws: server.WebSocketServerProtocol
    ) -> int | None:
        LOG.debug("Attempting handshake.")
        req: dict[str, Any] = json.loads(await ws.recv())
        if req.get("token") != self.token:
            LOG.debug("Received invalid token.")
            await ws.close(close_codes.INVALID_TOKEN, "Invalid Token")
            return None

        uid = self._next_uid
        await ws.send(
            json.dumps(
                {
                    "uid": uid,
                    "client_uids": list(self.clients.keys()),
                }
            )
        )
        LOG.debug(f"Handshake successful, uid {uid}")
        return uid

    async def _send_client_uids_loop(self) -> None:
        await self.wait_until_ready()
        while True:
            data = json.dumps(
                {"internal": True, "client_uids": list(self.clients.keys())}
            )
            await self._dispatch(list(self.clients.keys()), data)
            await asyncio.sleep(5)

    async def _dispatch(self, to: Iterable[int], msg: str | bytes) -> None:
        for cid in to:
            client = self.clients.get(cid)
            if not client or not client.open:
                continue
            try:
                await client.send(msg)
            except Exception:
                LOG.error(traceback.format_exc())

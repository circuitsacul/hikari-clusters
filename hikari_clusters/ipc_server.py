from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import ssl
import traceback
from typing import Any, Iterable

from websockets.exceptions import ConnectionClosedOK
from websockets.legacy import server

from . import close_codes, payload
from .ipc_base import IpcBase
from .task_manager import TaskManager

__all__ = ("IpcServer",)

_LOG = logging.getLogger(__name__)
_LOG.setLevel(logging.INFO)


class IpcServer(IpcBase):
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
        self.tasks = TaskManager()

        self.host = host
        self.port = port
        self.token = token

        self.ssl_context: ssl.SSLContext | None
        if certificate_path is not None:
            self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self.ssl_context.load_cert_chain(certificate_path)
        else:
            self.ssl_context = None

        self.stop_future: asyncio.Future[None] | None = None
        self.ready_future: asyncio.Future[None] | None = None

        self.clients: dict[int, server.WebSocketServerProtocol] = {}
        self._current_uid: int = 0

        self.main_task: asyncio.Task[None] | None = None

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

    async def _serve(
        self, ws: server.WebSocketServerProtocol, path: str
    ) -> None:
        uid: int | None = None
        _LOG.debug("Client connected.")
        try:
            uid = await self._handshake(ws)
            if uid is None:
                return
            self.clients[uid] = ws

            _LOG.info(f"Client connected as {uid}")

            try:
                while True:
                    msg = await ws.recv()
                    _LOG.debug(f"Received message: {msg!s}")
                    pl = payload.deserialize_payload(json.loads(msg))
                    await self._dispatch(pl.recipients, msg)
            except ConnectionClosedOK:
                pass
            finally:
                del self.clients[uid]

        except Exception:
            _LOG.error(f"Exception in handler for client {uid}:")
            _LOG.error(traceback.format_exc())

        _LOG.info(f"Client {uid} disconnected.")

    async def _start(self) -> None:
        _LOG.debug("Server starting up...")
        assert self.ready_future
        assert self.stop_future
        async with server.serve(
            self._serve, self.host, self.port, ssl=self.ssl_context
        ):
            _LOG.debug("Server started.")
            self.ready_future.set_result(None)
            await self.stop_future
            _LOG.debug("Stopping...")
        _LOG.debug("Server exited.")

    async def _handshake(
        self, ws: server.WebSocketServerProtocol
    ) -> int | None:
        _LOG.debug("Attempting handshake.")
        req: dict[str, Any] = json.loads(await ws.recv())
        if req.get("token") != self.token:
            _LOG.debug("Received invalid token.")
            await ws.close(close_codes.INVALID_TOKEN, "Invalid Token")
            return None

        uid = self._next_uid
        await ws.send(
            json.dumps({"uid": uid, "client_uids": list(self.clients.keys())})
        )
        _LOG.debug(f"Handshake successful, uid {uid}")
        return uid

    async def _send_client_uids_loop(self) -> None:
        await self.wait_until_ready()
        while True:
            client_ids = list(self.clients.keys())
            data = json.dumps({"internal": True, "client_uids": client_ids})
            await self._dispatch(client_ids, data)
            await asyncio.sleep(5)

    async def _dispatch(self, to: Iterable[int], msg: str | bytes) -> None:
        for cid in to:
            client = self.clients.get(cid)
            if not (client and client.open):
                continue
            try:
                await client.send(msg)
            except Exception:
                _LOG.error(traceback.format_exc())

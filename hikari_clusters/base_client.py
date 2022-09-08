from __future__ import annotations

import asyncio
import logging
import pathlib

from websockets.exceptions import ConnectionClosed

from .info_classes import BaseInfo
from .ipc_client import IpcClient
from .task_manager import TaskManager

_LOG = logging.getLogger(__name__)


class BaseClient:
    """The base client, which contains an IpcClient.

    Parameters
    ----------
    ipc_uri : str
        The URI of the brain.
    token : str
        The token for the IPC server.
    reconnect : bool
        Whether to automatically reconnect if the connection
        is lost. Defaults to True.
    certificate_path : pathlib.Path | str | None
        The path to your certificate, which allos for secure
        connection over the IPC. Defaults to None.
    """

    def __init__(
        self,
        ipc_uri: str,
        token: str,
        reconnect: bool = True,
        certificate_path: pathlib.Path | str | None = None,
    ):
        if isinstance(certificate_path, str):
            certificate_path = pathlib.Path(certificate_path)

        self.tasks = TaskManager()
        self.ipc = IpcClient(
            uri=ipc_uri,
            token=token,
            reconnect=reconnect,
            certificate_path=certificate_path,
        )

        self.stop_future: asyncio.Future[None] | None = None

    def get_info(self) -> BaseInfo:
        """Get the info class for this client.

        Returns:
            BaseInfo: The info class.
        """

        raise NotImplementedError

    async def start(self) -> None:
        """Start the client.

        Connects to the IPC server and begins sending out this clients
        info.
        """

        if self.stop_future is None:
            self.stop_future = asyncio.Future()

        await self.ipc.start()

        self.tasks.create_task(self._broadcast_info_loop())

    async def join(self) -> None:
        """Wait until the client begins exiting."""

        assert self.stop_future and self.ipc.stop_future

        await asyncio.wait(
            [self.stop_future, self.ipc.stop_future],
            return_when=asyncio.FIRST_COMPLETED,
        )

    async def close(self) -> None:
        """Shut down the client."""

        self.ipc.stop()
        await self.ipc.close()

        self.tasks.cancel_all()
        await self.tasks.wait_for_all()

    def stop(self) -> None:
        """Tell the client to stop."""

        assert self.stop_future
        self.stop_future.set_result(None)

    async def _broadcast_info_loop(self) -> None:
        while True:
            await self.ipc.wait_until_ready()
            assert self.ipc.uid
            try:
                await self.ipc.send_event(
                    self.ipc.client_uids,
                    "set_info_class",
                    self.get_info().asdict(),
                )
            except ConnectionClosed:
                _LOG.error("Failed to send client info.", exc_info=True)
            await asyncio.sleep(1)

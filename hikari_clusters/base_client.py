from __future__ import annotations

import asyncio
import pathlib

from websockets.exceptions import ConnectionClosed

from . import log
from .info_classes import BaseInfo
from .ipc_client import IpcClient
from .task_manager import TaskManager

_LOG = log.Logger(__file__)


class BaseClient:
    def __init__(
        self,
        ipc_uri: str,
        token: str,
        reconnect: bool = True,
        certificate_path: pathlib.Path | str | None = None,
    ):
        if isinstance(certificate_path, str):
            certificate_path = pathlib.Path(certificate_path)

        self.tasks = TaskManager(_LOG)
        self.ipc = IpcClient(
            uri=ipc_uri,
            token=token,
            logger=_LOG,
            reconnect=reconnect,
            certificate_path=certificate_path,
        )

        self.stop_future: asyncio.Future[None] | None = None

    def get_info(self) -> BaseInfo:
        raise NotImplementedError

    async def start(self) -> None:
        await self.ipc.start()

        self.stop_future = asyncio.Future()
        self.tasks.create_task(self._broadcast_info_loop())

    async def join(self) -> None:
        assert self.stop_future and self.ipc.stop_future

        await asyncio.wait(
            [self.stop_future, self.ipc.stop_future],
            return_when=asyncio.FIRST_COMPLETED,
        )

    async def close(self) -> None:
        self.ipc.stop()
        await self.ipc.close()

        self.tasks.cancel_all()
        await self.tasks.wait_for_all()

    def stop(self) -> None:
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
                return
            await asyncio.sleep(1)

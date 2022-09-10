from __future__ import annotations

import asyncio

from .task_manager import TaskManager


class IpcBase:
    """Base class for IpcClient and IpcServer"""

    stop_future: asyncio.Future[None] | None
    ready_future: asyncio.Future[None] | None
    tasks: TaskManager

    def stop(self) -> None:
        """Tell the client/server to stop."""

        if self.stop_future and not self.stop_future.done():
            self.stop_future.set_result(None)
        if self.ready_future and not self.ready_future.done():
            self.ready_future.cancel()

    async def close(self) -> None:
        """Disconnect and close the client/server."""

        self.tasks.cancel_all()
        await self.tasks.wait_for_all()

    async def wait_until_ready(self) -> None:
        """Wait until the client/server is either ready or shutting down.

        Raises:
            asyncio.CancelledError: The client/server shut down before it was
            ready.
        """

        assert self.ready_future is not None
        await self.ready_future

    async def join(self) -> None:
        """Wait until the client/server is shutting down."""

        assert self.stop_future is not None
        await self.stop_future

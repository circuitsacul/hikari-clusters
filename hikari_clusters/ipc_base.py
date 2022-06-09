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

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
import traceback
from typing import Awaitable, Iterable, Type, TypeVar

from . import log

__all__ = ("TaskManager",)

_T = TypeVar("_T")


class _TaskWrapper:
    def __init__(
        self,
        allow_cancel: bool,
        allow_wait: bool,
        t: asyncio.Task,
    ) -> None:
        self.allow_cancel = allow_cancel
        self.allow_wait = allow_wait
        self.t = t


class TaskManager:
    """Makes asyncio.Task managements slightly easier."""

    def __init__(self, logger: log.Logger) -> None:
        self.logger = logger
        self._tasks: dict[int, _TaskWrapper] = {}
        self._curr_tid = 0

    @property
    def next_tid(self) -> int:
        """Generate the next task id."""

        self._curr_tid += 1
        return self._curr_tid

    def create_task(
        self,
        coro: Awaitable[_T],
        *,
        name: str | None = None,
        ignored_exceptions: Iterable[Type[Exception]] = tuple(),
        allow_cancel: bool = True,
        allow_wait: bool = True,
    ) -> asyncio.Task[_T]:
        """Create a task and add it to the list of tasks.

        Parameters
        ----------
        coro : Awaitable[_T]
            The coroutine to start.
        name : str, optional
            The name parameters specified by asyncio.create_task, by default
            None
        ignored_exceptions : Iterable[Type[Exception]], optional
            Exceptions to ignore upon task completion, by default tuple()
        allow_cancel : bool, optional
            Whether or not :meth:`~TaskManager.cancel_all` will cancel this
            task, by default True
        allow_wait : bool, optional
            Whether or not :meth:`~TaskManager.wait_for_all` will wait for
            this task, by default True

        Returns
        -------
        asyncio.Task[_T]
            The task that was created.
        """

        tid = self.next_tid

        def callback(task: asyncio.Task):
            try:
                task.result()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                if not isinstance(e, tuple(ignored_exceptions)):
                    self.logger.error("Exception in task callback:")
                    self.logger.error(traceback.format_exc())
            finally:
                if tid in self._tasks:
                    del self._tasks[tid]

        t = asyncio.create_task(coro, name=name)
        self._tasks[tid] = _TaskWrapper(allow_cancel, allow_wait, t)
        t.add_done_callback(callback)
        return t

    def cancel_all(self) -> None:
        """Cancel all tasks that allow cancelling."""

        for t in self._tasks.values():
            if t.allow_cancel:
                t.t.cancel()
        self._remove_finished()

    async def wait_for_all(self, timeout: float = 3.0) -> None:
        """Wait for all tasks that allow waiting.

        Parameters
        ----------
        timeout : float
            How long to wait for a task before giving up.
        """

        to_wait: list[asyncio.Task] = []
        for t in self._tasks.values():
            if t.allow_wait:
                to_wait.append(t.t)

        if len(to_wait) == 0:
            return

        await asyncio.wait(to_wait, timeout=timeout)
        self._remove_finished()

    def _remove_finished(self) -> None:
        for tid, t in list(self._tasks.items()):
            if t.t.done():
                del self._tasks[tid]

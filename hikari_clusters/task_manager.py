from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, Coroutine, Generator, Iterable, Type, TypeVar

__all__ = ("TaskManager",)

_T = TypeVar("_T")
_LOG = logging.getLogger(__name__)
_LOG.setLevel(logging.INFO)


class _TaskWrapper:
    __slots__ = ("allow_cancel", "allow_wait", "t")

    def __init__(
        self, allow_cancel: bool, allow_wait: bool, t: asyncio.Task[Any]
    ) -> None:
        self.allow_cancel = allow_cancel
        self.allow_wait = allow_wait
        self.t = t


class TaskManager:
    """Makes asyncio.Task managements slightly easier."""

    def __init__(self) -> None:
        self._tasks: dict[int, _TaskWrapper] = {}
        self._curr_tid = 0

    @property
    def next_tid(self) -> int:
        """Generate the next task id."""

        self._curr_tid += 1
        return self._curr_tid

    def create_task(
        self,
        coro: Generator[Any, None, _T] | Coroutine[Any, None, _T],
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

        def callback(task: asyncio.Task[Any]) -> None:
            try:
                task.result()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                if not isinstance(e, tuple(ignored_exceptions)):
                    _LOG.error("Exception in task callback:")
                    _LOG.error(traceback.format_exc())
            finally:
                self._tasks.pop(tid, None)

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

        to_wait = [t.t for t in self._tasks.values() if t.allow_wait]

        if not to_wait:
            return

        await asyncio.wait(to_wait, timeout=timeout)
        self._remove_finished()

    def _remove_finished(self) -> None:
        for tid, t in list(self._tasks.items()):
            if t.t.done():
                del self._tasks[tid]

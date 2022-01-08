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

import traceback
from typing import Any, Awaitable, Callable

from . import log, payload

__all__ = (
    "EventHandler",
    "EventGroup",
    "IPC_EVENT",
)

IPC_EVENT = Callable[..., Awaitable[None]]


class EventHandler:
    """Event handler.

    Parameters
    ----------
    logger : :class:`~log.Logger`
        The logger to use.
    event_kwargs : dict[str, Any], optional
        Extra kwargs to pass to event functions, default to None.
    """

    def __init__(
        self, logger: log.Logger, event_kwargs: dict[str, Any] | None = None
    ) -> None:
        self.events: dict[str, list[IPC_EVENT]] = {}
        self.event_kwargs = event_kwargs or {}
        self.logger = logger

    async def handle_event(
        self,
        pl: payload.EVENT,
    ) -> None:
        """Handle an event.

        Parameters
        ----------
        pl : payload.EVENT
            The event to handle.
        """

        events = self.events.get(pl.data.name)
        if events is None:
            return

        for func in events:
            kwargs = {}
            func_co_names = func.__code__.co_varnames
            for name, val in self.event_kwargs.items():
                if name in func_co_names:
                    kwargs[name] = val

            try:
                await func(pl, **kwargs)
            except Exception:
                print("Ignoring Exception in handle_event:")
                self.logger.error(traceback.format_exc())

    def include(self, group: EventGroup) -> None:
        """Add the events from an :class:`~EventGroup` to this
        :class:`~EventHandler`."""

        for name, funcs in group.events.items():
            self.events.setdefault(name, list())
            self.events[name].extend(funcs)


class EventGroup:
    """A group of events.

    Functionaly identical to :class:`~commands.CommandGroup`, except that
    each name can have multiple functions."""

    def __init__(self) -> None:
        self.events: dict[str, list[IPC_EVENT]] = {}

    def add(self, name: str) -> Callable[[IPC_EVENT], IPC_EVENT]:
        """Add an event to the list of events in this group.

        Parameters
        ----------
        name : str
            The name of the event to add.

        Returns
        -------
        Callable[[IPC_EVENT], IPC_EVENT]
            A decorator that accept the function.

        Example
        -------
        ```
        events = EventGroup()

        @events.add("some_event")
        async def function_1(pl):
            ...
        ```
        """
        self.events.setdefault(name, list())

        def decorator(func: IPC_EVENT) -> IPC_EVENT:
            self.events[name].append(func)
            return func

        return decorator

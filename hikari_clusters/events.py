from __future__ import annotations

import logging
import traceback
from typing import Any, Awaitable, Callable

from . import payload

__all__ = ("EventHandler", "EventGroup", "IPC_EVENT")

IPC_EVENT = Callable[..., Awaitable[None]]
_LOG = logging.getLogger(__name__)
_LOG.setLevel(logging.INFO)


class EventHandler:
    """Event handler.

    Parameters
    ----------
    event_kwargs : dict[str, Any], optional
        Extra kwargs to pass to event functions, default to None.
    """

    def __init__(self, event_kwargs: dict[str, Any] | None = None) -> None:
        self.events: dict[str, list[IPC_EVENT]] = {}
        self.event_kwargs = event_kwargs or {}

    async def handle_event(self, pl: payload.EVENT) -> None:
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
            func_co_names = func.__code__.co_varnames
            kwargs = {
                name: val
                for name, val in self.event_kwargs.items()
                if name in func_co_names
            }

            try:
                await func(pl, **kwargs)
            except Exception:
                _LOG.error("Ignoring Exception in handle_event:")
                _LOG.error(traceback.format_exc())

    def include(self, group: EventGroup) -> None:
        """Add the events from an :class:`~EventGroup` to this
        :class:`~EventHandler`."""

        for name, funcs in group.events.items():
            self.events.setdefault(name, [])
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

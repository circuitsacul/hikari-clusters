from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import TYPE_CHECKING, Collection, Generator

from . import payload

if TYPE_CHECKING:
    from .ipc_client import IpcClient

__all__ = ("NoResponse", "Callback", "CallbackHandler")


class NoResponse:
    """Indicates that the client failed to respond, either because the client
    took too long to respond or because the client disconnected."""


class Callback:
    """Manages responses for a single callback key.

    Must be used inside of :meth:`~CallbackHandler.callback`
    in order to work correctly.

    Parameters
    ----------
    key : int
        The callback key this callback is for.
    responders : Iterable[int]
        The clients that should be responding to this callback.
    """

    __slots__ = ("ipc", "key", "responders", "resps", "future")

    def __init__(self, ipc: IpcClient, key: int, responders: Collection[int]):
        self.ipc = ipc
        self.key = key
        self.responders = responders
        self.resps: dict[int, payload.RESPONSE | NoResponse] = {}
        self.future: asyncio.Future[None] = asyncio.Future()

    async def wait(self, timeout: float = 3.0) -> None:
        """Wait until all responses have been received.

        Parameters
        ----------
        timeout : float
            The timeout for when to set a clients response to
            :class:`~NoResponse`, default to 3.0
        """

        await asyncio.wait_for(self.future, timeout)
        for uid in self._get_missing():
            self.resps[uid] = NoResponse()

    def _get_missing(self) -> set[int]:
        return {uid for uid in self.responders if uid not in self.resps}

    def _handle_response(self, pl: payload.RESPONSE) -> None:
        self.resps[pl.author] = pl
        self._finish_if_finished()

    def _finish_if_finished(self) -> None:
        still_missing = self._check_disconnects()
        if not still_missing:
            self.future.set_result(None)

    def _check_disconnects(self) -> set[int]:
        """Check for disconnects, returning any still-missing responses."""

        missing = self._get_missing()
        for uid in missing.difference(self.ipc.client_uids):
            # the client disconnected
            self.resps[uid] = NoResponse()
            missing.remove(uid)

        return missing


class CallbackHandler:
    """Handles callbacks for a client."""

    def __init__(self, ipc: IpcClient):
        self.ipc = ipc
        self.callbacks: dict[int, Callback] = {}
        self._curr_cbk: int = 0

    @property
    def next_cbk(self) -> int:
        """Generate the next callback key."""

        self._curr_cbk += 1
        return self._curr_cbk

    def handle_disconnects(self) -> None:
        """Tell callbacks to double-check if they've finished after a client
        has disconnected."""

        for cb in self.callbacks.values():
            cb._finish_if_finished()

    def handle_response(self, pl: payload.RESPONSE) -> None:
        """Handle a response and adds it to the propert :class:`~Callback`
        if it exists.
        """

        cb = self.callbacks.get(pl.data.callback)
        if not cb:
            return

        cb._handle_response(pl)

    @contextmanager
    def callback(
        self, responders: Collection[int]
    ) -> Generator[Callback, None, None]:
        """Context manager for easy callback managing.

        Example
        -------
        ```
        with callback_handler.callback([1, 2, 3]) as cb:
            await send_command(callback_key=cb.key)
            await cb.wait()
        return cb.resps
        ```
        """

        cb = Callback(self.ipc, self.next_cbk, responders)
        self.callbacks[cb.key] = cb

        try:
            yield cb
        finally:
            del self.callbacks[cb.key]

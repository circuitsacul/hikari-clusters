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
import datetime
from contextlib import contextmanager
from typing import Generator, Iterable

from . import payload

__all__ = (
    "NoResponse",
    "Callback",
    "CallbackHandler",
)


class NoResponse:
    """Indicates that the client failed to respond,
    either due to a bug or because the client
    no longer exists.
    """

    pass


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

    def __init__(self, key: int, responders: Iterable[int]):
        self.key = key
        self.responders = responders
        self.resps: dict[int, payload.RESPONSE | NoResponse] = {}

    async def wait(self, timeout: float = 3.0) -> None:
        """Wait until all responses have been received.

        Parameters
        ----------
        timeout : float
            The timeout for when to set a clients response to
            :class:`~NoResponse`, default to 3.0
        """
        start = datetime.datetime.utcnow()

        while True:
            missing = [
                uid for uid in self.responders if uid not in self.resps.keys()
            ]
            if not missing:
                return

            if (datetime.datetime.utcnow() - start).seconds > timeout:
                for uid in missing:
                    self.resps[uid] = NoResponse()
                return

            await asyncio.sleep(0.1)


class CallbackHandler:
    """Handles callbacks for a client."""

    def __init__(self):
        self.callbacks: dict[int, Callback] = {}
        self._curr_cbk: int = 0

    @property
    def next_cbk(self) -> int:
        """Generate the next callback key."""

        self._curr_cbk += 1
        return self._curr_cbk

    def handle_response(self, pl: payload.RESPONSE) -> None:
        """Handles a response and adds it to the propert :class:`~Callback`
        if it exists.
        """

        if pl.data.callback not in self.callbacks:
            return

        self.callbacks[pl.data.callback].resps[pl.author] = pl

    @contextmanager
    def callback(
        self, responders: Iterable[int]
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

        cb = Callback(self.next_cbk, responders)
        self.callbacks[cb.key] = cb

        try:
            yield cb
        finally:
            del self.callbacks[cb.key]

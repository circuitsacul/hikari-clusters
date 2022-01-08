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

import logging

__all__ = (
    "FATAL",
    "ERROR",
    "WARN",
    "INFO",
    "DEBUG",
    "Logger",
)

FATAL = logging.FATAL
ERROR = logging.ERROR
WARN = logging.WARN
INFO = logging.INFO
DEBUG = logging.DEBUG


class _LoggingHandler(logging.Handler):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.fmt = logging.Formatter(logging.BASIC_FORMAT)
        self.limit = 50
        self.name = name

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        return f"{self.name} {record.levelname}: {record.message}"

    def emit(self, record: logging.LogRecord) -> None:
        print(self.format(record))


class Logger(logging.Logger):
    """A logging.Logger that forces the handlers
    to be the same at all times."""

    def __init__(self, name: str) -> None:
        super().__init__(name, INFO)
        self.hdlr = _LoggingHandler(name)

    @property  # type: ignore
    def handlers(self):
        return [self.hdlr]

    @handlers.setter
    def handlers(self, other):
        # take that stupid things that try to erase my logs
        return


# ignore info messages from websockets
logging.getLogger("websockets.client").setLevel(logging.FATAL)

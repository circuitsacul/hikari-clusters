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

from dataclasses import asdict, dataclass
from typing import Any, ClassVar, Dict, Generic, Type, TypeVar, Union

from .callbacks import NoResponse

__all__ = (
    "NoResponse",
    "DATA",
    "Payload",
    "Command",
    "Event",
    "ResponseOk",
    "ResponseTraceback",
    "ResponseNotFound",
    "PAYLOAD_DATA",
    "OPCODES",
    "RESPONSE",
    "COMMAND",
    "EVENT",
    "ANY_PAYLOAD",
    "deserialize_payload",
)

_P = TypeVar(
    "_P",
    bound="PAYLOAD_DATA",
)
DATA = Union[Dict[str, Any], None]


@dataclass
class Payload(Generic[_P]):
    """The base payload for all messages sent and received
    by :class:`~ipc_client.IpcClient`."""

    opcode: int
    """The payload type."""
    author: int
    """The uid of the client that sent this payload."""
    recipients: list[int]
    """The uids that this payload was sent to."""
    data: _P
    """The data of the payload."""

    def serialize(self) -> dict[str, Any]:
        """Converts the payload to a dictionary."""
        return asdict(self)


@dataclass
class Command:
    """The data for a command payload."""

    name: str
    """The name of the command."""
    callback: int
    """The key to use when sending responses to this command."""
    data: DATA
    """The data of the command."""

    opcode: ClassVar[int] = 0


@dataclass
class Event:
    """The data for an event payload."""

    name: str
    """The name of the event."""
    data: DATA
    """The data of the event."""

    opcode: ClassVar[int] = 1


@dataclass
class ResponseOk:
    """The data for a response payload where the function exitted properly."""

    callback: int
    """The key sent in the command payload."""
    data: DATA
    """The data of the response."""

    opcode: ClassVar[int] = 2


@dataclass
class ResponseTraceback:
    """The data for a response payload where the function raised an
    exception."""

    callback: int
    """The key sent in the command payload."""
    traceback: str
    """The exception traceback."""

    opcode: ClassVar[int] = 3


@dataclass
class ResponseNotFound:
    """The data for a response payload where no function for the command
    name sent was found."""

    callback: int
    """The key sent in the command payload."""

    opcode: ClassVar[int] = 4


PAYLOAD_DATA = Union[
    Command,
    Event,
    ResponseOk,
    ResponseTraceback,
    ResponseNotFound,
]

OPCODES: dict[int, Type[PAYLOAD_DATA]] = {
    Command.opcode: Command,
    Event.opcode: Event,
    ResponseOk.opcode: ResponseOk,
    ResponseTraceback.opcode: ResponseTraceback,
    ResponseNotFound.opcode: ResponseNotFound,
}

RESPONSE = Payload[Union[ResponseOk, ResponseTraceback, ResponseNotFound]]
"""Payload sent in response to a command."""
COMMAND = Payload[Command]
"""Payload sent to tell another client to do something and then wait
for a response."""
EVENT = Payload[Event]
"""Payload for sending messages to another client without waiting for a
response."""
ANY_PAYLOAD = Payload[PAYLOAD_DATA]


def deserialize_payload(data: dict[str, Any]) -> ANY_PAYLOAD:
    """Convert a dictionary to a :class:`~Payload`."""

    data_data_cls = OPCODES[data["opcode"]]
    data_data = data_data_cls(**data.pop("data"))
    return Payload(**data, data=data_data)

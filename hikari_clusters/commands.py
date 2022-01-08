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
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from . import payload
from .exceptions import CommandAlreadyExists

if TYPE_CHECKING:
    from .ipc_client import IpcClient


__all__ = (
    "CommandHandler",
    "CommandGroup",
    "IPC_COMMAND",
)


IPC_COMMAND = Callable[..., Awaitable[payload.DATA]]


class CommandHandler:
    """Command handler.

    Parameters
    ----------
    client : IpcClient
        The IpcClient that owns this command handler.
    cmd_kwargs : dict[str, Any], optional
        Extra kwargs to pass to any command functions, default to None.
    """

    def __init__(
        self,
        client: IpcClient,
        cmd_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.commands: dict[str, IPC_COMMAND] = {}
        self.cmd_kwargs = cmd_kwargs or {}

    async def handle_command(
        self,
        pl: payload.COMMAND,
    ) -> None:
        """Parse a command payload and call the correct function,
        then send a response.

        Parameters
        ----------
        pl : payload.COMMAND
            The command payload to handle.
        """

        command = self.commands.get(pl.data.name)
        if command is None:
            await self.client.send_not_found_response(
                [pl.author], pl.data.callback
            )
            return

        kwargs = {}
        function_co_names = command.__code__.co_varnames
        for name, val in self.cmd_kwargs.items():
            if name in function_co_names:
                kwargs[name] = val

        try:
            r = await command(pl, **kwargs)
        except Exception:
            tb = traceback.format_exc()
            await self.client.send_tb_response(
                [pl.author], pl.data.callback, tb
            )
        else:
            await self.client.send_ok_response(
                [pl.author], pl.data.callback, r
            )

    def include(self, group: CommandGroup) -> None:
        """Copy all commands from a :class:`~CommandGroup`
        to this :class:`~CommandHandler`."""

        for name, func in group.commands.items():
            if name in self.commands:
                raise CommandAlreadyExists(name)
            self.commands[name] = func


class CommandGroup:
    """A group of commands.

    Example Usage
    -------------
    ```
    group = CommandGroup()

    @group.add("do_addition")
    async def any_name_at_all(pl: payload.COMMAND) -> int:
        return sum(pl.data.data["numbers"])

    bot.ipc.commands.include(group)
    ```
    """

    def __init__(self) -> None:
        self.commands: dict[str, IPC_COMMAND] = {}

    def add(self, name: str) -> Callable[[IPC_COMMAND], IPC_COMMAND]:
        """Add a command to the command group.

        Parameters
        ----------
        name : str
            The name of the command.

        Returns
        -------
        Callable[[IPC_COMMAND], IPC_COMMAND]
            Returns a function that accepts the function directly.

        Raises
        ------
        RuntimeError
            The command name already exists in this group.

        Example
        -------
        ```
        group = CommandGroup()

        @group.add("command_name")
        async def function_name(pl):
            ...
        ```
        """

        if name in self.commands:
            raise CommandAlreadyExists(name)

        def decorator(func: IPC_COMMAND) -> IPC_COMMAND:
            self.commands[name] = func
            return func

        return decorator

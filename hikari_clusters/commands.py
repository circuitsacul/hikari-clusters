from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from . import payload
from .exceptions import CommandAlreadyExists

if TYPE_CHECKING:
    from .ipc_client import IpcClient


__all__ = ("CommandHandler", "CommandGroup", "IPC_COMMAND")


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
        self, client: IpcClient, cmd_kwargs: dict[str, Any] | None = None
    ) -> None:
        self.client = client
        self.commands: dict[str, IPC_COMMAND] = {}
        self.cmd_kwargs = cmd_kwargs or {}

    async def handle_command(self, pl: payload.COMMAND) -> None:
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

        function_co_names = command.__code__.co_varnames
        kwargs = {
            name: val
            for name, val in self.cmd_kwargs.items()
            if name in function_co_names
        }

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

from hikari import HikariError


class HikariClustersError(HikariError):
    pass


_E = HikariClustersError


class InvalidIpcToken(_E):
    """The token passed to the ipc server was incorrect."""

    def __init__(self) -> None:
        super().__init__("Invalid IPC token.")


class CommandAlreadyExists(_E):
    """Raised when the command name used is already being used."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Command {name} already exists.")

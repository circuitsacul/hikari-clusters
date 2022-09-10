# When you send `!exec <code>`, the code will be sent to all clusters. Try
# running `print(1)` with multiple servers.

from typing import Any

from hikari import GatewayBot, GuildMessageCreateEvent

from hikari_clusters import Cluster, ClusterLauncher, Server, payload
from hikari_clusters.commands import CommandGroup


class MyBot(GatewayBot):
    cluster: Cluster

    def __init__(self) -> None:
        super().__init__(token="discord token")

        self.listen(GuildMessageCreateEvent)(self.on_message)

    async def on_message(self, event: GuildMessageCreateEvent) -> None:
        if not event.content:
            return
        if event.content.startswith("!exec"):
            await self.cluster.ipc.send_command(
                self.cluster.ipc.clusters,
                "exec_code",
                {"code": event.content[6:]},
            )

    async def start(self, *args: Any, **kwargs: Any) -> None:
        # we include commands inside start() because self.cluster is not
        # defined inside __init__()
        self.cluster.ipc.commands.include(COMMANDS)
        await super().start(*args, **kwargs)


COMMANDS = CommandGroup()


@COMMANDS.add("exec_code")
async def exec_code(pl: payload.COMMAND) -> None:
    assert pl.data.data is not None
    exec(pl.data.data["code"])


def run() -> None:
    Server(
        host="localhost",
        port=8765,
        token="ipc token",
        cluster_launcher=ClusterLauncher(MyBot),
    ).run()

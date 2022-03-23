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

# When you send `!exec <code>`, the code will be sent to all clusters. Try
# running `print(1)` with multiple servers.

from hikari import GatewayBot, GuildMessageCreateEvent

from hikari_clusters import Cluster, ClusterLauncher, Server, payload
from hikari_clusters.commands import CommandGroup


class MyBot(GatewayBot):
    _cluster: Cluster

    def __init__(self) -> None:
        super().__init__(token="discord token")

        self.listen(GuildMessageCreateEvent)(self.on_message)

    async def on_message(self, event: GuildMessageCreateEvent) -> None:
        if not event.content:
            return
        if event.content.startswith("!exec"):
            await self.cluster.ipc.send_command(
                self.cluster.ipc.cluster_uids,
                "exec_code",
                {"code": event.content[6:]},
            )

    @property
    def cluster(self) -> Cluster:
        return self._cluster

    @cluster.setter
    def cluster(self, value: Cluster) -> None:
        # when the cluster is set, we can include our commands.
        self._cluster = value
        self._cluster.ipc.commands.include(COMMANDS)


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

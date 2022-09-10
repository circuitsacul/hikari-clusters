from hikari import GatewayBot

from hikari_clusters import Cluster, ClusterLauncher, Server


class MyBot(GatewayBot):
    cluster: Cluster
    # purely optional typehint. ClusterLauncher will set this on init

    def __init__(self) -> None:
        super().__init__(token="discord token")

        # load modules & events here


def run() -> None:
    Server(
        host="localhost",
        port=8765,
        token="ipc token",
        cluster_launcher=ClusterLauncher(MyBot),
    ).run()

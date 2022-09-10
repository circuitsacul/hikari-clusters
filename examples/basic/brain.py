from hikari_clusters import Brain


def run() -> None:
    Brain(
        host="localhost",
        port=8765,
        token="ipc token",
        total_servers=1,
        clusters_per_server=2,
        shards_per_cluster=3,
    ).run()

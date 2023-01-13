# hikari-clusters
[![pypi](https://github.com/TrigonDev/hikari-clusters/actions/workflows/pypi.yml/badge.svg)](https://pypi.org/project/hikari-clusters)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/TrigonDev/hikari-clusters/main.svg)](https://results.pre-commit.ci/latest/github/TrigonDev/hikari-clusters/main)

[Documentation](https://github.com/circuitsacul/hikari-clusters/wiki)

hikari-clusters allows you to scale your Discord bots horizontally by using multiprocessing and websockets. This means that your bot can use multiple cores, as well as multiple VPSes.

See the #clusters channel in the hikari-py discord for help.

```py
# brain.py
from hikari_clusters import Brain

Brain(
    host="localhost",
    port=8765,
    token="ipc token",
    total_servers=1,
    clusters_per_server=2,
    shards_per_cluster=3,
).run()
```
```py
# server.py
from hikari import GatewayBot
from hikari_clusters import Cluster, ClusterLauncher, Server

class MyBot(GatewayBot):
    cluster: Cluster

    def __init__(self):
        super().__init__(token="discord token")

        # load modules & events here

Server(
    host="localhost",
    port=8765,
    token="ipc token",
    cluster_launcher=ClusterLauncher(MyBot),
).run()
```

Run examples with `python -m examples.<example name>` (`python -m examples.basic`)

<p align="center">
  <img src="https://us-east-1.tixte.net/uploads/files.circuitsacul.dev/hikari-clusters-diagram.jpg">
</p>

## Creating Self-Signed Certificate:
```
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout cert.key -out cert.cert && cat cert.key cert.cert > cert.pem
```

# hikari-clusters
[![pypi](https://github.com/TrigonDev/hikari-clusters/actions/workflows/pypi.yml/badge.svg)](https://pypi.org/project/hikari-clusters)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/TrigonDev/hikari-clusters/main.svg)](https://results.pre-commit.ci/latest/github/TrigonDev/hikari-clusters/main)

[Documentation](https://github.com/trigondev/hikari-clusters/wiki) | [CONTRIBUTING.md](https://github.com/trigondev/.github/tree/main/CONTRIBUTING.md)

Clustering for hikari made easy. Run examples with `python -m examples.<example name>` (`python -m examples.basic`)

If you need support, you can contact me `Circuit#3397` after joining [this server](https://discord.gg/dGAzZDaTS9). I don't accept friend requests.

<p align="center">
  <img src="https://us-east-1.tixte.net/uploads/circuit.is-from.space/clustered-bot-structure.jpeg">
</p>

## Creating Self-Signed Certificate:
```
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout cert.key -out cert.cert && cat cert.key cert.cert > cert.pem
```

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import pathlib
import signal
from typing import TYPE_CHECKING, Any

from hikari_clusters import payload
from hikari_clusters.info_classes import ClusterInfo, ServerInfo

from .base_client import BaseClient
from .commands import CommandGroup
from .events import EventGroup
from .ipc_client import IpcClient

if TYPE_CHECKING:
    from .cluster import ClusterLauncher

__all__ = ("Server",)

_LOG = logging.getLogger(__name__)
_LOG.setLevel(logging.INFO)


class Server(BaseClient):
    """A group of clusters.

    Parameters
    ----------
    host : str
        The host of the ipc server (brain).
    port : int
        The port of the ipc server.
    token : str
        The token required by the ipc server.
    cluster_launch : :class:`~ClusterLauncher`
        The cluster launcher.
    certificate_path : pathlib.Path, optional
        Required for secure (wss) connections, by default None.
    """

    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        cluster_launcher: ClusterLauncher,
        certificate_path: pathlib.Path | str | None = None,
    ) -> None:
        if isinstance(certificate_path, str):
            certificate_path = pathlib.Path(certificate_path)

        super().__init__(
            IpcClient.get_uri(host, port, certificate_path is not None),
            token,
            True,
            certificate_path,
        )

        self.ipc.commands.cmd_kwargs["server"] = self
        self.ipc.events.event_kwargs["server"] = self
        self.ipc.commands.include(_C)
        self.ipc.events.include(_E)

        self.cluster_processes: dict[int, multiprocessing.Process] = {}
        """Maps the smallest shard id of the cluster to it's process."""

        self.cluster_launcher = cluster_launcher

    @property
    def clusters(self) -> list[ClusterInfo]:
        """A list of :class:`~info_classes.ClusterInfo`
        that belong to this server."""

        return [
            c
            for c in self.ipc.clusters.values()
            if c.server_uid == self.ipc.uid
        ]

    def get_info(self) -> ServerInfo:
        # <<<docstring from BaseClient>>>

        assert self.ipc.uid
        return ServerInfo(self.ipc.uid, [c.uid for c in self.clusters])

    def run(self) -> None:
        """Run the server, wait for the server to stop, and then shutdown."""

        def sigstop(*args: Any, **kwargs: Any) -> None:
            self.stop()

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, sigstop)
        loop.run_until_complete(self.start())
        loop.run_until_complete(self.join())
        loop.run_until_complete(self.close())

    async def start(self) -> None:
        # <<<docstring from BaseClient>>>

        await super().start()
        self.tasks.create_task(self._loop_cleanup_processes())

    async def _loop_cleanup_processes(self) -> None:
        while True:
            await asyncio.sleep(5)
            await self.ipc.wait_until_ready()
            if (brain := self.ipc.brain) is None:
                continue

            dead_procs: list[int] = []
            for smallest_shard_id, proc in self.cluster_processes.items():
                if not proc.is_alive():
                    await self.ipc.send_event(
                        [brain.uid],
                        "cluster_died",
                        {"smallest_shard_id": smallest_shard_id},
                    )
                    dead_procs.append(smallest_shard_id)

            for shard_id in dead_procs:
                del self.cluster_processes[shard_id]


_C = CommandGroup()


@_C.add("launch_cluster")
async def start_cluster(pl: payload.COMMAND, server: Server) -> None:
    assert pl.data.data is not None
    _LOG.info(f"Launching Cluster with shard_ids {pl.data.data['shard_ids']}")
    p = multiprocessing.Process(
        target=server.cluster_launcher.launch_cluster,
        kwargs={
            "ipc_uri": server.ipc.uri,
            "ipc_token": server.ipc.token,
            "shard_ids": pl.data.data["shard_ids"],
            "shard_count": pl.data.data["shard_count"],
            "server_uid": server.ipc.uid,
            "certificate_path": server.ipc.certificate_path,
        },
    )
    p.start()
    server.cluster_processes[min(pl.data.data["shard_ids"])] = p


_E = EventGroup()


@_E.add("server_stop")
async def server_stop(pl: payload.EVENT, server: Server) -> None:
    server.stop()

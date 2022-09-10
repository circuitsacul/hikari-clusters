from __future__ import annotations

import asyncio
import pathlib
import signal
from typing import Any

from hikari_clusters.base_client import BaseClient
from hikari_clusters.info_classes import BrainInfo

from . import payload
from .events import EventGroup
from .ipc_client import IpcClient
from .ipc_server import IpcServer

__all__ = ("Brain",)


class Brain(BaseClient):
    """The brain of the bot.

    Allows for comunication between clusters and servers,
    and manages what clusters to launch and when to launch
    them.

    Parameters
    ----------
    host : str
        The host to run the brain on.
    port : int
        The port to run the brain on.
    token : str
        The token to require from any connecting clients.
    total_servers : int
        The number of servers to expect.
    clusters_per_server : int
        The number of clusters each server should run.
    shards_per_clusters : int
        The number of shards each cluster should have.
    certificate_path : pathlib.Path, optional
        Required for secure (wss) connections, by default None.
    """

    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        total_servers: int,
        clusters_per_server: int,
        shards_per_cluster: int,
        certificate_path: pathlib.Path | str | None = None,
    ) -> None:
        certificate_path = (
            pathlib.Path(certificate_path)
            if isinstance(certificate_path, str)
            else certificate_path
        )

        super().__init__(
            IpcClient.get_uri(host, port, certificate_path is not None),
            token,
            True,
            certificate_path,
        )

        self.total_servers = total_servers
        self.cluster_per_server = clusters_per_server
        self.shards_per_cluster = shards_per_cluster

        self.server = IpcServer(
            host, port, token, certificate_path=certificate_path
        )

        self.ipc.commands.cmd_kwargs["brain"] = self
        self.ipc.events.event_kwargs["brain"] = self
        self.ipc.events.include(_E)

        self._waiting_for: tuple[int, int] | None = None

    @property
    def total_clusters(self) -> int:
        """The total number of clusters across all servers."""

        return self.total_servers * self.cluster_per_server

    @property
    def total_shards(self) -> int:
        """The total number of shards across all clusters."""

        return self.total_clusters * self.shards_per_cluster

    @property
    def waiting_for(self) -> tuple[int, int] | None:
        """The cluster that has been asked to start, but has not
        started or is not ready.

        Returns
        -------
        tuple[int, int] | None
            None if there is no cluster that is being waited for,
            otherwise the uid of the server that should be
            starting the cluster and the smallest shard id
            of the cluster that should be starting.
        """

        if self._waiting_for is not None:
            server_uid, smallest_shard = self._waiting_for
            if (
                server_uid not in self.ipc.servers
                or smallest_shard in self.ipc.all_shards()
            ):
                # `server_uid not in self.ipc.server_uids`
                # This means that the server that was supposed to start
                # the cluster disconnected. This also means the
                # cluster will never start, so we set _waiting_for
                # to None.

                # `smallest_shard in self.ipc.all_shards()`
                # This means that the cluster has already started.

                self._waiting_for = None

        return self._waiting_for

    @waiting_for.setter
    def waiting_for(self, value: tuple[int, int] | None) -> None:
        self._waiting_for = value

    def get_info(self) -> BrainInfo:
        # <<<docstring from BaseClient>>>

        assert self.ipc.uid
        return BrainInfo(uid=self.ipc.uid)

    def run(self) -> None:
        """Run the brain, wait for the brain to stop, then cleanup."""

        def sigstop(*args: Any, **kwargs: Any) -> None:
            self.stop()

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, sigstop)
        loop.run_until_complete(self.start())
        loop.run_until_complete(self.join())
        loop.run_until_complete(self.close())

    async def start(self) -> None:
        # <<<docstring from BaseClient>>>

        self.stop_future = asyncio.Future()

        await self.server.start()
        await super().start()
        self.tasks.create_task(self._main_loop())

    async def close(self) -> None:
        # <<<docstring from BaseClient>>>

        self.ipc.stop()
        await self.ipc.close()

        self.server.stop()
        await self.server.close()

        self.tasks.cancel_all()
        await self.tasks.wait_for_all()

    def _get_next_cluster_to_launch(self) -> tuple[int, list[int]] | None:
        if len(self.ipc.servers) == 0:
            return None

        if not all(c.ready for c in self.ipc.clusters.values()):
            return None

        all_shard_ids = self.ipc.all_shards()

        if self.waiting_for is not None:
            return None

        for s in self.ipc.servers.values():
            if len(s.cluster_uids) < self.cluster_per_server:
                break
        else:
            return None

        shards_to_launch = set(range(self.total_shards)) - all_shard_ids
        if not shards_to_launch:
            return None

        return s.uid, list(shards_to_launch)[: self.shards_per_cluster]

    async def _main_loop(self) -> None:
        await self.ipc.wait_until_ready()
        while True:
            await asyncio.sleep(1)

            to_launch = self._get_next_cluster_to_launch()
            if not to_launch:
                continue

            server_uid, shards = to_launch

            await self.ipc.send_command(
                server_uid,
                "launch_cluster",
                {"shard_ids": shards, "shard_count": self.total_shards},
            )

            self.waiting_for = (server_uid, min(shards))


_E = EventGroup()


@_E.add("brain_stop")
async def brain_stop(pl: payload.EVENT, brain: Brain) -> None:
    brain.stop()


@_E.add("shutdown")
async def shutdown(pl: payload.EVENT, brain: Brain) -> None:
    await brain.ipc.send_event(brain.ipc.servers.keys(), "server_stop")
    brain.stop()


@_E.add("cluster_died")
async def cluster_died(pl: payload.EVENT, brain: Brain) -> None:
    assert pl.data.data is not None
    shard_id = pl.data.data["smallest_shard_id"]
    if brain._waiting_for is not None and brain._waiting_for[1] == shard_id:
        brain.waiting_for = None

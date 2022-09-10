from __future__ import annotations

import asyncio
import pathlib
import signal
from typing import Any, Type

from hikari import GatewayBot

from . import payload
from .base_client import BaseClient
from .events import EventGroup
from .info_classes import ClusterInfo

__all__ = ("Cluster", "ClusterLauncher")


class Cluster(BaseClient):
    """A subclass of :class:`~hikari.GatewayBot` designed for
    use with hikari-clusters.

    Parameters
    ----------
    ipc_uri : str
        The uri of the ipc server.
    ipc_token : str
        The token required by the ipc server.
    shard_ids : list[int]
        The shards this cluster should run.
    shard_count : int
        The total number of shards across all clusters.
    server_uid : int
        The uid of the server that owns the process running this clusters.
    init_kwargs : dict[str, Any]
        Any kwargs to pass to :meth:`hikari.GatewayBot.__init__`.
    """

    def __init__(
        self,
        ipc_uri: str,
        ipc_token: str,
        shard_ids: list[int],
        shard_count: int,
        server_uid: int,
        certificate_path: pathlib.Path | None,
        bot: GatewayBot,
    ) -> None:
        self.bot = bot

        self.shard_ids = shard_ids
        """The shard ids for this cluster."""
        self.server_uid = server_uid
        """The IPC uid of the server that launched this cluster."""

        self._shard_count = shard_count

        super().__init__(
            ipc_uri,
            ipc_token,
            reconnect=False,
            certificate_path=certificate_path,
        )

        self.ipc.events.include(_E)

        self.bot.cluster = self  # type: ignore

    def get_info(self) -> ClusterInfo:
        # <<<docstring from BaseClient>>>

        assert self.ipc.uid
        return ClusterInfo(
            self.ipc.uid, self.server_uid, self.shard_ids, self.ready
        )

    @property
    def cluster_id(self) -> int:
        """The id of this cluster.

        Note that this is not the ipc uid of the cluster;
        that can be found under :attr:`~Cluster.ipc.uid`.
        """

        return ClusterInfo.get_cluster_id(
            self.shard_ids[0], len(self.shard_ids)
        )

    @property
    def ready(self) -> bool:
        """Whether or not this cluster is fully launched."""

        return len(self.bot.shards) == len(self.shard_ids)

    @property
    def shard_count(self) -> int:
        """The total number of shards across all clusters."""

        return self._shard_count

    async def start(self, **kwargs: Any) -> None:
        # <<<docstring from BaseClient>>>

        await super().start()

        kwargs["shard_count"] = self.shard_count
        kwargs["shard_ids"] = self.shard_ids

        await self.bot.start(**kwargs)

    async def close(self) -> None:
        # <<<docstring from BaseClient>>>

        await self.bot.close()
        await super().close()


class ClusterLauncher:
    """Provides methods and utilities for launching clusters."""

    def __init__(
        self,
        bot_class: Type[GatewayBot],
        bot_init_kwargs: dict[str, Any] | None = None,
        bot_start_kwargs: dict[str, Any] | None = None,
        cluster_class: Type[Cluster] = Cluster,
    ) -> None:
        self.bot_class = bot_class
        self.bot_init_kwargs = bot_init_kwargs or {}
        self.bot_start_kwargs = bot_start_kwargs or {}
        self.cluster_class = cluster_class

    def launch_cluster(
        self,
        ipc_uri: str,
        ipc_token: str,
        shard_ids: list[int],
        shard_count: int,
        server_uid: int,
        certificate_path: pathlib.Path | None,
    ) -> None:
        """Should be called in a new :class:`~multiprocessing.Process`"""

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        cluster = self.cluster_class(
            ipc_uri,
            ipc_token,
            shard_ids,
            shard_count,
            server_uid,
            certificate_path,
            self.bot_class(**self.bot_init_kwargs),
        )

        def sigstop(*args: Any, **kwargs: Any) -> None:
            cluster.stop()

        loop.add_signal_handler(signal.SIGINT, sigstop)

        loop.run_until_complete(cluster.start())
        loop.run_until_complete(cluster.join())
        loop.run_until_complete(cluster.close())


_E = EventGroup()


@_E.add("cluster_stop")
async def handle_stop(pl: payload.EVENT, cluster: Cluster) -> None:
    cluster.stop()

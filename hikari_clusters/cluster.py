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

from __future__ import annotations

import asyncio
import sys
from dataclasses import asdict
from typing import Any, Type

from hikari import GatewayBot
from websockets.exceptions import ConnectionClosed

from . import log, payload
from .commands import CommandGroup
from .info_classes import ClusterInfo
from .ipc_client import IpcClient
from .task_manager import TaskManager

__all__ = (
    "Cluster",
    "ClusterLauncher",
)


class RecordStdout:
    """Redirects sys.stdout to a list, which the :class:`~Cluster`
    then sends to the :class:`~server.Server` to be printed."""

    def __init__(self):
        self.old_stdout = sys.stdout
        self.records: list[str] = []

    def pop(self) -> list[str]:
        """Returns the records while simultaneously clearing
        them from :class:`~RecordStdout`."""

        r = self.records
        self.records = []
        return r

    def write(self, text: str):
        self.records.append(text)

    def flush(self):
        pass

    def __getattr__(self, name: str):
        return self.old_stdout.__getattribute__(name)


class Cluster(GatewayBot):
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
        init_kwargs: dict[str, Any],
    ):
        init_kwargs.setdefault("allow_color", False)
        init_kwargs.setdefault("banner", None)

        super().__init__(**init_kwargs)

        self.shard_ids = shard_ids
        """The shard ids for this cluster."""
        self.server_uid = server_uid
        """The IPC uid of the server that launched this cluster."""

        self._shard_count = shard_count

        self.logger = log.Logger(f"Cluster {self.cluster_id}")
        self.ipc = IpcClient(
            ipc_uri,
            ipc_token,
            self.logger,
            reconnect=False,
            cmd_kwargs={"cluster": self},
        )
        self.ipc.commands.include(_C)
        self.__tasks = TaskManager(self.logger)

        self.stop_future: asyncio.Future | None = None

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

        return True  # TODO undo this
        return len(self.shards) == len(self.shard_ids)

    @property
    def shard_count(self) -> int:
        """Returns the total number of shards across all clusters."""

        return self._shard_count

    async def start(self, **kwargs):
        """Start the IPC and then the bot.

        Returns once all shards are ready."""

        self.stop_future = asyncio.Future()

        await self.ipc.start()

        self.__tasks.create_task(self._broadcast_cluster_info_loop())
        self.__tasks.create_task(self._broadcast_stdout_loop())

        kwargs["shard_count"] = self.shard_count
        kwargs["shard_ids"] = self.shard_ids

        # await super().start(**kwargs)

    async def join(self):
        """Wait for the bot to close, and then return.

        Does not ask the bot to close. Use :meth:`~Cluster.stop` to tell
        the bot to stop."""

        await asyncio.wait(
            [self.stop_future, self.ipc.stop_future],
            return_when=asyncio.FIRST_COMPLETED,
        )

    async def close(self):
        self.ipc.stop()
        await self.ipc.close()

        self.__tasks.cancel_all()
        await self.__tasks.wait_for_all()

        # await super().close()

    def stop(self):
        """Tells the bot and IPC to close."""

        self.stop_future.set_result(None)

    async def _broadcast_cluster_info_loop(self):
        while True:
            await self.ipc.wait_until_ready()
            try:
                await self.ipc.send_event(
                    self.ipc.client_uids,
                    "set_cluster_info",
                    asdict(
                        ClusterInfo(
                            self.ipc.uid,
                            self.server_uid,
                            self.shard_ids,
                            self.ready,
                        )
                    ),
                )
            except ConnectionClosed:
                return
            await asyncio.sleep(1)

    async def _broadcast_stdout_loop(self):
        while True:
            await self.ipc.wait_until_ready()
            # NOTE: stdout is actually a RecordStdout here.
            tosend: list[str] = sys.stdout.pop()
            if len(tosend) > 0:
                try:
                    await self.ipc.send_event(
                        [self.server_uid],
                        "cluster_stdout",
                        {"data": tosend},
                    )
                except ConnectionClosed:
                    return
            await asyncio.sleep(1)


class ClusterLauncher:
    """Provides methods and utilities for launching clusters."""

    def __init__(
        self,
        bot_class: Type[Cluster] = Cluster,
        bot_init_kwargs: dict[str, Any] | None = None,
        bot_start_kwargs: dict[str, Any] | None = None,
    ):
        self.bot_class = bot_class
        self.bot_init_kwargs = bot_init_kwargs or {}
        self.bot_start_kwargs = bot_start_kwargs or {}

    def launch_cluster(
        self,
        ipc_uri: str,
        ipc_token: str,
        shard_ids: list[int],
        shard_count: int,
        server_uid: int,
    ):
        """Should be called in a new :class:`~multiprocessing.Process`"""

        sys.stdout = RecordStdout()  # type: ignore

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        bot = Cluster(
            ipc_uri,
            ipc_token,
            shard_ids,
            shard_count,
            server_uid,
            self.bot_init_kwargs,
        )

        loop.run_until_complete(bot.start())
        loop.run_until_complete(bot.join())
        loop.run_until_complete(bot.close())


_C = CommandGroup()


@_C.add("cluster_stop")
async def handle_stop(pl: payload.COMMAND, cluster: Cluster):
    cluster.stop()

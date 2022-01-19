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
import pathlib
import signal

from . import log
from .ipc_client import IpcClient
from .ipc_server import IpcServer
from .task_manager import TaskManager

__all__ = ("Brain",)

LOG = log.Logger("Brain")


class Brain:
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
        self.tasks = TaskManager(LOG)

        self.total_servers = total_servers
        self.cluster_per_server = clusters_per_server
        self.shards_per_cluster = shards_per_cluster

        if isinstance(certificate_path, str):
            certificate_path = pathlib.Path(certificate_path)

        self.server = IpcServer(
            host,
            port,
            token,
            certificate_path=certificate_path,
        )
        self.ipc = IpcClient(
            IpcClient.get_uri(host, port, certificate_path is not None),
            token,
            LOG,
            certificate_path=certificate_path,
        )

        self.stop_future: asyncio.Future | None = None

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
            if server_uid not in self.ipc.server_uids:
                # This means that the server that was supposed to start
                # the cluster disconnected. This also means the
                # cluster will never start, so we set _waiting_for
                # to None.
                self._waiting_for = None
            elif smallest_shard in self.ipc.all_shards():
                # This means that the cluster has been started.
                self._waiting_for = None
        return self._waiting_for

    @waiting_for.setter
    def waiting_for(self, value: tuple[int, int] | None) -> None:
        self._waiting_for = value

    def run(self) -> None:
        """Run the brain, wait for the brain to stop, then cleanup."""

        def sigstop(*args, **kwargs):
            self.stop()

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, sigstop)
        loop.run_until_complete(self.start())
        loop.run_until_complete(self.join())
        loop.run_until_complete(self.close())

    async def start(self) -> None:
        """Start the brain.

        Returns as soon as all tasks have started.
        """
        self.stop_future = asyncio.Future()
        self.tasks.create_task(self._send_brain_uid_loop())
        self.tasks.create_task(self._main_loop())
        await self.server.start()
        await self.ipc.start()

    async def join(self) -> None:
        """Wait for the brain to stop."""

        assert self.stop_future
        await self.stop_future

    async def close(self) -> None:
        """Shuts the brain down."""

        self.server.stop()
        await self.server.close()

        self.ipc.stop()
        await self.ipc.close()

        self.tasks.cancel_all()
        await self.tasks.wait_for_all()

    def stop(self) -> None:
        """Tells the brain to stop."""

        assert self.stop_future
        self.stop_future.set_result(None)

    def _get_next_cluster_to_launch(self) -> tuple[int, list[int]] | None:
        if len(self.ipc.server_uids) == 0:
            return None

        if not all([c.ready for c in self.ipc.clusters.values()]):
            return None

        all_shard_ids = self.ipc.all_shards()

        if self.waiting_for is not None:
            return None

        for s in self.ipc.servers.values():
            if len(s.cluster_uids) < self.cluster_per_server:
                break
        else:
            return None

        shards_to_launch = set(range(0, self.total_shards))
        shards_to_launch.difference_update(all_shard_ids)
        if len(shards_to_launch) == 0:
            return None

        return s.uid, list(shards_to_launch)[0 : self.shards_per_cluster]

    async def _send_brain_uid_loop(self) -> None:
        while True:
            await self.ipc.wait_until_ready()
            await self.ipc.send_event(
                self.ipc.client_uids, "set_brain_uid", {"uid": self.ipc.uid}
            )
            await asyncio.sleep(1)

    async def _main_loop(self) -> None:
        await self.ipc.wait_until_ready()
        while True:
            await asyncio.sleep(1)

            to_launch = self._get_next_cluster_to_launch()
            if not to_launch:
                continue

            server_uid, shards = to_launch

            await self.ipc.send_command(
                [server_uid],
                "launch_cluster",
                {"shard_ids": shards, "shard_count": self.total_shards},
            )

            self.waiting_for = (server_uid, min(shards))

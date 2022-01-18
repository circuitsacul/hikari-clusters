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
import multiprocessing
import pathlib
import signal
from dataclasses import asdict
from typing import TYPE_CHECKING

from websockets.exceptions import ConnectionClosed

from hikari_clusters import payload
from hikari_clusters.info_classes import ClusterInfo, ServerInfo

from . import log
from .commands import CommandGroup
from .events import EventGroup
from .ipc_client import IpcClient
from .task_manager import TaskManager

if TYPE_CHECKING:
    from .cluster import ClusterLauncher

__all__ = ("Server",)

LOG = log.Logger("Server")


class Server:
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
        self.tasks = TaskManager(LOG)

        if isinstance(certificate_path, str):
            certificate_path = pathlib.Path(certificate_path)

        self.ipc = IpcClient(
            IpcClient.get_uri(host, port, certificate_path is not None),
            token,
            LOG,
            cmd_kwargs={"server": self},
            certificate_path=certificate_path,
        )
        self.certificate_path = certificate_path
        self.ipc.commands.include(_C)
        self.ipc.events.include(_E)

        self.cluster_processes: dict[int, multiprocessing.Process] = {}
        """Maps the smallest shard id of the cluster to it's process."""

        self.cluster_launcher = cluster_launcher

        self.stop_future: asyncio.Future | None = None

    @property
    def clusters(self) -> list[ClusterInfo]:
        """Returns a list of :class:`~info_classes.ClusterInfo`
        that belong to this server."""

        return [
            c
            for c in self.ipc.clusters.values()
            if c.server_uid == self.ipc.uid
        ]

    def run(self) -> None:
        """Run the server, wait for the server to stop, and then shutdown."""

        def sigstop(*args, **kwargs) -> None:
            self.stop()

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, sigstop)
        loop.run_until_complete(self.start())
        loop.run_until_complete(self.join())
        loop.run_until_complete(self.close())

    async def start(self) -> None:
        """Start the server.

        Returns as soon as all tasks are completed. Returning does not mean
        that the server is ready."""

        self.stop_future = asyncio.Future()
        self.tasks.create_task(self._broadcast_server_info_loop())
        await self.ipc.start()

    async def join(self) -> None:
        """Wait for the server to stop."""

        assert self.stop_future and self.ipc.stop_future
        await asyncio.wait(
            [self.stop_future, self.ipc.stop_future],
            return_when=asyncio.FIRST_COMPLETED,
        )

    async def close(self) -> None:
        """Shutdown the server and all clusters that belong to this server."""

        self.ipc.stop()
        await self.ipc.close()

        self.tasks.cancel_all()
        await self.tasks.wait_for_all()

    def stop(self) -> None:
        """Tell the server to stop."""

        assert self.stop_future
        self.stop_future.set_result(None)

    async def _broadcast_server_info_loop(self) -> None:
        while True:
            await self.ipc.wait_until_ready()
            assert self.ipc.uid
            try:
                await self.ipc.send_event(
                    self.ipc.client_uids,
                    "set_server_info",
                    asdict(
                        ServerInfo(
                            self.ipc.uid, [c.uid for c in self.clusters]
                        )
                    ),
                )
            except ConnectionClosed:
                pass
            await asyncio.sleep(1)


_C = CommandGroup()


@_C.add("launch_cluster")
async def start_cluster(pl: payload.COMMAND, server: Server) -> None:
    assert pl.data.data is not None
    LOG.info(f"Launching Cluster with shard_ids {pl.data.data['shard_ids']}")
    p = multiprocessing.Process(
        target=server.cluster_launcher.launch_cluster,
        kwargs={
            "ipc_uri": server.ipc.uri,
            "ipc_token": server.ipc.token,
            "shard_ids": pl.data.data["shard_ids"],
            "shard_count": pl.data.data["shard_count"],
            "server_uid": server.ipc.uid,
            "certificate_path": server.certificate_path,
        },
    )
    p.start()
    server.cluster_processes[min(pl.data.data["shard_ids"])] = p


_E = EventGroup()


@_E.add("cluster_stdout")
async def handle_cluster_stdout(pl: payload.EVENT) -> None:
    assert pl.data.data is not None
    print("".join(pl.data.data["data"]))

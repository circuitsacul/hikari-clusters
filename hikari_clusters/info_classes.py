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

from dataclasses import dataclass

__all__ = (
    "ServerInfo",
    "ClusterInfo",
)


@dataclass
class ServerInfo:
    """A representation of a :class:`~server.Server`."""

    uid: int
    """The ipc uid of the server."""
    cluster_uids: list[int]
    """The uids of the clusters that this server has launched."""


@dataclass
class ClusterInfo:
    """A representation of a :class:`~cluster.Cluster`."""

    uid: int
    """The ipc uid of the cluster."""
    server_uid: int
    """The uid of the server that launched this custer."""
    shard_ids: list[int]
    """The shard ids that this cluster owns."""
    ready: bool
    """Whether or not this cluster is ready."""

    @property
    def smallest_shard(self) -> int:
        """Returns the min of the shard_ids of this cluster."""

        return min(self.shard_ids)

    @property
    def cluster_id(self) -> int:
        """Returns the cluster id of this cluster."""

        return self.get_cluster_id(self.smallest_shard, len(self.shard_ids))

    @staticmethod
    def get_cluster_id(shard_id: int, shards_per_cluster: int) -> int:
        """Generates a cluster id based on the id of a shard.

        Assumes that all the shard ids of a cluster are adjacent."""

        return shard_id // shards_per_cluster

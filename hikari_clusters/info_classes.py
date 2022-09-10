from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

__all__ = ("ServerInfo", "ClusterInfo", "BaseInfo", "BrainInfo")


class BaseInfo:
    uid: int
    _info_classes: dict[int, type[BaseInfo]] = {}
    _info_class_id: int

    def __init_subclass__(cls) -> None:
        if not hasattr(cls, "_info_class_id"):
            raise AttributeError(f"{cls} is missing _info_class_id.")
        if used_by := BaseInfo._info_classes.get(cls._info_class_id):
            raise ValueError(
                f"_info_class_id {cls._info_class_id} is already used by "
                f"{used_by}"
            )
        BaseInfo._info_classes[cls._info_class_id] = cls

    def asdict(self) -> dict[str, Any]:
        """Convert this info class to a dictionary."""

        dct = asdict(self)
        dct["_info_class_id"] = self._info_class_id
        return dct

    @staticmethod
    def fromdict(data: dict[str, Any]) -> BaseInfo:
        """Convert a dictionary back into its info class."""

        cls = BaseInfo._info_classes[data.pop("_info_class_id")]
        return cls(**data)

    def __int__(self) -> int:
        """The IPC UID of the client this info class represents."""

        return self.uid


@dataclass
class ServerInfo(BaseInfo):
    """A representation of a :class:`~server.Server`."""

    _info_class_id = 0
    uid: int
    """The ipc uid of the server."""
    cluster_uids: list[int]
    """The uids of the clusters that this server has launched."""


@dataclass
class ClusterInfo(BaseInfo):
    """A representation of a :class:`~cluster.Cluster`."""

    _info_class_id = 1
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
        """The min of the shard_ids of this cluster."""

        return min(self.shard_ids)

    @property
    def cluster_id(self) -> int:
        """The cluster id of this cluster."""

        return self.get_cluster_id(self.smallest_shard, len(self.shard_ids))

    @staticmethod
    def get_cluster_id(shard_id: int, shards_per_cluster: int) -> int:
        """Generate a cluster id based on the id of a shard.

        Assumes that all the shard ids of a cluster are adjacent."""

        return shard_id // shards_per_cluster


@dataclass
class BrainInfo(BaseInfo):
    """A representation of a :class:`~brain.Brain`."""

    _info_class_id = 2
    uid: int
    """The ipc uid of the brain."""

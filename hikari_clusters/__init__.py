"""
An advanced yet easy-to-use clustering tool for Hikari.

https://github.com/trigondev/hikari-clusters
"""

from importlib.metadata import version

from hikari.internal.ux import init_logging

from . import close_codes, commands, events, exceptions, payload
from .base_client import BaseClient
from .brain import Brain
from .cluster import Cluster, ClusterLauncher
from .info_classes import BaseInfo, BrainInfo, ClusterInfo, ServerInfo
from .ipc_client import IpcClient
from .ipc_server import IpcServer
from .server import Server

init_logging("INFO", True, False)

__version__ = version(__name__)

__all__ = (
    "IpcClient",
    "IpcServer",
    "Brain",
    "Cluster",
    "ClusterLauncher",
    "Server",
    "BaseClient",
    "ClusterInfo",
    "ServerInfo",
    "BrainInfo",
    "BaseInfo",
    "payload",
    "events",
    "commands",
    "exceptions",
    "close_codes",
)

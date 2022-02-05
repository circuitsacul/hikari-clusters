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

"""
An advanced yet easy-to-use clustering tool for Hikari.

https://github.com/trigondev/hikari-clusters
"""

from importlib.metadata import version

from . import close_codes, commands, events, exceptions, payload
from .brain import Brain
from .cluster import Cluster, ClusterLauncher
from .info_classes import ClusterInfo, ServerInfo
from .ipc_client import IpcClient
from .ipc_server import IpcServer
from .server import Server

__version__ = version(__name__)

__all__ = (
    "IpcClient",
    "IpcServer",
    "Brain",
    "Cluster",
    "ClusterLauncher",
    "Server",
    "ClusterInfo",
    "ServerInfo",
    "payload",
    "events",
    "commands",
    "exceptions",
    "close_codes",
)

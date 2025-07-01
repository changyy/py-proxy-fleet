"""
proxy-fleet: A high-performance Python library for managing concurrent HTTP requests 
through multiple proxy servers with intelligent health monitoring and automatic failover.
"""

from .core.fleet import ProxyFleet
from .models.proxy import ProxyServer, ProxyStatus, ProxyProtocol
from .models.task import HttpTask, TaskResult, TaskStatus, HttpMethod
from .models.config import FleetConfig

__version__ = "1.0.1"
__author__ = "changyy"

__all__ = [
    "ProxyFleet",
    "ProxyServer", 
    "ProxyStatus",
    "ProxyProtocol",
    "HttpTask",
    "TaskResult",
    "TaskStatus",
    "HttpMethod",
    "FleetConfig",
]

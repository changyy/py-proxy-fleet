"""
proxy-fleet: A high-performance proxy server management tool with intelligent
load balancing, health monitoring, and graceful shutdown capabilities.

This is now focused on being a self-proxy server similar to HAProxy.
"""

# Core proxy fleet components
from .core.fleet import ProxyFleet
from .models.task import HttpTask, HttpMethod, TaskResult

# Core proxy server components
from .cli.main import ProxyStorage
from .server.enhanced_proxy_server import (EnhancedHTTPProxyServer,
                                           EnhancedProxyRotator,
                                           GracefulShutdownManager,
                                           LoadBalancingStrategy)
from .utils.proxy_utils import (create_proxy_from_url, filter_healthy_proxies,
                                load_proxies_from_file, save_proxies_to_file)
from .utils.socks_validator import SocksValidator

# Models
from .models.config import FleetConfig
from .models.proxy import ProxyServer, ProxyProtocol, ProxyStatus

__version__ = "2.1.2"
__author__ = "changyy"

__all__ = [
    # Core Fleet
    "ProxyFleet",
    "HttpTask", 
    "HttpMethod",
    "TaskResult",
    "FleetConfig",
    "ProxyServer",
    "ProxyProtocol",
    "ProxyStatus",
    # Server components
    "ProxyStorage",
    "EnhancedHTTPProxyServer",
    "GracefulShutdownManager",
    "EnhancedProxyRotator",
    "LoadBalancingStrategy",
    # Utils
    "SocksValidator",
    "create_proxy_from_url",
    "filter_healthy_proxies",
    "load_proxies_from_file",
    "save_proxies_to_file",
]

"""
proxy-fleet: A high-performance proxy server management tool with intelligent
load balancing, health monitoring, and graceful shutdown capabilities.

This is now focused on being a self-proxy server similar to HAProxy.
"""

# Core proxy server components
from .cli.main import ProxyStorage
from .server.enhanced_proxy_server import (EnhancedHTTPProxyServer,
                                           EnhancedProxyRotator,
                                           GracefulShutdownManager,
                                           LoadBalancingStrategy)
from .utils.proxy_utils import (create_proxy_from_url, filter_healthy_proxies,
                                load_proxies_from_file, save_proxies_to_file)
from .utils.socks_validator import SocksValidator

__version__ = "2.0.0"
__author__ = "changyy"

__all__ = [
    "ProxyStorage",
    "EnhancedHTTPProxyServer",
    "GracefulShutdownManager",
    "EnhancedProxyRotator",
    "LoadBalancingStrategy",
    "SocksValidator",
    "ProxyTester",
]

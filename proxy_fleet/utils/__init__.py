"""
Utilities package initialization.
"""

from .output import OutputManager, setup_logging
from .proxy_utils import (create_proxy_from_dict, create_proxy_from_url,
                          filter_healthy_proxies, load_proxies_from_file,
                          make_request_with_proxy,
                          reset_recent_failures_if_needed,
                          save_proxies_to_file, test_proxy_health)
from .socks_validator import ProxyDownloader, SocksValidator, SocksVersion

__all__ = [
    "test_proxy_health",
    "load_proxies_from_file",
    "save_proxies_to_file",
    "create_proxy_from_dict",
    "create_proxy_from_url",
    "filter_healthy_proxies",
    "reset_recent_failures_if_needed",
    "make_request_with_proxy",
    "OutputManager",
    "setup_logging",
    "SocksValidator",
    "ProxyDownloader",
    "SocksVersion",
]

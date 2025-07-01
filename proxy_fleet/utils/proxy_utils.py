"""
Utility functions for proxy fleet management.
"""

import asyncio
import aiohttp
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta

from ..models.proxy import ProxyServer, ProxyStatus


logger = logging.getLogger(__name__)


async def test_proxy_health(
    proxy: ProxyServer, 
    test_urls: List[str], 
    timeout: int = 10
) -> Tuple[bool, Optional[float], Optional[str]]:
    """
    Test proxy server health by making requests to test URLs.
    
    Args:
        proxy: Proxy server to test
        test_urls: List of URLs to test against
        timeout: Request timeout in seconds
        
    Returns:
        Tuple of (is_healthy, response_time, error_message)
    """
    proxy.status = ProxyStatus.TESTING
    
    connector = None
    try:
        # Setup proxy connector based on protocol
        if proxy.protocol.value in ['http', 'https']:
            # HTTP/HTTPS proxy support
            connector = aiohttp.TCPConnector()
            proxy_url = proxy.url
            
        elif proxy.protocol.value in ['socks4', 'socks5']:
            # SOCKS proxy support requires aiohttp-socks
            try:
                from aiohttp_socks import ProxyConnector
                
                if proxy.protocol.value == 'socks4':
                    from aiohttp_socks import ProxyType
                    proxy_type = ProxyType.SOCKS4
                else:  # socks5
                    from aiohttp_socks import ProxyType
                    proxy_type = ProxyType.SOCKS5
                
                connector = ProxyConnector(
                    proxy_type=proxy_type,
                    host=proxy.host,
                    port=proxy.port,
                    username=proxy.username,
                    password=proxy.password
                )
                proxy_url = None  # No need for proxy URL with ProxyConnector
                
            except ImportError:
                error_msg = f"SOCKS proxy support requires aiohttp-socks package: pip install aiohttp-socks"
                proxy.record_failure()
                return False, None, error_msg
        else:
            error_msg = f"Unsupported proxy protocol: {proxy.protocol}"
            proxy.record_failure()
            return False, None, error_msg
        
        # Test each URL
        for test_url in test_urls:
            start_time = datetime.now()
            
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
                
                # Make request through proxy
                request_kwargs = {
                    'headers': {'User-Agent': 'proxy-fleet-health-check/1.0'}
                }
                
                # Add proxy URL for HTTP/HTTPS proxies
                if proxy.protocol.value in ['http', 'https']:
                    request_kwargs['proxy'] = proxy_url
                
                async with session.get(test_url, **request_kwargs) as response:
                    
                    if response.status == 200:
                        response_time = (datetime.now() - start_time).total_seconds()
                        proxy.record_success(response_time)
                        return True, response_time, None
                    else:
                        error_msg = f"HTTP {response.status} from {test_url}"
                        proxy.record_failure()
                        return False, None, error_msg
    
    except asyncio.TimeoutError:
        error_msg = f"Timeout testing proxy {proxy.host}:{proxy.port}"
        proxy.record_failure()
        return False, None, error_msg
    
    except Exception as e:
        error_msg = f"Error testing proxy {proxy.host}:{proxy.port}: {str(e)}"
        proxy.record_failure()
        return False, None, error_msg
    
    finally:
        if connector:
            await connector.close()
    
    return False, None, "No test URLs succeeded"


def load_proxies_from_file(file_path: str) -> List[ProxyServer]:
    """
    Load proxy servers from JSON file.
    
    Args:
        file_path: Path to JSON file containing proxy list
        
    Returns:
        List of ProxyServer instances
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        logger.warning(f"Proxy file not found: {file_path}")
        return []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        proxies = []
        if isinstance(data, dict) and 'proxies' in data:
            proxy_list = data['proxies']
        elif isinstance(data, list):
            proxy_list = data
        else:
            logger.error(f"Invalid proxy file format: {file_path}")
            return []
        
        for proxy_data in proxy_list:
            try:
                proxy = ProxyServer.from_dict(proxy_data)
                proxies.append(proxy)
            except Exception as e:
                logger.error(f"Failed to parse proxy data {proxy_data}: {e}")
        
        logger.info(f"Loaded {len(proxies)} proxies from {file_path}")
        return proxies
    
    except Exception as e:
        logger.error(f"Failed to load proxies from {file_path}: {e}")
        return []


def save_proxies_to_file(proxies: List[ProxyServer], file_path: str):
    """
    Save proxy servers to JSON file.
    
    Args:
        proxies: List of ProxyServer instances
        file_path: Path to save JSON file
    """
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        data = {
            'proxies': [proxy.to_dict() for proxy in proxies],
            'updated_at': datetime.now().isoformat(),
            'total_count': len(proxies)
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(proxies)} proxies to {file_path}")
    
    except Exception as e:
        logger.error(f"Failed to save proxies to {file_path}: {e}")


def create_proxy_from_dict(data: Dict[str, Any]) -> ProxyServer:
    """
    Create ProxyServer instance from dictionary.
    
    Args:
        data: Dictionary containing proxy configuration
        
    Returns:
        ProxyServer instance
    """
    return ProxyServer.from_dict(data)


def create_proxy_from_url(url: str) -> ProxyServer:
    """
    Create ProxyServer instance from URL string.
    
    Args:
        url: Proxy URL (e.g., "http://user:pass@host:port")
        
    Returns:
        ProxyServer instance
    """
    from urllib.parse import urlparse
    
    parsed = urlparse(url)
    
    if not parsed.hostname or not parsed.port:
        raise ValueError(f"Invalid proxy URL: {url}")
    
    return ProxyServer(
        host=parsed.hostname,
        port=parsed.port,
        protocol=parsed.scheme,
        username=parsed.username,
        password=parsed.password
    )


def filter_healthy_proxies(proxies: List[ProxyServer]) -> List[ProxyServer]:
    """
    Filter list to return only healthy proxies.
    
    Args:
        proxies: List of all proxies
        
    Returns:
        List of healthy proxies
    """
    return [proxy for proxy in proxies if proxy.is_available]


def reset_recent_failures_if_needed(proxies: List[ProxyServer]):
    """
    Reset recent failure counts for proxies if the failure window has passed.
    
    Args:
        proxies: List of proxy servers to check
    """
    now = datetime.now()
    
    for proxy in proxies:
        if proxy.last_failure:
            time_since_failure = now - proxy.last_failure
            if time_since_failure.total_seconds() > (proxy.failure_window_minutes * 60):
                proxy.reset_recent_failures()
                
                # If proxy was unhealthy due to recent failures, mark as unknown to retry
                if proxy.status == ProxyStatus.UNHEALTHY:
                    proxy.status = ProxyStatus.UNKNOWN


async def make_request_with_proxy(
    proxy: ProxyServer,
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Any] = None,
    timeout: int = 30
) -> Tuple[int, Dict[str, str], bytes, float]:
    """
    Make HTTP request through a proxy server.
    
    協議差異說明：
    - HTTP/HTTPS Proxy: 在應用層工作，可以檢查和修改 HTTP 標頭
    - SOCKS4: 在會話層工作，支援 TCP，不支援認證和 IPv6
    - SOCKS5: SOCKS4 的升級版，支援 TCP/UDP、IPv6、多種認證方式
    
    Args:
        proxy: Proxy server to use
        url: Target URL
        method: HTTP method
        headers: Request headers
        data: Request body data
        timeout: Request timeout
        
    Returns:
        Tuple of (status_code, response_headers, response_data, response_time)
    """
    start_time = datetime.now()
    
    connector = None
    try:
        # Setup proxy connector based on protocol
        if proxy.protocol.value in ['http', 'https']:
            # HTTP/HTTPS Proxy
            # 特點：可以檢查 HTTP 標頭，支援 CONNECT 方法用於 HTTPS
            connector = aiohttp.TCPConnector()
            proxy_url = proxy.url
            
        elif proxy.protocol.value in ['socks4', 'socks5']:
            # SOCKS Proxy
            # 特點：在較低層級工作，更好的匿名性，支援更多協議
            try:
                from aiohttp_socks import ProxyConnector, ProxyType
                
                if proxy.protocol.value == 'socks4':
                    # SOCKS4: 較舊協議，不支援認證和 IPv6
                    proxy_type = ProxyType.SOCKS4
                    if proxy.username or proxy.password:
                        logger.warning(f"SOCKS4 不支援認證，忽略用戶名/密碼")
                else:  # socks5
                    # SOCKS5: 支援認證、IPv6、UDP
                    proxy_type = ProxyType.SOCKS5
                
                connector = ProxyConnector(
                    proxy_type=proxy_type,
                    host=proxy.host,
                    port=proxy.port,
                    username=proxy.username if proxy.protocol.value == 'socks5' else None,
                    password=proxy.password if proxy.protocol.value == 'socks5' else None
                )
                proxy_url = None
                
            except ImportError:
                raise Exception("SOCKS proxy support requires aiohttp-socks: pip install aiohttp-socks")
        else:
            raise Exception(f"Unsupported proxy protocol: {proxy.protocol}")
        
        # Prepare headers
        request_headers = headers or {}
        if 'User-Agent' not in request_headers:
            request_headers['User-Agent'] = 'proxy-fleet/1.0'
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            
            request_kwargs = {
                'headers': request_headers,
                'data': data
            }
            
            # Add proxy URL for HTTP/HTTPS proxies
            if proxy.protocol.value in ['http', 'https']:
                request_kwargs['proxy'] = proxy_url
            
            async with session.request(method, url, **request_kwargs) as response:
                
                response_time = (datetime.now() - start_time).total_seconds()
                response_data = await response.read()
                response_headers = dict(response.headers)
                
                proxy.record_success(response_time)
                
                return response.status, response_headers, response_data, response_time
    
    except Exception as e:
        proxy.record_failure()
        response_time = (datetime.now() - start_time).total_seconds()
        raise Exception(f"Request failed through proxy {proxy.host}:{proxy.port}: {str(e)}")
    
    finally:
        if connector:
            await connector.close()

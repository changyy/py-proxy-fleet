"""
SOCKS Proxy Validator using raw socket handshake.

This module implements direct SOCKS4/5 handshake validation inspired by
TheSpeedX/socker project. This allows validation of SOCKS proxies without
making HTTP requests, providing faster and more direct proxy verification.

Implementation references:
- TheSpeedX/socker: https://github.com/TheSpeedX/socker
- SOCKS4/5 Protocol specification handshake
"""

import asyncio
import json
import logging
import socket
import struct
from enum import Enum
from typing import Any, Dict, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class SocksVersion(Enum):
    """SOCKS protocol versions"""

    UNKNOWN = 0
    SOCKS4 = 4
    SOCKS5 = 5


class ValidationResult:
    """SOCKS 驗證結果包含 IP 信息"""

    def __init__(
        self,
        is_valid: bool,
        version: Optional[SocksVersion] = None,
        ip_info: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        self.is_valid = is_valid
        self.version = version
        self.ip_info = ip_info
        self.error = error

    def __str__(self):
        if not self.is_valid:
            return f"❌ Invalid - {self.error or 'Unknown error'}"

        result = f"✅ Valid SOCKS{self.version.value if self.version else '?'}"

        if self.ip_info:
            ip = self.ip_info.get("ip", "Unknown")
            country = self.ip_info.get("country", "Unknown")
            city = self.ip_info.get("city", "Unknown")
            org = self.ip_info.get("org", "Unknown")
            result += f" - IP: {ip} ({city}, {country}) - {org}"

        return result


class SocksValidator:
    """Validates SOCKS proxies using raw socket handshake"""

    def __init__(self, timeout: float = 10.0, check_ip_info: bool = True):
        """
        Initialize SOCKS validator

        Args:
            timeout: Connection timeout in seconds
            check_ip_info: Whether to query ipinfo.io after successful validation
        """
        self.timeout = timeout
        self.check_ip_info = check_ip_info

    async def validate_proxy(self, proxy_string: str) -> ValidationResult:
        """
        Validate a proxy string in format 'host:port' or 'protocol://host:port'

        Args:
            proxy_string: Proxy string like '127.0.0.1:1080' or 'socks5://127.0.0.1:1080'

        Returns:
            ValidationResult object
        """
        try:
            # Parse proxy string
            protocol = "socks5"  # default
            host_port = proxy_string

            if "://" in proxy_string:
                protocol_part, host_port = proxy_string.split("://", 1)
                protocol = protocol_part.lower()

            if ":" not in host_port:
                return ValidationResult(
                    False, error="Invalid proxy format: missing port"
                )

            parts = host_port.split(":")
            if len(parts) < 2:
                return ValidationResult(False, error="Invalid proxy format")

            host = parts[0].strip()
            try:
                port = int(parts[1].strip())
            except ValueError:
                return ValidationResult(False, error="Invalid port number")

            # Validate based on protocol
            if protocol in ["socks4"]:
                return self.validate_socks4(host, port)
            elif protocol in ["socks5"]:
                return self.validate_socks5(host, port)
            elif protocol in ["http", "https"]:
                return self.validate_http(host, port)
            else:
                return ValidationResult(
                    False, error=f"Unsupported protocol: {protocol}"
                )

        except Exception as e:
            return ValidationResult(False, error=f"Validation error: {str(e)}")

    async def check_ip_info_via_proxy(
        self, host: str, port: int, protocol: str = "socks5"
    ) -> Optional[Dict[str, Any]]:
        """
        通過 SOCKS 代理查詢 ipinfo.io 獲取 IP 信息

        Args:
            host: SOCKS proxy host
            port: SOCKS proxy port
            protocol: SOCKS protocol ('socks4' or 'socks5')

        Returns:
            IP 信息字典或 None（如果失敗）
        """
        try:
            # 使用 aiohttp-socks 通過代理發送 HTTP 請求
            import aiohttp
            from aiohttp_socks import ProxyConnector, ProxyType

            # 選擇代理類型
            proxy_type = ProxyType.SOCKS5 if protocol == "socks5" else ProxyType.SOCKS4

            connector = ProxyConnector(proxy_type=proxy_type, host=host, port=port)

            async with aiohttp.ClientSession(
                connector=connector, timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as session:
                async with session.get("https://ipinfo.io/json") as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.debug(
                            f"IP info via {host}:{port}: {data.get('ip')} ({data.get('country')})"
                        )
                        return data
                    else:
                        logger.debug(f"ipinfo.io returned status {response.status}")
                        return None

        except ImportError:
            logger.warning(
                "aiohttp-socks package required for IP info check: pip install aiohttp-socks"
            )
            return None
        except Exception as e:
            logger.debug(f"Failed to get IP info via {host}:{port}: {e}")
            return None

    def validate_socks4(
        self, host: str, port: int, target_host: str = "8.8.8.8", target_port: int = 80
    ) -> ValidationResult:
        """
        Validate SOCKS4 proxy using raw socket handshake
        Reference: TheSpeedX/socker implementation for SOCKS4 validation

        Args:
            host: SOCKS proxy host
            port: SOCKS proxy port
            target_host: Target host to connect through proxy (must be IP address for SOCKS4)
            target_port: Target port to connect through proxy

        Returns:
            ValidationResult object with is_valid status and optional IP information
        """
        sock = None
        try:
            # Validate port range (inspired by socker)
            if port < 0 or port > 65536:
                logger.debug(f"SOCKS4 {host}:{port} - Invalid port")
                return ValidationResult(is_valid=False, error="Invalid port")

            # Create socket and connect to SOCKS proxy
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((host, port))

            # Prepare SOCKS4 request packet (following socker's approach)
            # Format: VER(1) + CMD(1) + DSTPORT(2) + DSTIP(4) + USERID(variable) + NULL(1)
            try:
                # For SOCKS4, target must be an IP address, try to resolve if it's a hostname
                if not target_host.replace(".", "").isdigit():
                    target_ip = socket.gethostbyname(target_host)
                else:
                    target_ip = target_host
                target_ip_bytes = socket.inet_aton(target_ip)
            except socket.error:
                logger.debug(
                    f"SOCKS4 {host}:{port} - Cannot resolve target host: {target_host}"
                )
                return ValidationResult(
                    is_valid=False, error="Cannot resolve target host"
                )

            target_port_bytes = struct.pack(">H", target_port)

            # SOCKS4 packet: 0x04 (version) + 0x01 (connect) + port + ip + null terminator
            # This matches the exact format used in socker
            packet = b"\x04\x01" + target_port_bytes + target_ip_bytes + b"\x00"

            # Send SOCKS4 request
            sock.sendall(packet)

            # Receive response (8 bytes expected)
            response = sock.recv(8)

            if len(response) < 2:
                logger.debug(f"SOCKS4 {host}:{port} - Null response")
                return ValidationResult(is_valid=False, error="Null response")

            # Check response format (following socker's validation logic)
            # Response: VER(1) + REP(1) + DSTPORT(2) + DSTIP(4)
            if response[0] != int(
                "0x00", 16
            ):  # First byte should be 0x00 for SOCKS4 response
                logger.debug(f"SOCKS4 {host}:{port} - Bad response data")
                return ValidationResult(is_valid=False, error="Bad response data")

            if response[1] != int("0x5A", 16):  # 0x5A = request granted
                logger.debug(
                    f"SOCKS4 {host}:{port} - Server returned error (code: {response[1]})"
                )
                return ValidationResult(
                    is_valid=False, error=f"Server returned error (code: {response[1]})"
                )

            logger.debug(f"SOCKS4 {host}:{port} - Handshake successful")

            # Note: IP info check moved to async methods to avoid event loop issues
            return ValidationResult(
                is_valid=True, version=SocksVersion.SOCKS4, ip_info=None
            )

        except socket.timeout:
            logger.debug(f"SOCKS4 {host}:{port} - Connection timeout")
            return ValidationResult(is_valid=False, error="Connection timeout")
        except socket.error as e:
            logger.debug(f"SOCKS4 {host}:{port} - Connection refused: {e}")
            return ValidationResult(is_valid=False, error=f"Connection refused: {e}")
        except Exception as e:
            logger.debug(f"SOCKS4 {host}:{port} - Unexpected error: {e}")
            return ValidationResult(is_valid=False, error=f"Unexpected error: {e}")
        finally:
            if sock:
                try:
                    sock.close()
                except:
                    pass

    def validate_socks5(self, host: str, port: int) -> ValidationResult:
        """
        Validate SOCKS5 proxy using raw socket handshake
        Reference: TheSpeedX/socker implementation for SOCKS5 validation

        Args:
            host: SOCKS proxy host
            port: SOCKS proxy port

        Returns:
            ValidationResult object with is_valid status and optional IP information
        """
        sock = None
        try:
            # Validate port range (inspired by socker)
            if port < 0 or port > 65536:
                logger.debug(f"SOCKS5 {host}:{port} - Invalid port")
                return ValidationResult(is_valid=False, error="Invalid port")

            # Create socket and connect to SOCKS proxy
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((host, port))

            # Send SOCKS5 authentication request (following socker's approach)
            # Format: VER(1) + NMETHODS(1) + METHODS(variable)
            # We request no authentication (method 0x00)
            auth_request = b"\x05\x01\x00"
            sock.sendall(auth_request)

            # Receive authentication response (2 bytes expected)
            auth_response = sock.recv(2)

            if len(auth_response) < 2:
                logger.debug(f"SOCKS5 {host}:{port} - Null authentication response")
                return ValidationResult(
                    is_valid=False, error="Null authentication response"
                )

            # Check response format (following socker's validation logic)
            if auth_response[0] != int("0x05", 16):  # SOCKS version 5
                logger.debug(f"SOCKS5 {host}:{port} - Not SOCKS5 protocol")
                return ValidationResult(is_valid=False, error="Not SOCKS5 protocol")

            if auth_response[1] != int("0x00", 16):  # No authentication required
                logger.debug(f"SOCKS5 {host}:{port} - Requires authentication")
                return ValidationResult(is_valid=False, error="Requires authentication")

            logger.debug(f"SOCKS5 {host}:{port} - Authentication handshake successful")

            # Note: IP info check moved to async methods to avoid event loop issues
            return ValidationResult(
                is_valid=True, version=SocksVersion.SOCKS5, ip_info=None
            )

        except socket.timeout:
            logger.debug(f"SOCKS5 {host}:{port} - Connection timeout")
            return ValidationResult(is_valid=False, error="Connection timeout")
        except socket.error as e:
            logger.debug(f"SOCKS5 {host}:{port} - Connection refused: {e}")
            return ValidationResult(is_valid=False, error=f"Connection refused: {e}")
        except Exception as e:
            logger.debug(f"SOCKS5 {host}:{port} - Unexpected error: {e}")
            return ValidationResult(is_valid=False, error=f"Unexpected error: {e}")
        finally:
            if sock:
                try:
                    sock.close()
                except:
                    pass

    def detect_socks_version(self, host: str, port: int) -> SocksVersion:
        """
        Detect SOCKS protocol version by attempting handshakes
        Reference: TheSpeedX/socker getSocksVersion implementation

        Args:
            host: Proxy host
            port: Proxy port

        Returns:
            Detected SOCKS version or UNKNOWN
        """
        # Validate port range first (like socker does)
        try:
            port_int = int(port) if isinstance(port, str) else port
            if port_int < 0 or port_int > 65536:
                logger.debug(f"Invalid port: {host}:{port}")
                return SocksVersion.UNKNOWN
        except (ValueError, TypeError):
            logger.debug(f"Invalid port format: {host}:{port}")
            return SocksVersion.UNKNOWN

        sock = None
        try:
            # Create socket and connect (following socker's approach)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((host, port_int))

            # Try SOCKS4 first (simpler handshake, like socker does)
            if self._test_socks4_on_socket(sock, host, port_int):
                return SocksVersion.SOCKS4

            # Re-establish connection for SOCKS5 test
            sock.close()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((host, port_int))

            # Try SOCKS5
            if self._test_socks5_on_socket(sock):
                return SocksVersion.SOCKS5

            logger.debug(f"Not a SOCKS proxy: {host}:{port}")
            return SocksVersion.UNKNOWN

        except socket.timeout:
            logger.debug(f"Timeout: {host}:{port}")
            return SocksVersion.UNKNOWN
        except socket.error:
            logger.debug(f"Connection refused: {host}:{port}")
            return SocksVersion.UNKNOWN
        except Exception as e:
            logger.debug(f"Unexpected error for {host}:{port}: {e}")
            return SocksVersion.UNKNOWN
        finally:
            if sock:
                try:
                    sock.close()
                except:
                    pass

    def _test_socks4_on_socket(
        self,
        sock: socket.socket,
        host: str,
        port: int,
        target_host: str = "8.8.8.8",
        target_port: int = 80,
    ) -> bool:
        """Test SOCKS4 on an existing socket (inspired by socker's isSocks4)"""
        try:
            # Prepare target IP (SOCKS4 requires IP, not hostname)
            try:
                if not target_host.replace(".", "").replace(":", "").isdigit():
                    target_ip = socket.gethostbyname(target_host)
                else:
                    target_ip = target_host
                target_ip_bytes = socket.inet_aton(target_ip)
            except socket.error:
                return False

            target_port_bytes = struct.pack(">H", target_port)

            # Build SOCKS4 packet (exactly like socker)
            packet4 = b"\x04\x01" + target_port_bytes + target_ip_bytes + b"\x00"
            sock.sendall(packet4)

            # Receive response
            data = sock.recv(8)
            if len(data) < 2:
                return False

            # Validate response (exactly like socker)
            if data[0] != int("0x00", 16):  # Bad data
                return False
            if data[1] != int("0x5A", 16):  # Server returned an error
                return False

            return True
        except Exception:
            return False

    def _test_socks5_on_socket(self, sock: socket.socket) -> bool:
        """Test SOCKS5 on an existing socket (inspired by socker's isSocks5)"""
        try:
            # Send SOCKS5 auth request (exactly like socker)
            sock.sendall(b"\x05\x01\x00")

            # Receive response
            data = sock.recv(2)
            if len(data) < 2:
                return False

            # Validate response (exactly like socker)
            if data[0] != int("0x05", 16):  # Not socks5
                return False
            if data[1] != int("0x00", 16):  # Requires authentication
                return False

            return True
        except Exception:
            return False

    def validate_http(
        self, host: str, port: int, test_url: str = "http://httpbin.org/ip"
    ) -> ValidationResult:
        """
        驗證 HTTP 代理伺服器

        Args:
            host: Proxy host
            port: Proxy port
            test_url: URL to test with the proxy

        Returns:
            ValidationResult with validation status
        """
        try:
            import urllib.error
            import urllib.request

            proxy_url = f"http://{host}:{port}"
            proxy_handler = urllib.request.ProxyHandler(
                {"http": proxy_url, "https": proxy_url}
            )
            opener = urllib.request.build_opener(proxy_handler)

            request = urllib.request.Request(
                test_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
            )

            with opener.open(request, timeout=self.timeout) as response:
                if response.getcode() == 200:
                    return ValidationResult(is_valid=True, version=None)
                else:
                    return ValidationResult(
                        is_valid=False, error=f"HTTP {response.getcode()}"
                    )

        except urllib.error.URLError as e:
            return ValidationResult(is_valid=False, error=str(e))
        except Exception as e:
            return ValidationResult(is_valid=False, error=str(e))

    async def async_validate_http(
        self, host: str, port: int, test_url: str = "http://httpbin.org/ip"
    ) -> ValidationResult:
        """Async wrapper for HTTP proxy validation with IP info check"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, self.validate_http, host, port, test_url
        )

        # If validation successful and IP info check enabled, get IP information
        if result.is_valid and self.check_ip_info:
            try:
                import aiohttp

                proxy_url = f"http://{host}:{port}"

                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as session:
                    async with session.get(
                        "https://ipinfo.io/json", proxy=proxy_url
                    ) as response:
                        if response.status == 200:
                            ip_info = await response.json()
                            result.ip_info = ip_info
            except Exception as e:
                logger.debug(f"HTTP {host}:{port} - IP info lookup failed: {e}")

        return result

    async def async_validate_socks4(
        self, host: str, port: int, target_host: str = "8.8.8.8", target_port: int = 80
    ) -> ValidationResult:
        """Async wrapper for SOCKS4 validation with IP info check"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, self.validate_socks4, host, port, target_host, target_port
        )

        # If validation successful and IP info check enabled, get IP information
        if result.is_valid and self.check_ip_info:
            try:
                ip_info = await self.check_ip_info_via_proxy(host, port, "socks4")
                result.ip_info = ip_info
            except Exception as e:
                logger.debug(f"SOCKS4 {host}:{port} - IP info lookup failed: {e}")

        return result

    async def async_validate_socks5(self, host: str, port: int) -> ValidationResult:
        """Async wrapper for SOCKS5 validation with IP info check"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.validate_socks5, host, port)

        # If validation successful and IP info check enabled, get IP information
        if result.is_valid and self.check_ip_info:
            try:
                ip_info = await self.check_ip_info_via_proxy(host, port, "socks5")
                result.ip_info = ip_info
            except Exception as e:
                logger.debug(f"SOCKS5 {host}:{port} - IP info lookup failed: {e}")

        return result

    async def async_detect_socks_version(self, host: str, port: int) -> SocksVersion:
        """Async wrapper for SOCKS version detection"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.detect_socks_version, host, port)


class ProxyDownloader:
    """Downloads proxy lists from TheSpeedX/PROXY-List project"""

    # Public proxy list URLs from TheSpeedX/PROXY-List
    PROXY_SOURCES = {
        "http": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
        "socks4": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt",
        "socks5": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    }

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def download_proxy_list(
        self, proxy_type: str, limit: Optional[int] = None
    ) -> list:
        """
        Download proxy list from public source

        Args:
            proxy_type: Type of proxy ('http', 'socks4', 'socks5')
            limit: Maximum number of proxies to return

        Returns:
            List of proxy dictionaries with 'host', 'port', 'protocol' keys
        """
        if proxy_type not in self.PROXY_SOURCES:
            raise ValueError(f"Unsupported proxy type: {proxy_type}")

        url = self.PROXY_SOURCES[proxy_type]
        proxies = []

        try:
            import aiohttp

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.text()
                        lines = content.strip().split("\n")

                        for line in lines:
                            line = line.strip()
                            if ":" in line and not line.startswith("#"):
                                try:
                                    host, port_str = line.split(":", 1)
                                    port = int(port_str.strip())

                                    proxy_config = {
                                        "host": host.strip(),
                                        "port": port,
                                        "protocol": proxy_type,
                                    }
                                    proxies.append(proxy_config)

                                    if limit and len(proxies) >= limit:
                                        break

                                except (ValueError, IndexError):
                                    continue
                    else:
                        raise Exception(f"HTTP {response.status}")

        except Exception as e:
            logger.error(f"Failed to download {proxy_type} proxy list: {e}")
            raise

        logger.info(f"Downloaded {len(proxies)} {proxy_type} proxies from {url}")
        return proxies


# Quick test function
async def test_socks_validation():
    """Test SOCKS validation with real proxies"""
    print("🔍 Testing SOCKS Validation")
    print("-" * 40)

    downloader = ProxyDownloader()
    validator = SocksValidator(timeout=10)

    # Test SOCKS4 proxies
    try:
        print("📥 Downloading SOCKS4 proxies...")
        socks4_proxies = await downloader.download_proxy_list("socks4", limit=5)

        print(
            f"🔍 Testing {len(socks4_proxies)} SOCKS4 proxies with raw socket handshake..."
        )
        for proxy in socks4_proxies:
            host, port = proxy["host"], proxy["port"]
            result = await validator.async_validate_socks4(host, port)
            print(f"   {result}")

    except Exception as e:
        print(f"❌ SOCKS4 test failed: {e}")

    # Test SOCKS5 proxies
    try:
        print("\n📥 Downloading SOCKS5 proxies...")
        socks5_proxies = await downloader.download_proxy_list("socks5", limit=5)

        print(
            f"🔍 Testing {len(socks5_proxies)} SOCKS5 proxies with raw socket handshake..."
        )
        for proxy in socks5_proxies:
            host, port = proxy["host"], proxy["port"]
            result = await validator.async_validate_socks5(host, port)
            print(f"   {result}")

    except Exception as e:
        print(f"❌ SOCKS5 test failed: {e}")

    print("\n✅ SOCKS validation test completed")


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_socks_validation())

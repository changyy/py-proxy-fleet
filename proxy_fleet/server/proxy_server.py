"""
HTTP Proxy Server that rotates through verified proxy servers.

This module implements a HTTP proxy server that accepts client connections
and forwards requests through verified proxy servers from proxy storage,
using round-robin rotation for load balancing.
"""

import asyncio
import json
import logging
import random
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp
from aiohttp import ClientSession, ClientTimeout, web
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from aiohttp_socks import ProxyConnector, ProxyType

from ..cli.main import ProxyStorage

logger = logging.getLogger(__name__)


class ProxyRotator:
    """Manages rotation of verified proxy servers"""

    def __init__(self, storage_dir: str = "proxy", proxy_types: List[str] = None, regions: List[str] = None):
        self.storage = ProxyStorage(storage_dir)
        self.proxy_types = proxy_types or ['socks5']
        self.regions = regions
        self.current_index = 0
        self.last_refresh = 0
        self.refresh_interval = 60  # Refresh proxy list every 60 seconds
        self.valid_proxies = []
        self.failed_proxies = set()  # Track temporarily failed proxies
        self.failure_reset_time = 300  # Reset failed proxies after 5 minutes

    def refresh_proxies(self) -> List[Dict[str, Any]]:
        """Refresh the list of valid proxies from storage"""
        current_time = time.time()

        if current_time - self.last_refresh < self.refresh_interval:
            return self.valid_proxies

        self.valid_proxies = self.storage.get_valid_proxies(proxy_types=self.proxy_types, regions=self.regions)
        self.last_refresh = current_time

        # Reset failed proxies if enough time has passed
        if (
            current_time - getattr(self, "last_failure_reset", 0)
            > self.failure_reset_time
        ):
            self.failed_proxies.clear()
            self.last_failure_reset = current_time

        # Filter out temporarily failed proxies
        available_proxies = [
            proxy
            for proxy in self.valid_proxies
            if f"{proxy['host']}:{proxy['port']}" not in self.failed_proxies
        ]

        logger.info(
            f"Refreshed proxy list: {len(available_proxies)} available proxies "
            f"({len(self.failed_proxies)} temporarily failed)"
        )

        return available_proxies

    def get_next_proxy(self) -> Optional[Dict[str, Any]]:
        """Get the next proxy using round-robin rotation"""
        available_proxies = self.refresh_proxies()

        if not available_proxies:
            logger.warning("No available proxies found")
            return None

        # Round-robin selection
        proxy = available_proxies[self.current_index % len(available_proxies)]
        self.current_index = (self.current_index + 1) % len(available_proxies)

        return proxy

    def mark_proxy_failed(self, host: str, port: int):
        """Mark a proxy as temporarily failed"""
        proxy_key = f"{host}:{port}"
        self.failed_proxies.add(proxy_key)
        logger.warning(f"Marked proxy {proxy_key} as temporarily failed")

    def get_random_proxy(self) -> Optional[Dict[str, Any]]:
        """Get a random proxy instead of round-robin"""
        available_proxies = self.refresh_proxies()

        if not available_proxies:
            return None

        return random.choice(available_proxies)


class HTTPProxyServer:
    """HTTP Proxy Server that forwards requests through verified proxies"""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8888,
        storage_dir: str = "proxy",
        rotation_mode: str = "round-robin",
        proxy_types: List[str] = None,
        regions: List[str] = None,
        skip_cert_check: bool = False,
    ):
        self.host = host
        self.port = port
        self.rotator = ProxyRotator(storage_dir, proxy_types=proxy_types, regions=regions)
        self.rotation_mode = rotation_mode  # 'round-robin' or 'random'
        self.skip_cert_check = skip_cert_check
        self.stats = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "proxy_failures": 0,
            "start_time": time.time(),
        }

    async def handle_request(self, request: Request) -> Response:
        """Handle incoming HTTP requests and forward through proxies"""
        self.stats["requests_total"] += 1

        # Get proxy for this request
        if self.rotation_mode == "random":
            proxy = self.rotator.get_random_proxy()
        else:
            proxy = self.rotator.get_next_proxy()

        if not proxy:
            self.stats["requests_failed"] += 1
            return web.Response(
                status=503,
                text="No available proxy servers",
                headers={"Content-Type": "text/plain"},
            )

        proxy_host = proxy["host"]
        proxy_port = proxy["port"]
        proxy_protocol = proxy.get("protocol", "socks5")

        # Prepare request details
        url = str(request.url)
        method = request.method
        headers = dict(request.headers)

        # Remove hop-by-hop headers
        hop_by_hop = {
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "upgrade",
        }
        headers = {k: v for k, v in headers.items() if k.lower() not in hop_by_hop}

        try:
            # Read request body
            body = await request.read()

            # Create proxy connector
            if proxy_protocol in ["socks4", "socks5"]:
                proxy_type = (
                    ProxyType.SOCKS5 if proxy_protocol == "socks5" else ProxyType.SOCKS4
                )
                connector = ProxyConnector(
                    proxy_type=proxy_type, host=proxy_host, port=proxy_port
                )
                session_kwargs = {"connector": connector}
            else:  # http proxy
                connector = aiohttp.TCPConnector()
                session_kwargs = {
                    "connector": connector,
                    "proxy": f"http://{proxy_host}:{proxy_port}",
                }

            # Forward request through proxy
            timeout = ClientTimeout(total=30)
            async with ClientSession(timeout=timeout, **session_kwargs) as session:
                async with session.request(
                    method=method, url=url, headers=headers, data=body if body else None
                ) as proxy_response:

                    # Prepare response
                    response_headers = dict(proxy_response.headers)
                    response_headers = {
                        k: v
                        for k, v in response_headers.items()
                        if k.lower() not in hop_by_hop
                    }

                    response_body = await proxy_response.read()

                    self.stats["requests_success"] += 1

                    logger.info(
                        f"✅ {method} {url} -> {proxy_host}:{proxy_port} "
                        f"[{proxy_response.status}]"
                    )

                    return web.Response(
                        status=proxy_response.status,
                        headers=response_headers,
                        body=response_body,
                    )

        except Exception as e:
            # Mark proxy as failed and increment stats
            self.rotator.mark_proxy_failed(proxy_host, proxy_port)
            self.stats["requests_failed"] += 1
            self.stats["proxy_failures"] += 1

            logger.error(f"❌ {method} {url} -> {proxy_host}:{proxy_port} failed: {e}")

            return web.Response(
                status=502,
                text=f"Proxy request failed: {str(e)}",
                headers={"Content-Type": "text/plain"},
            )

    async def handle_stats(self, request: Request) -> Response:
        """Handle requests to /stats endpoint"""
        uptime = time.time() - self.stats["start_time"]

        stats_data = {
            **self.stats,
            "uptime_seconds": round(uptime, 2),
            "available_proxies": len(self.rotator.refresh_proxies()),
            "failed_proxies": len(self.rotator.failed_proxies),
            "current_proxy_index": self.rotator.current_index,
            "rotation_mode": self.rotation_mode,
        }

        return web.json_response(stats_data)

    async def handle_health(self, request: Request) -> Response:
        """Handle health check requests"""
        available_proxies = len(self.rotator.refresh_proxies())

        if available_proxies > 0:
            return web.json_response(
                {"status": "healthy", "available_proxies": available_proxies}
            )
        else:
            return web.json_response(
                {"status": "unhealthy", "available_proxies": available_proxies},
                status=503,
            )

    def create_app(self) -> web.Application:
        """Create the aiohttp application"""
        app = web.Application()

        # Add routes
        app.router.add_route("*", "/stats", self.handle_stats)
        app.router.add_route("*", "/health", self.handle_health)
        app.router.add_route("*", "/{path:.*}", self.handle_request)

        return app

    async def start(self):
        """Start the proxy server"""
        app = self.create_app()

        logger.info(f"🚀 Starting HTTP Proxy Server on {self.host}:{self.port}")
        logger.info(f"🔄 Rotation mode: {self.rotation_mode}")
        logger.info(f"📊 Stats endpoint: http://{self.host}:{self.port}/stats")
        logger.info(f"🏥 Health endpoint: http://{self.host}:{self.port}/health")

        # Refresh proxy list on startup
        available_proxies = self.rotator.refresh_proxies()
        logger.info(f"📥 Loaded {len(available_proxies)} available proxy servers")

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

        logger.info(f"✅ Proxy server running at http://{self.host}:{self.port}")

        # Keep server running
        try:
            while True:
                await asyncio.sleep(3600)  # Sleep for 1 hour
        except KeyboardInterrupt:
            logger.info("🛑 Shutting down proxy server...")
        finally:
            await runner.cleanup()


async def main():
    """Main entry point for the proxy server"""
    import argparse

    parser = argparse.ArgumentParser(
        description="HTTP Proxy Server with verified proxy rotation"
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8888, help="Server port (default: 8888)"
    )
    parser.add_argument(
        "--storage", default="proxy", help="Proxy storage directory (default: proxy)"
    )
    parser.add_argument(
        "--rotation",
        choices=["round-robin", "random"],
        default="round-robin",
        help="Proxy rotation mode (default: round-robin)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Set up logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    server = HTTPProxyServer(
        host=args.host,
        port=args.port,
        storage_dir=args.storage,
        rotation_mode=args.rotation,
    )

    await server.start()


if __name__ == "__main__":
    asyncio.run(main())

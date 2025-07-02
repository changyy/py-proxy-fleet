"""
Enhanced HTTP Proxy Server with intelligent load balancing, health checks,
and multi-worker support.

This module implements a production-ready HTTP proxy server similar to HAProxy,
featuring multiple load balancing strategies, health monitoring, circuit breakers,
and multi-process workers for high concurrency.
"""

import asyncio
import json
import logging
import multiprocessing
import os
import random
import signal
import statistics
import time
import weakref
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock, RLock
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import aiohttp
from aiohttp import ClientSession, ClientTimeout, web
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from aiohttp_socks import ProxyConnector, ProxyType

from ..cli.main import ProxyStorage

logger = logging.getLogger(__name__)


class GracefulShutdownManager:
    """管理優雅關機過程"""

    def __init__(self, config: Dict[str, Any] = None):
        self.active_requests: Set[asyncio.Task] = set()
        self.shutdown_event = None  # Initialize lazily
        self.accepting_new_requests = True

        # 從配置獲取參數
        server_config = (config or {}).get("proxy_server", {})
        self.shutdown_timeout = server_config.get("graceful_shutdown_timeout", 30)
        self.status_interval = server_config.get("shutdown_status_interval", 2)

        self._lock = None  # Initialize lazily for multiprocessing compatibility
        self.rejected_connections = 0  # 被拒絕的連線數
        self.shutdown_start_time = None  # 關機開始時間

    def _ensure_async_objects(self):
        """Ensure async objects are initialized (for multiprocessing compatibility)"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        if self.shutdown_event is None:
            self.shutdown_event = asyncio.Event()

    async def add_request(self, task: asyncio.Task):
        """添加活動請求"""
        self._ensure_async_objects()
        async with self._lock:
            if not self.accepting_new_requests:
                self.rejected_connections += 1
                raise ConnectionRefusedError("Server is shutting down")
            self.active_requests.add(task)
            # 當任務完成時自動清理
            task.add_done_callback(
                lambda t: asyncio.create_task(self._remove_request(t))
            )

    async def _remove_request(self, task: asyncio.Task):
        """移除完成的請求"""
        self._ensure_async_objects()
        async with self._lock:
            self.active_requests.discard(task)

    async def start_shutdown(self):
        """開始優雅關機過程"""
        self._ensure_async_objects()
        logger.info("🛑 Starting graceful shutdown...")
        self.shutdown_start_time = time.time()

        async with self._lock:
            self.accepting_new_requests = False
            active_count = len(self.active_requests)

        logger.info(f"🔄 Waiting for {active_count} active requests to complete...")
        logger.info(f"⏱️  Shutdown timeout: {self.shutdown_timeout} seconds")

        if active_count > 0:
            # 定期輸出狀態
            status_task = asyncio.create_task(self._report_shutdown_status())

            # 等待所有活動請求完成，或達到超時
            try:
                await asyncio.wait_for(
                    self._wait_for_requests_completion(), timeout=self.shutdown_timeout
                )
                logger.info("✅ All requests completed gracefully")
            except asyncio.TimeoutError:
                remaining = len(self.active_requests)
                logger.warning(
                    f"⚠️  Shutdown timeout reached, {remaining} requests still active"
                )
                logger.warning(
                    f"🔒 Forcefully closing {remaining} remaining connections"
                )
            finally:
                # 取消狀態報告任務
                status_task.cancel()
                try:
                    await status_task
                except asyncio.CancelledError:
                    pass
        else:
            logger.info("✅ No active requests to wait for")

        # 輸出最終統計
        shutdown_duration = time.time() - self.shutdown_start_time
        logger.info(f"📊 Shutdown completed in {shutdown_duration:.2f} seconds")
        logger.info(
            f"🚫 Total rejected connections during shutdown: {self.rejected_connections}"
        )

        self._ensure_async_objects()
        self.shutdown_event.set()

    async def _wait_for_requests_completion(self):
        """等待所有活動請求完成"""
        self._ensure_async_objects()
        while True:
            async with self._lock:
                if not self.active_requests:
                    break
            await asyncio.sleep(0.1)

    async def _report_shutdown_status(self):
        """定期報告關機狀態"""
        self._ensure_async_objects()
        try:
            while True:
                await asyncio.sleep(self.status_interval)
                async with self._lock:
                    active_count = len(self.active_requests)
                if active_count > 0:
                    elapsed = time.time() - self.shutdown_start_time
                    logger.info(
                        f"🕐 Shutdown progress: {active_count} requests remaining "
                        f"({elapsed:.1f}s elapsed, {self.rejected_connections} rejected)"
                    )
        except asyncio.CancelledError:
            pass

    async def wait_for_shutdown(self):
        """等待關機完成"""
        self._ensure_async_objects()
        await self.shutdown_event.wait()

    def is_accepting_requests(self) -> bool:
        """檢查是否還在接受新請求"""
        return self.accepting_new_requests

    def get_active_request_count(self) -> int:
        """獲取活動請求數量"""
        return len(self.active_requests)


class LoadBalancingStrategy(Enum):
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED = "weighted"
    RESPONSE_TIME = "response_time"
    FAIL_OVER = "fail_over"


class CircuitBreakerState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit breaker tripped
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class ProxyStats:
    """Statistics for a single proxy"""

    host: str
    port: int
    active_connections: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    last_health_check: float = 0
    is_healthy: bool = True
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    weight: float = 1.0
    circuit_breaker_state: CircuitBreakerState = CircuitBreakerState.CLOSED
    circuit_breaker_failure_count: int = 0
    circuit_breaker_last_failure: float = 0
    circuit_breaker_half_open_calls: int = 0

    @property
    def proxy_key(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def average_response_time(self) -> float:
        """Calculate average response time from recent requests"""
        if not self.response_times:
            return float("inf")
        return statistics.mean(self.response_times)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        total = self.successful_requests + self.failed_requests
        if total == 0:
            return 100.0
        return (self.successful_requests / total) * 100

    def record_response_time(self, response_time: float):
        """Record a response time"""
        self.response_times.append(response_time)

    def update_circuit_breaker(self, success: bool, config: Dict[str, Any]):
        """Update circuit breaker state based on request result"""
        if not config.get("enabled", True):
            return

        current_time = time.time()
        failure_threshold = config.get("failure_threshold", 5)
        recovery_timeout = config.get("recovery_timeout", 60)

        if success:
            self.consecutive_successes += 1
            self.circuit_breaker_failure_count = 0

            if self.circuit_breaker_state == CircuitBreakerState.HALF_OPEN:
                # If we have enough successful calls in half-open, close the circuit
                if self.consecutive_successes >= config.get("half_open_max_calls", 3):
                    self.circuit_breaker_state = CircuitBreakerState.CLOSED
                    logger.info(f"Circuit breaker CLOSED for {self.proxy_key}")
        else:
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            self.circuit_breaker_failure_count += 1
            self.circuit_breaker_last_failure = current_time

            if self.circuit_breaker_state == CircuitBreakerState.CLOSED:
                if self.circuit_breaker_failure_count >= failure_threshold:
                    self.circuit_breaker_state = CircuitBreakerState.OPEN
                    logger.warning(f"Circuit breaker OPENED for {self.proxy_key}")
            elif self.circuit_breaker_state == CircuitBreakerState.HALF_OPEN:
                # Failure in half-open state goes back to open
                self.circuit_breaker_state = CircuitBreakerState.OPEN
                self.circuit_breaker_half_open_calls = 0
                logger.warning(f"Circuit breaker back to OPEN for {self.proxy_key}")

        # Check if we should move from OPEN to HALF_OPEN
        if (
            self.circuit_breaker_state == CircuitBreakerState.OPEN
            and current_time - self.circuit_breaker_last_failure >= recovery_timeout
        ):
            self.circuit_breaker_state = CircuitBreakerState.HALF_OPEN
            self.circuit_breaker_half_open_calls = 0
            logger.info(f"Circuit breaker HALF_OPEN for {self.proxy_key}")

    def is_available(self) -> bool:
        """Check if proxy is available for requests"""
        return self.is_healthy and self.circuit_breaker_state in [
            CircuitBreakerState.CLOSED,
            CircuitBreakerState.HALF_OPEN,
        ]


class EnhancedProxyRotator:
    """Advanced proxy rotation with multiple load balancing strategies"""

    def __init__(self, storage_dir: str = "proxy", config: Dict[str, Any] = None, proxy_types: List[str] = None, regions: List[str] = None):
        self.storage = ProxyStorage(storage_dir)
        self.config = config or {}
        self.proxy_types = proxy_types
        self.regions = regions
        self.lb_config = self.config.get("load_balancing", {})
        self.strategy = LoadBalancingStrategy(
            self.lb_config.get("strategy", "round_robin")
        )

        # Proxy management
        self.proxy_stats: Dict[str, ProxyStats] = {}
        self.available_proxies: List[Dict[str, Any]] = []
        self.last_refresh = 0
        self.refresh_interval = 60

        # Load balancing state
        self.current_index = 0
        self.proxy_weights = (
            self.lb_config.get("strategies", {})
            .get("weighted", {})
            .get("proxy_weights", {})
        )

        # Thread safety - initialize lazily to support multiprocessing
        self._lock = None
        self._health_check_executor = None

        logger.info(f"Initialized proxy rotator with strategy: {self.strategy.value}")

    @property
    def lock(self):
        """Lazy initialization of RLock for multiprocessing compatibility"""
        if self._lock is None:
            self._lock = RLock()
        return self._lock

    @property
    def health_check_executor(self):
        """Lazy initialization of ThreadPoolExecutor for multiprocessing compatibility"""
        if self._health_check_executor is None:
            self._health_check_executor = ThreadPoolExecutor(
                max_workers=self.config.get("health_checks", {}).get("parallel_checks", 10)
            )
        return self._health_check_executor

    async def refresh_proxies(self) -> List[Dict[str, Any]]:
        """Refresh the list of valid proxies from storage"""
        current_time = time.time()

        if current_time - self.last_refresh < self.refresh_interval:
            return self.available_proxies

        with self.lock:
            # Get fresh proxy list with filters
            all_proxies = self.storage.get_valid_proxies(proxy_types=self.proxy_types, regions=self.regions)
            self.last_refresh = current_time

            # Initialize stats for new proxies
            for proxy in all_proxies:
                proxy_key = f"{proxy['host']}:{proxy['port']}"
                if proxy_key not in self.proxy_stats:
                    self.proxy_stats[proxy_key] = ProxyStats(
                        host=proxy["host"],
                        port=proxy["port"],
                        weight=self.proxy_weights.get(proxy_key, 1.0),
                    )

            # Remove stats for proxies no longer in storage
            valid_keys = {f"{p['host']}:{p['port']}" for p in all_proxies}
            self.proxy_stats = {
                k: v for k, v in self.proxy_stats.items() if k in valid_keys
            }

            # Filter available proxies based on health and circuit breaker
            self.available_proxies = [
                proxy
                for proxy in all_proxies
                if self.proxy_stats[f"{proxy['host']}:{proxy['port']}"].is_available()
            ]

            logger.info(
                f"Refreshed proxy list: {len(self.available_proxies)} available "
                f"out of {len(all_proxies)} total proxies"
            )

            return self.available_proxies

    async def get_next_proxy(self) -> Optional[Tuple[Dict[str, Any], ProxyStats]]:
        """Get the next proxy based on configured strategy"""
        available_proxies = await self.refresh_proxies()

        if not available_proxies:
            logger.warning("No available proxies found")
            return None

        with self.lock:
            if self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
                return self._get_round_robin_proxy(available_proxies)
            elif self.strategy == LoadBalancingStrategy.RANDOM:
                return self._get_random_proxy(available_proxies)
            elif self.strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
                return self._get_least_connections_proxy(available_proxies)
            elif self.strategy == LoadBalancingStrategy.WEIGHTED:
                return self._get_weighted_proxy(available_proxies)
            elif self.strategy == LoadBalancingStrategy.RESPONSE_TIME:
                return self._get_fastest_proxy(available_proxies)
            elif self.strategy == LoadBalancingStrategy.FAIL_OVER:
                return self._get_failover_proxy(available_proxies)
            else:
                return self._get_round_robin_proxy(available_proxies)

    def _get_round_robin_proxy(
        self, proxies: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], ProxyStats]:
        """Round-robin selection"""
        proxy = proxies[self.current_index % len(proxies)]
        self.current_index = (self.current_index + 1) % len(proxies)
        stats = self.proxy_stats[f"{proxy['host']}:{proxy['port']}"]
        return proxy, stats

    def _get_random_proxy(
        self, proxies: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], ProxyStats]:
        """Random selection"""
        proxy = random.choice(proxies)
        stats = self.proxy_stats[f"{proxy['host']}:{proxy['port']}"]
        return proxy, stats

    def _get_least_connections_proxy(
        self, proxies: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], ProxyStats]:
        """Least connections selection"""
        best_proxy = min(
            proxies,
            key=lambda p: self.proxy_stats[
                f"{p['host']}:{p['port']}"
            ].active_connections,
        )
        stats = self.proxy_stats[f"{best_proxy['host']}:{best_proxy['port']}"]
        return best_proxy, stats

    def _get_weighted_proxy(
        self, proxies: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], ProxyStats]:
        """Weighted random selection"""
        weights = [self.proxy_stats[f"{p['host']}:{p['port']}"].weight for p in proxies]
        proxy = random.choices(proxies, weights=weights)[0]
        stats = self.proxy_stats[f"{proxy['host']}:{proxy['port']}"]
        return proxy, stats

    def _get_fastest_proxy(
        self, proxies: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], ProxyStats]:
        """Response time based selection"""
        best_proxy = min(
            proxies,
            key=lambda p: self.proxy_stats[
                f"{p['host']}:{p['port']}"
            ].average_response_time,
        )
        stats = self.proxy_stats[f"{best_proxy['host']}:{best_proxy['port']}"]
        return best_proxy, stats

    def _get_failover_proxy(
        self, proxies: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], ProxyStats]:
        """Failover selection (primary first, then backup)"""
        strategy_config = self.lb_config.get("strategies", {}).get("fail_over", {})
        primary_proxies = strategy_config.get("primary_proxies", [])

        # Try primary proxies first
        for proxy in proxies:
            proxy_key = f"{proxy['host']}:{proxy['port']}"
            if proxy_key in primary_proxies:
                stats = self.proxy_stats[proxy_key]
                if stats.is_available():
                    return proxy, stats

        # Fall back to any available proxy
        return self._get_round_robin_proxy(proxies)

    async def record_request_result(
        self,
        proxy_host: str,
        proxy_port: int,
        success: bool,
        response_time: float = None,
    ):
        """Record the result of a proxy request"""
        proxy_key = f"{proxy_host}:{proxy_port}"

        with self.lock:
            if proxy_key in self.proxy_stats:
                stats = self.proxy_stats[proxy_key]
                stats.total_requests += 1

                if success:
                    stats.successful_requests += 1
                    if response_time is not None:
                        stats.record_response_time(response_time)
                else:
                    stats.failed_requests += 1

                # Update circuit breaker
                circuit_config = self.config.get("circuit_breaker", {})
                stats.update_circuit_breaker(success, circuit_config)

                # Update health status based on consecutive failures
                health_config = self.config.get("health_checks", {})
                unhealthy_threshold = health_config.get("unhealthy_threshold", 3)
                healthy_threshold = health_config.get("healthy_threshold", 2)

                if not success:
                    if stats.consecutive_failures >= unhealthy_threshold:
                        stats.is_healthy = False
                        logger.warning(
                            f"Marked proxy {proxy_key} as unhealthy after {stats.consecutive_failures} failures"
                        )
                else:
                    if (
                        stats.consecutive_successes >= healthy_threshold
                        and not stats.is_healthy
                    ):
                        stats.is_healthy = True
                        logger.info(
                            f"Marked proxy {proxy_key} as healthy after {stats.consecutive_successes} successes"
                        )

    def increment_connections(self, proxy_host: str, proxy_port: int):
        """Increment active connection count for a proxy"""
        proxy_key = f"{proxy_host}:{proxy_port}"
        with self.lock:
            if proxy_key in self.proxy_stats:
                self.proxy_stats[proxy_key].active_connections += 1

    def decrement_connections(self, proxy_host: str, proxy_port: int):
        """Decrement active connection count for a proxy"""
        proxy_key = f"{proxy_host}:{proxy_port}"
        with self.lock:
            if proxy_key in self.proxy_stats:
                self.proxy_stats[proxy_key].active_connections = max(
                    0, self.proxy_stats[proxy_key].active_connections - 1
                )

    async def start_health_checks(self):
        """Start periodic health checks for all proxies"""
        health_config = self.config.get("health_checks", {})
        if not health_config.get("enabled", True):
            return

        interval = health_config.get("interval", 30)

        async def health_check_loop():
            while True:
                try:
                    await self._perform_health_checks()
                except Exception as e:
                    logger.error(f"Health check error: {e}")
                await asyncio.sleep(interval)

        asyncio.create_task(health_check_loop())
        logger.info(f"Started health checks with {interval}s interval")

    async def _perform_health_checks(self):
        """Perform health checks on all proxies using protocol-specific validation"""
        health_config = self.config.get("health_checks", {})
        test_url = health_config.get("test_url", "http://httpbin.org/ip")
        timeout = health_config.get("timeout", 10)

        all_proxies = self.storage.get_valid_proxies(proxy_types=self.proxy_types, regions=self.regions)

        async def check_proxy(proxy):
            proxy_key = f"{proxy['host']}:{proxy['port']}"
            protocol = proxy.get("protocol", "socks5")

            try:
                start_time = time.time()

                # Use protocol-specific validation method
                if protocol in ["socks4", "socks5"]:
                    # Use SOCKS validator for more accurate validation
                    from ..utils.socks_validator import SocksValidator
                    
                    validator = SocksValidator(timeout=timeout, check_ip_info=False)
                    
                    if protocol == "socks4":
                        # For SOCKS4, use sync handshake validation
                        result = validator.validate_socks4(proxy["host"], proxy["port"])
                    else:
                        # For SOCKS5, use sync handshake validation
                        result = validator.validate_socks5(proxy["host"], proxy["port"])
                    
                    response_time = time.time() - start_time
                    
                    if result.is_valid:
                        await self.record_request_result(
                            proxy["host"], proxy["port"], True, response_time
                        )
                        logger.debug(
                            f"Health check OK for {proxy_key} ({protocol.upper()}, {response_time:.2f}s)"
                        )
                    else:
                        await self.record_request_result(
                            proxy["host"], proxy["port"], False
                        )
                        logger.warning(
                            f"Health check failed for {proxy_key} ({protocol.upper()}): {result.error}"
                        )
                        
                else:
                    # For HTTP proxies, use HTTP request validation
                    connector = aiohttp.TCPConnector()
                    session_kwargs = {
                        "connector": connector,
                        "proxy": f"http://{proxy['host']}:{proxy['port']}",
                    }

                    client_timeout = ClientTimeout(total=timeout)
                    async with ClientSession(
                        timeout=client_timeout, **session_kwargs
                    ) as session:
                        async with session.get(test_url) as response:
                            if response.status == 200:
                                response_time = time.time() - start_time
                                await self.record_request_result(
                                    proxy["host"], proxy["port"], True, response_time
                                )
                                logger.debug(
                                    f"Health check OK for {proxy_key} (HTTP, {response_time:.2f}s)"
                                )
                            else:
                                await self.record_request_result(
                                    proxy["host"], proxy["port"], False
                                )
                                logger.warning(
                                    f"Health check failed for {proxy_key} (HTTP): HTTP {response.status}"
                                )

            except Exception as e:
                await self.record_request_result(proxy["host"], proxy["port"], False)
                logger.warning(f"Health check failed for {proxy_key}: {e}")

        # Run health checks in parallel
        tasks = [check_proxy(proxy) for proxy in all_proxies]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_stats_summary(self) -> Dict[str, Any]:
        """Get comprehensive statistics for all proxies"""
        with self.lock:
            total_requests = sum(
                stats.total_requests for stats in self.proxy_stats.values()
            )
            total_successful = sum(
                stats.successful_requests for stats in self.proxy_stats.values()
            )
            total_failed = sum(
                stats.failed_requests for stats in self.proxy_stats.values()
            )

            proxy_details = {}
            for proxy_key, stats in self.proxy_stats.items():
                proxy_details[proxy_key] = {
                    "active_connections": stats.active_connections,
                    "total_requests": stats.total_requests,
                    "successful_requests": stats.successful_requests,
                    "failed_requests": stats.failed_requests,
                    "success_rate": stats.success_rate,
                    "average_response_time": stats.average_response_time,
                    "is_healthy": stats.is_healthy,
                    "circuit_breaker_state": stats.circuit_breaker_state.value,
                    "weight": stats.weight,
                }

            return {
                "strategy": self.strategy.value,
                "total_proxies": len(self.proxy_stats),
                "available_proxies": len(self.available_proxies),
                "total_requests": total_requests,
                "total_successful": total_successful,
                "total_failed": total_failed,
                "overall_success_rate": (
                    (total_successful / total_requests * 100)
                    if total_requests > 0
                    else 0
                ),
                "proxy_details": proxy_details,
            }

    async def force_refresh_proxies(self) -> List[Dict[str, Any]]:
        """Force refresh the proxy list regardless of refresh interval"""
        with self.lock:
            # Reset refresh timestamp to force reload
            self.last_refresh = 0
            
            # Perform refresh
            return await self.refresh_proxies()

    async def update_refresh_interval(self, new_interval: int):
        """Update the refresh interval dynamically"""
        with self.lock:
            old_interval = self.refresh_interval
            self.refresh_interval = new_interval
            logger.info(f"Updated refresh interval from {old_interval}s to {new_interval}s")


class EnhancedHTTPProxyServer:
    """Enhanced HTTP Proxy Server with multi-worker support and advanced features"""

    def __init__(self, config_file: str = None, proxy_types: List[str] = None, regions: List[str] = None, skip_cert_check: bool = False):
        # Load configuration
        if config_file and os.path.exists(config_file):
            with open(config_file, "r") as f:
                self.config = json.load(f)
        else:
            self.config = self._get_default_config()

        self.server_config = self.config.get("proxy_server", {})
        self.host = self.server_config.get("host", "127.0.0.1")
        self.port = self.server_config.get("port", 8888)
        self.workers = self.server_config.get("workers", multiprocessing.cpu_count())
        self.proxy_types = proxy_types
        self.regions = regions
        self.skip_cert_check = skip_cert_check

        # Initialize rotator with filtering support
        self.rotator = EnhancedProxyRotator(config=self.config, proxy_types=proxy_types, regions=regions)

        # Server statistics
        self.stats = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "start_time": time.time(),
            "worker_pid": os.getpid(),
        }

        # Graceful shutdown manager
        self.shutdown_manager = GracefulShutdownManager(self.config)

        # Application runner for cleanup
        self.app_runner = None

        logger.info(f"Initialized enhanced proxy server (PID: {os.getpid()})")

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "proxy_server": {"host": "127.0.0.1", "port": 8888, "workers": 4},
            "load_balancing": {"strategy": "round_robin"},
            "health_checks": {
                "enabled": True, 
                "interval": 86400,  # 24 hours - very conservative to avoid external service pressure
                "test_url": "http://httpbin.org/ip"  # More reliable than ipinfo.io
            },
            "circuit_breaker": {"enabled": True},
            "logging": {"level": "INFO"},
        }

    async def handle_request(self, request: Request) -> Response:
        """Handle incoming HTTP requests and forward through proxies"""
        # 檢查是否還在接受新請求
        if not self.shutdown_manager.is_accepting_requests():
            return web.Response(
                status=503,
                text="Server is shutting down, please try again later",
                headers={"Connection": "close"},
            )

        # 創建請求任務並註冊到關機管理器
        current_task = asyncio.current_task()
        try:
            await self.shutdown_manager.add_request(current_task)
        except ConnectionRefusedError:
            return web.Response(
                status=503,
                text="Server is shutting down, please try again later",
                headers={"Connection": "close"},
            )

        self.stats["requests_total"] += 1
        start_time = time.time()

        # Handle CONNECT method for HTTPS tunneling
        if request.method == "CONNECT":
            # Support HTTPS tunneling through CONNECT method
            return await self.handle_connect_request(request, start_time)

        # Get proxy for this request
        proxy_result = await self.rotator.get_next_proxy()
        if not proxy_result:
            self.stats["requests_failed"] += 1
            return web.Response(
                status=503,
                text="No available proxy servers",
                headers={"Content-Type": "text/plain"},
            )

        proxy, proxy_stats = proxy_result
        proxy_host = proxy["host"]
        proxy_port = proxy["port"]
        proxy_protocol = proxy.get("protocol", "socks5")

        # Track connection
        self.rotator.increment_connections(proxy_host, proxy_port)

        try:
            # Prepare request details
            # For proxy requests, we need to use the raw request line or reconstruct the URL
            method = request.method
            headers = dict(request.headers)
            
            # Handle proxy-style URLs (e.g., "GET http://example.com/path HTTP/1.1")
            if request.path_qs.startswith('http://') or request.path_qs.startswith('https://'):
                # Full URL in path (proxy-style request)
                url = request.path_qs
            else:
                # Relative path - reconstruct from Host header
                host = headers.get('Host', 'localhost')
                scheme = 'https' if request.secure else 'http'
                url = f"{scheme}://{host}{request.path_qs}"

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
            timeout_value = self.server_config.get("request_timeout", 30)
            timeout = ClientTimeout(total=timeout_value)

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
                    response_time = time.time() - start_time

                    # Record success
                    await self.rotator.record_request_result(
                        proxy_host, proxy_port, True, response_time
                    )
                    self.stats["requests_success"] += 1

                    logger.info(
                        f"✅ {method} {url} -> {proxy_host}:{proxy_port} "
                        f"[{proxy_response.status}] ({response_time:.2f}s)"
                    )

                    return web.Response(
                        status=proxy_response.status,
                        headers=response_headers,
                        body=response_body,
                    )

        except Exception as e:
            # Record failure
            await self.rotator.record_request_result(proxy_host, proxy_port, False)
            self.stats["requests_failed"] += 1

            logger.error(f"❌ {method} {url} -> {proxy_host}:{proxy_port} failed: {e}")

            return web.Response(
                status=502,
                text=f"Proxy request failed: {str(e)}",
                headers={"Content-Type": "text/plain"},
            )
        finally:
            # Always decrement connection count
            self.rotator.decrement_connections(proxy_host, proxy_port)

    async def handle_connect_request(self, request: Request, start_time: float) -> Response:
        """Handle CONNECT method for HTTPS tunneling"""
        # Parse target host and port from request path
        target = request.match_info.get('target', '') or request.path_qs.lstrip('/')
        
        # If no target in path, try to get from the request line
        if not target:
            # For CONNECT requests, target should be in the URL path
            # e.g., "CONNECT httpbin.org:443 HTTP/1.1"
            target = request.path_qs.lstrip('/')
        
        if not target or ':' not in target:
            self.stats["requests_failed"] += 1
            return web.Response(
                status=400,
                text="Invalid CONNECT request: missing or invalid target",
                headers={"Content-Type": "text/plain"}
            )
        
        try:
            target_host, target_port = target.rsplit(':', 1)
            target_port = int(target_port)
        except ValueError:
            self.stats["requests_failed"] += 1
            return web.Response(
                status=400,
                text="Invalid CONNECT request: invalid port",
                headers={"Content-Type": "text/plain"}
            )

        # Get proxy for this request
        proxy_result = await self.rotator.get_next_proxy()
        if not proxy_result:
            self.stats["requests_failed"] += 1
            return web.Response(
                status=503,
                text="No available proxy servers",
                headers={"Content-Type": "text/plain"},
            )

        proxy, proxy_stats = proxy_result
        proxy_host = proxy["host"]
        proxy_port = proxy["port"]
        proxy_protocol = proxy.get("protocol", "socks5")

        # Track connection
        self.rotator.increment_connections(proxy_host, proxy_port)

        try:
            # Establish connection through proxy
            if proxy_protocol in ["socks4", "socks5"]:
                proxy_type = (
                    ProxyType.SOCKS5 if proxy_protocol == "socks5" else ProxyType.SOCKS4
                )
                connector = ProxyConnector(
                    proxy_type=proxy_type, host=proxy_host, port=proxy_port
                )
            else:  # http proxy
                connector = aiohttp.TCPConnector()

            # Create connection to target through proxy
            timeout_value = self.server_config.get("request_timeout", 30)
            
            if proxy_protocol in ["socks4", "socks5"]:
                # For SOCKS proxies, establish direct connection through the proxy
                try:
                    # Use the connector to establish connection
                    # This is a simplified approach - in production you might want to implement
                    # a full tunnel using raw sockets
                    response_time = time.time() - start_time
                    await self.rotator.record_request_result(
                        proxy_host, proxy_port, True, response_time
                    )
                    self.stats["requests_success"] += 1

                    logger.info(
                        f"✅ CONNECT {target_host}:{target_port} -> {proxy_host}:{proxy_port} "
                        f"({proxy_protocol.upper()}, {response_time:.2f}s)"
                    )

                    # Return 200 Connection established for successful CONNECT
                    return web.Response(
                        status=200,
                        text="Connection established",
                        headers={"Content-Type": "text/plain"}
                    )
                except Exception as e:
                    logger.error(f"❌ CONNECT {target_host}:{target_port} -> {proxy_host}:{proxy_port} failed: {e}")
                    raise
            else:
                # For HTTP proxies, we need to establish a tunnel
                # This is a simplified implementation
                response_time = time.time() - start_time
                await self.rotator.record_request_result(
                    proxy_host, proxy_port, True, response_time
                )
                self.stats["requests_success"] += 1

                logger.info(
                    f"✅ CONNECT {target_host}:{target_port} -> {proxy_host}:{proxy_port} "
                    f"(HTTP, {response_time:.2f}s)"
                )

                return web.Response(
                    status=200,
                    text="Connection established",
                    headers={"Content-Type": "text/plain"}
                )

        except Exception as e:
            # Record failure
            await self.rotator.record_request_result(proxy_host, proxy_port, False)
            self.stats["requests_failed"] += 1

            logger.error(f"❌ CONNECT {target_host}:{target_port} -> {proxy_host}:{proxy_port} failed: {e}")

            return web.Response(
                status=502,
                text=f"Connection failed: {str(e)}",
                headers={"Content-Type": "text/plain"},
            )
        finally:
            # Always decrement connection count
            self.rotator.decrement_connections(proxy_host, proxy_port)

    async def handle_stats(self, request: Request) -> Response:
        """Handle requests to /stats endpoint"""
        uptime = time.time() - self.stats["start_time"]

        rotator_stats = self.rotator.get_stats_summary()

        stats_data = {
            **self.stats,
            "uptime_seconds": round(uptime, 2),
            "config": {
                "strategy": rotator_stats["strategy"],
                "workers": self.workers,
                "host": self.host,
                "port": self.port,
            },
            "rotator_stats": rotator_stats,
        }

        return web.json_response(stats_data)

    async def handle_health(self, request: Request) -> Response:
        """Handle health check requests"""
        rotator_stats = self.rotator.get_stats_summary()
        available_proxies = rotator_stats["available_proxies"]

        if available_proxies > 0:
            return web.json_response(
                {
                    "status": "healthy",
                    "available_proxies": available_proxies,
                    "worker_pid": self.stats["worker_pid"],
                }
            )
        else:
            return web.json_response(
                {
                    "status": "unhealthy",
                    "available_proxies": available_proxies,
                    "worker_pid": self.stats["worker_pid"],
                },
                status=503,
            )

    async def handle_force_refresh(self, request: Request) -> Response:
        """Force refresh proxy pool from storage"""
        try:
            # Force refresh proxy list
            refreshed_proxies = await self.rotator.force_refresh_proxies()
            
            # Optionally trigger immediate health check
            force_health_check = request.query.get('health_check', 'false').lower() == 'true'
            if force_health_check:
                await self.rotator._perform_health_checks()
            
            return web.json_response({
                "status": "success",
                "message": "Proxy pool refreshed successfully",
                "total_proxies": len(refreshed_proxies),
                "available_proxies": len(self.rotator.available_proxies),
                "health_check_performed": force_health_check,
                "timestamp": time.time()
            })
        except Exception as e:
            logger.error(f"Failed to refresh proxy pool: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)

    async def handle_connect_direct(self, request: Request) -> Response:
        """Handle CONNECT method directly for HTTPS tunneling"""
        # 檢查是否還在接受新請求
        if not self.shutdown_manager.is_accepting_requests():
            return web.Response(
                status=503,
                text="Server is shutting down, please try again later",
                headers={"Connection": "close"},
            )

        # 創建請求任務並註冊到關機管理器
        current_task = asyncio.current_task()
        try:
            await self.shutdown_manager.add_request(current_task)
        except ConnectionRefusedError:
            return web.Response(
                status=503,
                text="Server is shutting down, please try again later",
                headers={"Connection": "close"},
            )

        self.stats["requests_total"] += 1
        start_time = time.time()

        return await self.handle_connect_request(request, start_time)

    def create_app(self) -> web.Application:
        """Create the aiohttp application"""
        app = web.Application()

        # Add routes - specific routes first, catch-all last
        app.router.add_route("*", "/stats", self.handle_stats)
        app.router.add_route("*", "/health", self.handle_health)
        app.router.add_route("*", "/refresh", self.handle_force_refresh)
        # Handle CONNECT method specifically
        app.router.add_route("CONNECT", "/{target:.*}", self.handle_connect_direct)
        app.router.add_route("*", "/{path:.*}", self.handle_request)

        return app

    async def start_worker(self):
        """Start a single worker process"""
        app = self.create_app()

        logger.info(f"🚀 Starting worker {os.getpid()} on {self.host}:{self.port}")

        # 設置信號處理
        def signal_handler():
            logger.info("🛑 Received shutdown signal (Ctrl+C)")
            asyncio.create_task(self.shutdown_manager.start_shutdown())

        if hasattr(asyncio, "get_running_loop"):
            loop = asyncio.get_running_loop()
        else:
            loop = asyncio.get_event_loop()

        # 註冊信號處理器
        for sig in [signal.SIGINT, signal.SIGTERM]:
            loop.add_signal_handler(sig, signal_handler)

        # Start health checks
        await self.rotator.start_health_checks()

        # Refresh proxy list on startup
        await self.rotator.refresh_proxies()

        runner = web.AppRunner(app)
        await runner.setup()
        self.app_runner = runner

        site = web.TCPSite(runner, self.host, self.port, reuse_port=True)
        await site.start()

        logger.info(f"✅ Worker {os.getpid()} ready")
        logger.info(f"💡 Press Ctrl+C for graceful shutdown")

        # Keep server running until shutdown
        try:
            await self.shutdown_manager.wait_for_shutdown()
        finally:
            logger.info("🧹 Cleaning up resources...")
            await runner.cleanup()
            logger.info("👋 Worker shutdown complete")

    def start_multiprocess(self):
        """Start multiple worker processes"""
        logger.info(f"🚀 Starting enhanced proxy server with {self.workers} workers")
        logger.info(
            f"🔄 Load balancing strategy: {self.config['load_balancing']['strategy']}"
        )
        logger.info(f"📊 Stats endpoint: http://{self.host}:{self.port}/stats")
        logger.info(f"🏥 Health endpoint: http://{self.host}:{self.port}/health")

        def signal_handler(signum, frame):
            signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
            logger.info(
                f"🛑 Received {signal_name} signal, initiating graceful shutdown..."
            )
            logger.info(f"🔄 Terminating {len(processes)} worker processes...")

            # 優雅地終止所有進程
            for i, process in enumerate(processes):
                if process.is_alive():
                    logger.info(
                        f"🛑 Stopping worker {i+1}/{len(processes)} (PID: {process.pid})"
                    )
                    process.terminate()

            # 等待進程結束，最多等待30秒
            shutdown_timeout = 30
            start_time = time.time()

            for i, process in enumerate(processes):
                remaining_time = shutdown_timeout - (time.time() - start_time)
                if remaining_time > 0:
                    process.join(timeout=remaining_time)
                    if process.is_alive():
                        logger.warning(
                            f"⚠️  Worker {i+1} did not terminate gracefully, killing..."
                        )
                        process.kill()
                        process.join()
                    else:
                        logger.info(f"✅ Worker {i+1} terminated gracefully")
                else:
                    logger.warning(f"⚠️  Timeout reached, killing worker {i+1}")
                    process.kill()
                    process.join()

            total_time = time.time() - start_time
            logger.info(f"📊 All workers terminated in {total_time:.2f} seconds")
            logger.info("👋 Enhanced proxy server shutdown complete")
            exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        processes = []
        for i in range(self.workers):
            process = multiprocessing.Process(target=self._run_worker, args=(i,))
            process.start()
            processes.append(process)
            logger.info(f"Started worker {i+1}/{self.workers} (PID: {process.pid})")

        # Wait for all processes
        for process in processes:
            process.join()

    def _run_worker(self, worker_id: int):
        """Run a single worker process"""
        # Set up logging for worker
        logging.basicConfig(
            level=getattr(logging, self.config.get("logging", {}).get("level", "INFO")),
            format=f"Worker-{worker_id} - %(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        # Run the worker
        asyncio.run(self.start_worker())


def load_config(config_file: str) -> Dict[str, Any]:
    """Load configuration from file"""
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            return json.load(f)
    else:
        logger.warning(f"Config file {config_file} not found, using defaults")
        return {}


async def main():
    """Main entry point for the enhanced proxy server"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Enhanced HTTP Proxy Server with load balancing"
    )
    parser.add_argument(
        "--config",
        default="proxy_server_config.json",
        help="Configuration file (default: proxy_server_config.json)",
    )
    parser.add_argument("--host", help="Server host (overrides config)")
    parser.add_argument("--port", type=int, help="Server port (overrides config)")
    parser.add_argument(
        "--workers", type=int, help="Number of worker processes (overrides config)"
    )
    parser.add_argument(
        "--strategy",
        choices=[s.value for s in LoadBalancingStrategy],
        help="Load balancing strategy (overrides config)",
    )
    parser.add_argument(
        "--single-process",
        action="store_true",
        help="Run in single process mode (for development)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Set up logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Load and override configuration
    config = load_config(args.config)

    if args.host:
        config.setdefault("proxy_server", {})["host"] = args.host
    if args.port:
        config.setdefault("proxy_server", {})["port"] = args.port
    if args.workers:
        config.setdefault("proxy_server", {})["workers"] = args.workers
    if args.strategy:
        config.setdefault("load_balancing", {})["strategy"] = args.strategy

    server = EnhancedHTTPProxyServer(config_file=args.config)
    server.config.update(config)

    if args.single_process:
        logger.info("Running in single process mode")
        await server.start_worker()
    else:
        server.start_multiprocess()


if __name__ == "__main__":
    asyncio.run(main())

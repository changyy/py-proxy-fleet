"""
Core proxy fleet management class.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..models.config import FleetConfig
from ..models.proxy import ProxyServer, ProxyStatus
from ..models.task import HttpTask, TaskResult, TaskStatus
from ..utils.output import OutputManager, setup_logging
from ..utils.proxy_utils import (create_proxy_from_dict,
                                 filter_healthy_proxies,
                                 load_proxies_from_file,
                                 make_request_with_proxy,
                                 reset_recent_failures_if_needed,
                                 save_proxies_to_file, test_proxy_health)

logger = logging.getLogger(__name__)


class ProxyFleet:
    """
    Main proxy fleet manager for handling concurrent HTTP requests through multiple proxies.
    """

    def __init__(self, config: Union[FleetConfig, str, None] = None):
        """
        Initialize proxy fleet.

        Args:
            config: Fleet configuration (FleetConfig instance, config file path, or None for defaults)
        """
        # Load configuration
        if isinstance(config, str):
            self.config = FleetConfig.load_from_file(config)
        elif isinstance(config, FleetConfig):
            self.config = config
        else:
            self.config = FleetConfig()

        # Initialize components
        self.proxies: List[ProxyServer] = []
        self.output_manager = OutputManager(
            output_dir=self.config.output_dir, compress=self.config.compress_output
        )

        # Setup logging
        setup_logging(log_file=self.config.log_file, level="INFO")

        # Runtime state
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_requests)

        logger.info("ProxyFleet initialized")

    async def load_proxies(
        self, proxy_data: Union[str, List[Dict[str, Any]], List[ProxyServer]]
    ):
        """
        Load proxy servers from various sources.

        Args:
            proxy_data: Proxy data (file path, list of dicts, or list of ProxyServer instances)
        """
        if isinstance(proxy_data, str):
            # Load from file
            self.proxies = load_proxies_from_file(proxy_data)
        elif isinstance(proxy_data, list):
            if proxy_data and isinstance(proxy_data[0], dict):
                # Load from list of dictionaries
                self.proxies = [create_proxy_from_dict(data) for data in proxy_data]
            elif proxy_data and isinstance(proxy_data[0], ProxyServer):
                # Load from list of ProxyServer instances
                self.proxies = proxy_data.copy()
            else:
                self.proxies = []
        else:
            raise ValueError("Invalid proxy data format")

        logger.info(f"Loaded {len(self.proxies)} proxy servers")

        # Save to config file for persistence
        await self.save_proxies()

    async def save_proxies(self):
        """Save current proxy list to file."""
        save_proxies_to_file(self.proxies, self.config.proxy_file)

    async def start_health_monitoring(self):
        """Start background health monitoring for all proxies."""
        if self._health_check_task and not self._health_check_task.done():
            return

        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Started proxy health monitoring")

    async def stop_health_monitoring(self):
        """Stop background health monitoring."""
        self._running = False

        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped proxy health monitoring")

    async def _health_check_loop(self):
        """Background loop for checking proxy health."""
        while self._running:
            try:
                await self.check_all_proxies_health()
                await asyncio.sleep(self.config.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(30)  # Wait before retrying

    async def check_all_proxies_health(self):
        """Check health of all proxy servers."""
        if not self.proxies:
            return

        logger.info(f"Checking health of {len(self.proxies)} proxies")

        # Reset recent failures if time window has passed
        reset_recent_failures_if_needed(self.proxies)

        # Create semaphore for concurrent health checks
        health_semaphore = asyncio.Semaphore(self.config.max_concurrent_health_checks)

        async def check_single_proxy(proxy: ProxyServer):
            async with health_semaphore:
                try:
                    is_healthy, response_time, error = await test_proxy_health(
                        proxy,
                        self.config.health_check_urls,
                        self.config.health_check_timeout,
                    )

                    if is_healthy:
                        logger.debug(
                            f"Proxy {proxy.host}:{proxy.port} is healthy (response_time: {response_time:.2f}s)"
                        )
                    else:
                        logger.warning(
                            f"Proxy {proxy.host}:{proxy.port} is unhealthy: {error}"
                        )

                except Exception as e:
                    logger.error(
                        f"Failed to check proxy {proxy.host}:{proxy.port}: {e}"
                    )
                    proxy.record_failure()

        # Run health checks concurrently
        tasks = [check_single_proxy(proxy) for proxy in self.proxies]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Save updated proxy states
        await self.save_proxies()

        # Log summary
        healthy_count = sum(1 for p in self.proxies if p.is_healthy)
        logger.info(
            f"Health check complete: {healthy_count}/{len(self.proxies)} proxies healthy"
        )

    def get_healthy_proxies(self) -> List[ProxyServer]:
        """Get list of currently healthy proxies."""
        return filter_healthy_proxies(self.proxies)

    def get_proxy_stats(self) -> Dict[str, Any]:
        """Get proxy usage statistics."""
        if not self.proxies:
            return {}

        healthy_proxies = self.get_healthy_proxies()

        stats = {
            "total_proxies": len(self.proxies),
            "healthy_proxies": len(healthy_proxies),
            "unhealthy_proxies": len(self.proxies) - len(healthy_proxies),
            "proxies": [],
        }

        for proxy in self.proxies:
            proxy_stats = {
                "host": proxy.host,
                "port": proxy.port,
                "status": proxy.status.value,
                "success_count": proxy.success_count,
                "failure_count": proxy.failure_count,
                "recent_failures": proxy.recent_failures,
                "average_response_time": proxy.average_response_time,
                "last_check": (
                    proxy.last_check.isoformat() if proxy.last_check else None
                ),
                "last_success": (
                    proxy.last_success.isoformat() if proxy.last_success else None
                ),
            }
            stats["proxies"].append(proxy_stats)

        return stats

    async def _make_direct_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
        timeout: int = 30,
    ) -> tuple:
        """
        Make HTTP request without proxy (direct connection).

        Args:
            url: Target URL
            method: HTTP method
            headers: Request headers
            data: Request body data
            timeout: Request timeout

        Returns:
            Tuple of (status_code, response_headers, response_data, response_time)
        """
        from datetime import datetime

        import aiohttp

        start_time = datetime.now()

        try:
            # Prepare headers
            request_headers = headers or {}
            if "User-Agent" not in request_headers:
                request_headers["User-Agent"] = "proxy-fleet/1.0"

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:

                async with session.request(
                    method, url, headers=request_headers, data=data
                ) as response:

                    response_time = (datetime.now() - start_time).total_seconds()
                    response_data = await response.read()
                    response_headers = dict(response.headers)

                    return (
                        response.status,
                        response_headers,
                        response_data,
                        response_time,
                    )

        except Exception as e:
            response_time = (datetime.now() - start_time).total_seconds()
            raise Exception(f"Direct request failed: {str(e)}")

    async def execute_task(self, task: HttpTask) -> TaskResult:
        """
        Execute a single HTTP task using available proxies or direct connection.

        Args:
            task: HTTP task to execute

        Returns:
            Task execution result
        """
        result = TaskResult.from_task(task, TaskStatus.PENDING)

        # Get healthy proxies
        healthy_proxies = self.get_healthy_proxies()

        # If no proxies available, try direct connection
        use_direct_connection = len(healthy_proxies) == 0

        result.status = TaskStatus.RUNNING

        # Try each proxy with retries (or direct connection)
        for attempt in range(task.max_retries + 1):
            try:
                result.attempt_count = attempt + 1

                if use_direct_connection:
                    # Make direct request without proxy
                    result.proxy_used = "direct"
                    status_code, headers, data, response_time = (
                        await self._make_direct_request(
                            url=task.url,
                            method=task.method.value,
                            headers=task.headers,
                            data=task.data,
                            timeout=task.timeout,
                        )
                    )
                else:
                    # Select proxy (round-robin for now, could implement other strategies)
                    proxy = healthy_proxies[attempt % len(healthy_proxies)]
                    result.proxy_used = f"{proxy.host}:{proxy.port}"

                    # Make request through proxy
                    status_code, headers, data, response_time = (
                        await make_request_with_proxy(
                            proxy=proxy,
                            url=task.url,
                            method=task.method.value,
                            headers=task.headers,
                            data=task.data,
                            timeout=task.timeout,
                        )
                    )

                # Record successful result
                result.status_code = status_code
                result.response_headers = headers
                result.response_data = data
                result.response_time = response_time
                result.response_size = len(data) if data else 0

                result.mark_completed(TaskStatus.SUCCESS)
                logger.debug(
                    f"Task {task.task_id} completed successfully via {result.proxy_used}"
                )
                break

            except Exception as e:
                error_msg = str(e)
                result.error_message = error_msg
                result.error_type = type(e).__name__

                logger.warning(
                    f"Task {task.task_id} attempt {attempt + 1} failed via {result.proxy_used}: {error_msg}"
                )

                # If this was the last attempt, mark as failed
                if attempt >= task.max_retries:
                    result.mark_completed(TaskStatus.FAILED, error_msg)
                else:
                    # Wait before retry
                    if task.retry_delay > 0:
                        await asyncio.sleep(task.retry_delay)

        return result

    async def execute_tasks(self, tasks: List[HttpTask]) -> List[TaskResult]:
        """
        Execute multiple HTTP tasks concurrently using available proxies.

        Args:
            tasks: List of HTTP tasks to execute

        Returns:
            List of task execution results
        """
        if not tasks:
            return []

        logger.info(f"Executing {len(tasks)} tasks")
        start_time = datetime.now()

        # Execute tasks with concurrency control
        async def execute_with_semaphore(task: HttpTask) -> TaskResult:
            async with self._semaphore:
                result = await self.execute_task(task)

                # Save result to output
                self.output_manager.save_task_result(result)

                # Save response data if configured
                if self.config.save_response_data and result.is_success:
                    self.output_manager.save_response_data(
                        result, self.config.max_response_size
                    )

                return result

        # Run all tasks concurrently
        task_coroutines = [execute_with_semaphore(task) for task in tasks]
        results = await asyncio.gather(*task_coroutines, return_exceptions=True)

        # Handle any exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Create failed result for exception
                failed_result = TaskResult.from_task(tasks[i], TaskStatus.FAILED)
                failed_result.mark_completed(TaskStatus.FAILED, str(result))
                processed_results.append(failed_result)
            else:
                processed_results.append(result)

        end_time = datetime.now()

        # Save summary report
        proxy_stats = self.get_proxy_stats()
        self.output_manager.save_summary_report(
            processed_results, proxy_stats, start_time, end_time
        )

        # Log summary
        successful = sum(1 for r in processed_results if r.is_success)
        logger.info(
            f"Completed {len(tasks)} tasks: {successful} successful, {len(tasks) - successful} failed"
        )

        return processed_results

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start_health_monitoring()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop_health_monitoring()

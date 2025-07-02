"""
Command-line interface for proxy-fleet.
"""

import asyncio
import json
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from ..utils.socks_validator import SocksValidator, ValidationResult

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ProxyStorage:
    """Manage proxy server storage and status with thread-safe file operations"""

    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        self.proxy_file = self.storage_dir / "proxy.json"
        self.log_file = self.storage_dir / "test-proxy-server.log"

        # Thread lock for file operations - initialize lazily for multiprocessing compatibility
        self._file_lock = None

        # Set up log file
        self._setup_proxy_logger()

    @property
    def file_lock(self):
        """Lazy initialization of RLock for multiprocessing compatibility"""
        if self._file_lock is None:
            import threading
            self._file_lock = threading.RLock()
        return self._file_lock

    def _setup_proxy_logger(self):
        """Set up proxy test logging"""
        self.proxy_logger = logging.getLogger("proxy_test")
        self.proxy_logger.setLevel(logging.INFO)

        # Avoid adding duplicate handlers
        if not self.proxy_logger.handlers:
            handler = logging.FileHandler(self.log_file)
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            self.proxy_logger.addHandler(handler)

    def load_proxy_data(self) -> Dict[str, Any]:
        """Load proxy data with thread safety"""
        with self.file_lock:
            if self.proxy_file.exists():
                try:
                    with open(self.proxy_file, "r", encoding="utf-8") as f:
                        return json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Failed to load proxy data: {e}, using empty data")
                    return {"proxies": {}}
            return {"proxies": {}}

    def save_proxy_data(self, data: Dict[str, Any]):
        """Save proxy data with thread safety"""
        with self.file_lock:
            temp_file = self.proxy_file.with_suffix(".tmp")
            try:
                # Write to temporary file first, then rename for atomic operation
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                # Atomic rename operation
                temp_file.replace(self.proxy_file)
            except IOError as e:
                logger.error(f"Failed to save proxy data: {e}")
                # Clean up temporary file if it exists
                if temp_file.exists():
                    temp_file.unlink()

    def update_proxy_status(
        self,
        host: str,
        port: int,
        is_valid: bool,
        ip_info: Optional[Dict[str, Any]] = None,
        proxy_type: str = "socks5",
        request_test_result: Optional[Dict[str, Any]] = None,
    ):
        """Update proxy status with thread safety"""
        with self.file_lock:
            data = self.load_proxy_data()
            proxy_key = f"{host}:{port}"
            current_time = datetime.now().isoformat()

            if proxy_key not in data["proxies"]:
                data["proxies"][proxy_key] = {
                    "host": host,
                    "port": port,
                    "protocol": proxy_type,
                    "first_test_time": current_time,
                    "last_success_time": None,
                    "success_count": 0,
                    "failure_count": 0,
                    "ip_info": None,
                    "request_test_result": None,
                    "is_valid": False,
                }

            proxy_data = data["proxies"][proxy_key]
            proxy_data["last_test_time"] = current_time
            proxy_data["protocol"] = proxy_type
            proxy_data["is_valid"] = is_valid

            if is_valid:
                proxy_data["last_success_time"] = current_time
                proxy_data["success_count"] += 1
                if ip_info:
                    proxy_data["ip_info"] = ip_info
                if request_test_result:
                    proxy_data["request_test_result"] = request_test_result

                self.proxy_logger.info(f"✅ {proxy_key} - Validation SUCCESS")
            else:
                proxy_data["failure_count"] += 1
                # Store failed request test result too
                if request_test_result:
                    proxy_data["request_test_result"] = request_test_result
                self.proxy_logger.info(f"❌ {proxy_key} - Validation FAILED")

            self.save_proxy_data(data)

    def get_valid_proxies(self, 
                          proxy_types: List[str] = None, 
                          regions: List[str] = None) -> List[Dict[str, Any]]:
        """Get list of valid proxies with optional filtering by type and region"""
        data = self.load_proxy_data()
        valid_proxies = []

        # Parse proxy types
        if proxy_types is None:
            proxy_types = ['socks5']
        elif 'all' in proxy_types:
            proxy_types = ['socks5', 'socks4', 'http']

        # Normalize proxy types to lowercase
        proxy_types = [ptype.lower() for ptype in proxy_types]

        # Normalize regions to uppercase
        if regions:
            regions = [region.upper() for region in regions]

        for proxy_key, proxy_data in data["proxies"].items():
            if proxy_data.get("is_valid", False):
                # Check proxy type filter
                proxy_protocol = proxy_data.get("protocol", "socks5").lower()
                if proxy_protocol not in proxy_types:
                    continue

                # Check region filter
                if regions:
                    proxy_region = ""
                    
                    # First try to get region from request_test_result (custom API)
                    request_test = proxy_data.get("request_test_result", {})
                    location_info = request_test.get("location_info")
                    if location_info and location_info.get("location"):
                        proxy_region = location_info["location"].upper()
                    
                    # Fallback to ip_info (from automatic ipinfo.io check)
                    if not proxy_region:
                        ip_info = proxy_data.get("ip_info", {})
                        proxy_region = ip_info.get("country", "").upper() if ip_info else ""
                    
                    if proxy_region not in regions:
                        continue

                valid_proxies.append(proxy_data)

        return valid_proxies

    def clear_failed_tasks(self):
        """Clear failed task records"""
        if self.fail_file.exists():
            self.fail_file.unlink()

    def add_verified_proxy(self, proxy_key: str, proxy_data: Dict[str, Any]):
        """Add a verified proxy to storage"""
        with self.file_lock:
            data = self.load_proxy_data()
            current_time = datetime.now().isoformat()

            data["proxies"][proxy_key] = {
                "host": proxy_data["host"],
                "port": proxy_data["port"],
                "protocol": proxy_data.get("protocol", "socks5"),
                "first_test_time": current_time,
                "last_success_time": current_time,
                "success_count": 1,
                "failure_count": 0,
                "ip_info": proxy_data.get("ip_info"),
                "request_test_result": proxy_data.get("request_test_result"),
                "is_valid": True,
            }

            self.save_proxy_data(data)

    def remove_failed_proxies(self) -> Dict[str, int]:
        """Remove failed proxies from storage and return statistics with thread safety"""
        with self.file_lock:
            data = self.load_proxy_data()
            original_count = len(data["proxies"])

            # Filter out failed proxies, keep only valid ones
            valid_proxies = {}
            removed_count = 0

            for proxy_key, proxy_data in data["proxies"].items():
                if proxy_data.get("is_valid", False):
                    valid_proxies[proxy_key] = proxy_data
                else:
                    removed_count += 1
                    self.proxy_logger.info(f"🗑️  Removed failed proxy: {proxy_key}")

            # Update storage with only valid proxies
            data["proxies"] = valid_proxies
            self.save_proxy_data(data)

            return {
                "original_count": original_count,
                "removed_count": removed_count,
                "remaining_count": len(valid_proxies),
                "total_processed": original_count,
            }


def read_proxy_input(input_source: str) -> List[str]:
    """Read proxy input"""
    if input_source == "-":
        # Read from stdin
        return [line.strip() for line in sys.stdin if line.strip()]
    else:
        # Read from file
        with open(input_source, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]


def parse_proxy_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse proxy line with protocol support"""
    line = line.strip()
    if not line or ":" not in line:
        return None

    try:
        protocol = None
        host_port = line

        # Check for protocol prefix
        if "://" in line:
            protocol_part, host_port = line.split("://", 1)
            protocol = protocol_part.lower()

        # Parse host:port
        if ":" not in host_port:
            return None

        parts = host_port.split(":")
        if len(parts) >= 2:
            host = parts[0].strip()
            port = int(parts[1].strip())

            result = {"host": host, "port": port}
            if protocol:
                result["protocol"] = protocol

            return result
    except (ValueError, IndexError):
        pass

    return None


@click.command()
@click.option(
    "--test-proxy-type",
    type=click.Choice(["socks4", "socks5", "http"], case_sensitive=False),
    default="socks5",
    help="Proxy type (socks4/socks5/http), default is socks5",
)
@click.option(
    "--test-proxy-timeout", default=10, help="Proxy connection timeout in seconds"
)
@click.option(
    "--test-proxy-with-request",
    help='Additional HTTP request validation, e.g., "https://ipinfo.io/json"',
)
@click.option(
    "--test-proxy-server",
    help='Proxy server input source: file path or "-" for stdin input',
)
@click.option(
    "--test-proxy-storage",
    is_flag=True,
    default=False,
    help="Test existing proxy servers in proxy storage (default: off)",
)
@click.option(
    "--proxy-storage",
    default="proxy",
    help="Proxy state storage directory for logging test results and statistics (default: proxy)",
)
@click.option(
    "--list-proxy-types",
    is_flag=True,
    default=False,
    help="List proxy type statistics from storage in JSON format",
)
@click.option(
    "--list-proxy",
    is_flag=True,
    default=False,
    help="List all proxy server status from proxy storage in JSON format",
)
@click.option(
    "--list-proxy-verified",
    is_flag=True,
    default=False,
    help="List only verified/valid proxy servers from proxy storage in JSON format",
)
@click.option(
    "--list-proxy-failed",
    is_flag=True,
    default=False,
    help="List only failed/invalid proxy servers from proxy storage in JSON format",
)
@click.option(
    "--remove-proxy-failed",
    is_flag=True,
    default=False,
    help="Remove all failed/invalid proxy servers from proxy storage",
)
@click.option(
    "--concurrent", default=10, help="Maximum concurrent connections for proxy testing"
)
@click.option("--verbose", "-v", is_flag=True, help="Show verbose output")
@click.option(
    "--start-proxy-server",
    is_flag=True,
    default=False,
    help="Start HTTP proxy server that rotates through verified proxies",
)
@click.option(
    "--enhanced-proxy-server",
    is_flag=True,
    default=False,
    help="Start enhanced HTTP proxy server with advanced load balancing",
)
@click.option(
    "--proxy-server-config",
    default="proxy_server_config.json",
    help="Configuration file for enhanced proxy server (default: proxy_server_config.json)",
)
@click.option(
    "--proxy-server-host",
    default="127.0.0.1",
    help="Proxy server host (default: 127.0.0.1)",
)
@click.option(
    "--proxy-server-port",
    default=8888,
    type=int,
    help="Proxy server port (default: 8888)",
)
@click.option(
    "--proxy-server-workers",
    default=None,
    type=int,
    help="Number of worker processes (default: CPU count)",
)
@click.option(
    "--proxy-server-rotation",
    type=click.Choice(["round-robin", "random"], case_sensitive=False),
    default="round-robin",
    help="Proxy rotation mode for basic server (default: round-robin)",
)
@click.option(
    "--proxy-server-strategy",
    type=click.Choice(
        [
            "round_robin",
            "random",
            "least_connections",
            "weighted",
            "response_time",
            "fail_over",
        ],
        case_sensitive=False,
    ),
    help="Load balancing strategy for enhanced server",
)
@click.option(
    "--single-process",
    is_flag=True,
    default=False,
    help="Run enhanced server in single process mode (for development)",
)
@click.option(
    "--generate-config",
    is_flag=True,
    default=False,
    help="Generate default proxy server configuration file",
)
@click.option(
    "--proxy-server-use-types",
    default="socks5",
    help="Proxy types to use in server: all, socks5, socks4, http (comma-separated, default: socks5)",
)
@click.option(
    "--proxy-server-skip-cert-check",
    is_flag=True,
    default=False,
    help="Skip SSL certificate verification for HTTPS requests (default: off)",
)
@click.option(
    "--proxy-server-use-region",
    default=None,
    help="Filter proxies by region/country codes (comma-separated, e.g., TW,US,JP - default: all regions)",
)
def main(
    test_proxy_type,
    test_proxy_timeout,
    test_proxy_with_request,
    test_proxy_server,
    test_proxy_storage,
    proxy_storage,
    list_proxy,
    list_proxy_verified,
    list_proxy_failed,
    remove_proxy_failed,
    concurrent,
    verbose,
    start_proxy_server,
    enhanced_proxy_server,
    proxy_server_config,
    proxy_server_host,
    proxy_server_port,
    proxy_server_workers,
    proxy_server_rotation,
    proxy_server_strategy,
    single_process,
    generate_config,
    proxy_server_use_types,
    list_proxy_types,
    proxy_server_skip_cert_check,
    proxy_server_use_region,
):
    """
    proxy-fleet: High-performance proxy server management tool

    Main Features:
    1. Validate SOCKS/HTTP proxy servers
    2. Run HTTP proxy server with verified proxy rotation
    3. Enhanced proxy server with intelligent load balancing
    4. Proxy pool management and health monitoring

    Usage Scenarios:

    Scenario 1 - Validate input proxy servers:
    # Validate proxies from file/stdin
    proxy-fleet --test-proxy-server proxies.txt
    cat proxies.txt | proxy-fleet --test-proxy-server -

    Scenario 2 - Validate existing proxy servers in storage:
    # Test existing proxies in storage
    proxy-fleet --test-proxy-storage

    Scenario 3 - List current proxy servers in storage:
    # List all proxy status
    proxy-fleet --list-proxy

    # List only verified/valid proxies
    proxy-fleet --list-proxy-verified

    # List only failed/invalid proxies
    proxy-fleet --list-proxy-failed

    # List proxy type statistics
    proxy-fleet --list-proxy-types

    Scenario 4 - Remove failed proxy servers from storage:
    # Clean up failed/invalid proxies from storage
    proxy-fleet --remove-proxy-failed

    Scenario 5 - Start basic HTTP proxy server:
    # Start proxy server that rotates through verified proxies
    proxy-fleet --start-proxy-server --proxy-server-port 8888

    # Start with random rotation instead of round-robin
    proxy-fleet --start-proxy-server --proxy-server-rotation random

    # Start with specific proxy types
    proxy-fleet --start-proxy-server --proxy-server-use-types socks5,http

    # Start with regional filtering
    proxy-fleet --start-proxy-server --proxy-server-use-region TW,US

    # Start with SSL cert check disabled (useful for SOCKS4)
    proxy-fleet --start-proxy-server --proxy-server-skip-cert-check

    Scenario 9 - Start enhanced HTTP proxy server:
    # Generate default configuration file
    proxy-fleet --generate-config

    # Start enhanced server with intelligent load balancing
    proxy-fleet --enhanced-proxy-server

    # Start with proxy type and region filtering
    proxy-fleet --enhanced-proxy-server --proxy-server-use-types all --proxy-server-use-region TW,JP

    # Start with custom configuration
    proxy-fleet --enhanced-proxy-server --proxy-server-config my_config.json

    # Start with specific strategy and workers
    proxy-fleet --enhanced-proxy-server --proxy-server-strategy least_connections --proxy-server-workers 8

    # Start in single process mode for development
    proxy-fleet --enhanced-proxy-server --single-process
    """

    async def run_proxy_fleet():
        # Set log level
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)

        # Determine running mode
        if generate_config:
            # Mode: Generate configuration file
            await run_generate_config_mode()
        elif enhanced_proxy_server:
            # Mode: Start enhanced HTTP proxy server
            await run_enhanced_proxy_server_mode()
        elif start_proxy_server:
            # Mode: Start basic HTTP proxy server
            await run_proxy_server_mode()
        elif list_proxy_types:
            # List proxy type statistics
            await run_list_proxy_types_mode()
        elif list_proxy:
            # List all proxy status
            await run_list_proxy_mode("all")
        elif list_proxy_verified:
            # List verified proxy status
            await run_list_proxy_mode("verified")
        elif list_proxy_failed:
            # List failed proxy status
            await run_list_proxy_mode("failed")
        elif remove_proxy_failed:
            # Remove failed proxies from storage
            await run_remove_failed_proxy_mode()
        elif test_proxy_server:
            # Mode 1: Validate proxies from input
            await run_proxy_test_mode()
        elif test_proxy_storage:
            # Mode 2: Test existing proxies in storage
            await run_test_storage_mode()
        else:
            click.echo("❌ Please specify a running mode:")
            click.echo("   Configuration mode: --generate-config")
            click.echo("   Enhanced proxy server mode: --enhanced-proxy-server")
            click.echo("   Basic proxy server mode: --start-proxy-server")
            click.echo(
                "   Proxy validation mode: --test-proxy-server <file|-> or --test-proxy-storage"
            )
            click.echo(
                "   Proxy management mode: --list-proxy, --list-proxy-verified, --list-proxy-failed, --list-proxy-types, or --remove-proxy-failed"
            )
            return

    async def run_proxy_test_mode():
        """Run proxy validation mode"""
        storage = ProxyStorage(proxy_storage)

        click.echo("🚀 Starting proxy server validation")
        click.echo("=" * 50)

        # Read proxy input
        try:
            proxy_lines = read_proxy_input(test_proxy_server)
            click.echo(f"📥 Read {len(proxy_lines)} proxy servers")
        except Exception as e:
            click.echo(f"❌ Failed to read proxy input: {e}")
            return

        # Parse proxies
        proxies = []
        for line in proxy_lines:
            proxy = parse_proxy_line(line)
            if proxy:
                proxies.append(proxy)
            else:
                click.echo(f"⚠️  Unable to parse proxy line: {line}")

        if not proxies:
            click.echo("❌ No valid proxy servers found")
            return

        click.echo(
            f"🔍 Starting validation of {len(proxies)} proxy servers (type: {test_proxy_type.upper()})"
        )
        click.echo(f"🔧 Using {concurrent} concurrent connections for validation")

        # Validate proxies
        valid_proxies = await validate_proxies(proxies, storage, concurrent)

        click.echo(f"\n📊 Validation completed")
        click.echo(f"   Valid proxies: {len(valid_proxies)}")
        click.echo(f"   Invalid proxies: {len(proxies) - len(valid_proxies)}")
        click.echo(f"   Results saved to: {proxy_storage}/")

    async def run_list_proxy_mode(filter_type="all"):
        """List proxy status mode with filtering"""
        storage = ProxyStorage(proxy_storage)
        proxy_data = storage.load_proxy_data()

        if filter_type == "verified":
            # Filter only verified/valid proxies
            filtered_proxies = {}
            for proxy_key, proxy_info in proxy_data.get("proxies", {}).items():
                if proxy_info.get("is_valid", False):
                    filtered_proxies[proxy_key] = proxy_info
            proxy_data = {"proxies": filtered_proxies}
        elif filter_type == "failed":
            # Filter only failed/invalid proxies
            filtered_proxies = {}
            for proxy_key, proxy_info in proxy_data.get("proxies", {}).items():
                if not proxy_info.get("is_valid", False):
                    filtered_proxies[proxy_key] = proxy_info
            proxy_data = {"proxies": filtered_proxies}
        # filter_type == 'all' shows all proxies (no filtering needed)

        # Output JSON format to stdout
        print(json.dumps(proxy_data, indent=2, ensure_ascii=False))

    async def run_list_proxy_types_mode():
        """List proxy type statistics mode"""
        storage = ProxyStorage(proxy_storage)
        proxy_data = storage.load_proxy_data()

        # Initialize counters
        stats = {
            "total": 0,
            "socks5": 0,
            "socks4": 0,
            "http": 0,
            "valid_total": 0,
            "valid_socks5": 0,
            "valid_socks4": 0,
            "valid_http": 0,
            "by_region": {}
        }

        # Count proxy types
        for proxy_key, proxy_info in proxy_data.get("proxies", {}).items():
            protocol = proxy_info.get("protocol", "unknown").lower()
            is_valid = proxy_info.get("is_valid", False)
            
            # Get region from IP info
            region = "Unknown"
            ip_info = proxy_info.get("ip_info", {})
            if ip_info:
                region = ip_info.get("country", "Unknown")
                if isinstance(region, str) and len(region) == 2:
                    region = region.upper()

            # Total counts
            stats["total"] += 1
            if protocol == "socks5":
                stats["socks5"] += 1
            elif protocol == "socks4":
                stats["socks4"] += 1
            elif protocol == "http":
                stats["http"] += 1

            # Valid counts
            if is_valid:
                stats["valid_total"] += 1
                if protocol == "socks5":
                    stats["valid_socks5"] += 1
                elif protocol == "socks4":
                    stats["valid_socks4"] += 1
                elif protocol == "http":
                    stats["valid_http"] += 1

            # Region statistics
            if region not in stats["by_region"]:
                stats["by_region"][region] = {
                    "total": 0,
                    "valid": 0,
                    "socks5": 0,
                    "socks4": 0,
                    "http": 0,
                    "valid_socks5": 0,
                    "valid_socks4": 0,
                    "valid_http": 0
                }
            
            region_stats = stats["by_region"][region]
            region_stats["total"] += 1
            region_stats[protocol] += 1
            
            if is_valid:
                region_stats["valid"] += 1
                region_stats[f"valid_{protocol}"] += 1

        # Output JSON format to stdout
        print(json.dumps(stats, indent=2, ensure_ascii=False))

    async def run_remove_failed_proxy_mode():
        """Remove failed proxies from storage mode"""
        storage = ProxyStorage(proxy_storage)

        click.echo("🗑️  Removing failed proxy servers from storage")
        click.echo("=" * 50)

        # Remove failed proxies and get statistics
        removal_stats = storage.remove_failed_proxies()

        click.echo(f"✅ Cleanup completed:")
        click.echo(f"   - Removed failed proxies: {removal_stats['removed_count']}")
        click.echo(f"   - Remaining valid proxies: {removal_stats['remaining_count']}")
        click.echo(f"   - Total processed: {removal_stats['total_processed']}")

        if removal_stats["removed_count"] > 0:
            click.echo(f"📝 Cleanup log saved to: {storage.log_file}")
        else:
            click.echo("ℹ️  No failed proxies found to remove")

    async def run_test_storage_mode():
        """Test existing proxies in storage mode"""
        storage = ProxyStorage(proxy_storage)

        click.echo("🔍 Testing existing proxy servers")
        click.echo("=" * 50)

        # Get all proxies (including valid and invalid ones)
        proxy_data = storage.load_proxy_data()
        all_proxies = []

        for proxy_key, proxy_info in proxy_data.get("proxies", {}).items():
            proxy = {"host": proxy_info["host"], "port": proxy_info["port"]}
            all_proxies.append(proxy)

        if not all_proxies:
            click.echo(f"📭 No proxy servers found in {proxy_storage}/")
            click.echo("   Please add proxies first using --test-proxy-server")
            return

        click.echo(f"📥 Found {len(all_proxies)} existing proxy servers")
        click.echo(f"🔍 Starting re-validation (type: {test_proxy_type.upper()})")
        click.echo(f"🔧 Using {concurrent} concurrent connections for validation")

        # Re-validate all proxies
        valid_proxies = await validate_proxies(all_proxies, storage, concurrent)

        click.echo(f"\n📊 Re-validation completed")
        click.echo(f"   Valid proxies: {len(valid_proxies)}")
        click.echo(f"   Invalid proxies: {len(all_proxies) - len(valid_proxies)}")
        click.echo(f"   Results updated to: {proxy_storage}/")

    async def validate_proxies(proxies, storage, max_concurrent):
        """Validate proxy list"""
        # Import asyncio explicitly to avoid scoping issues
        import asyncio
        
        # Initialize validator - use new server request validation if test URL provided
        if test_proxy_with_request:
            validator = SocksValidator(
                timeout=test_proxy_timeout, 
                check_server_via_request=True,
                request_url=test_proxy_with_request
            )
        else:
            validator = SocksValidator(timeout=test_proxy_timeout)
        valid_proxies = []

        # Use concurrency control to validate proxies
        semaphore = asyncio.Semaphore(max_concurrent)

        # Add debug info for concurrency
        click.echo(f"🔧 Concurrency settings: {max_concurrent} concurrent connections")
        click.echo(
            f"🔧 Creating ThreadPoolExecutor with max_workers={min(max_concurrent, 500)}"
        )

        # Create a larger thread pool to handle high concurrency
        import concurrent.futures

        loop = asyncio.get_event_loop()

        # Track active tasks for interruption handling
        active_tasks = 0
        max_active_tasks = 0
        completed_tasks = 0

        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(max_concurrent, 500)
            ) as executor:
                # Set the custom executor for this event loop
                old_executor = loop._default_executor
                loop.set_default_executor(executor)

                async def validate_single_proxy(proxy):
                    nonlocal active_tasks, max_active_tasks, completed_tasks
                    async with semaphore:
                        active_tasks += 1
                        if active_tasks > max_active_tasks:
                            max_active_tasks = active_tasks

                        host, port = proxy["host"], proxy["port"]

                        try:
                            # Add timeout wrapper for individual proxy validation
                            async def proxy_validation_with_timeout():
                                # Choose validation method based on proxy type
                                if test_proxy_type.lower() == "socks4":
                                    result = await validator.async_validate_socks4(
                                        host, port
                                    )
                                elif test_proxy_type.lower() == "socks5":
                                    result = await validator.async_validate_socks5(
                                        host, port
                                    )
                                elif test_proxy_type.lower() == "http":
                                    result = await validator.async_validate_http(host, port)
                                else:
                                    result = ValidationResult(
                                        is_valid=False, error="Unsupported proxy type"
                                    )
                                return result
                            
                            # Apply timeout to individual proxy validation
                            result = await asyncio.wait_for(
                                proxy_validation_with_timeout(), 
                                timeout=test_proxy_timeout + 5  # Add 5 seconds buffer
                            )

                            if result.is_valid:
                                # Extract server response data if available
                                http_response_data = None
                                if result.ip_info and isinstance(result.ip_info, dict):
                                    # The ip_info now contains the server response data
                                    http_response_data = result.ip_info

                                storage.update_proxy_status(
                                    host,
                                    port,
                                    True,
                                    None,  # No separate ip_info
                                    test_proxy_type.lower(),
                                    http_response_data,
                                )
                                return {
                                    "proxy": proxy,
                                    "result": result,
                                    "http_success": True,
                                }
                            else:
                                storage.update_proxy_status(
                                    host,
                                    port,
                                    False,
                                    proxy_type=test_proxy_type.lower(),
                                )
                                return {
                                    "proxy": proxy,
                                    "result": result,
                                    "http_success": False,
                                }

                        except asyncio.TimeoutError:
                            storage.update_proxy_status(
                                host, port, False, proxy_type=test_proxy_type.lower()
                            )
                            return {"proxy": proxy, "result": None, "error": "Validation timeout"}
                        except Exception as e:
                            storage.update_proxy_status(
                                host, port, False, proxy_type=test_proxy_type.lower()
                            )
                            return {"proxy": proxy, "result": None, "error": str(e)}
                        finally:
                            active_tasks -= 1
                            completed_tasks += 1
                            
                            # Show progress every 100 completed tasks or when finding valid proxies
                            if (completed_tasks % 100 == 0 or 
                                completed_tasks in [1, 10, 50]):
                                
                                progress_pct = (completed_tasks / len(proxies)) * 100
                                click.echo(f"📈 Progress: {completed_tasks}/{len(proxies)} ({progress_pct:.1f}%) - Active: {active_tasks}")

                # Validate all proxies concurrently with overall timeout
                # Set total timeout based on proxy count and timeout per proxy
                total_timeout = min(
                    len(proxies) * test_proxy_timeout / max_concurrent * 2,  # Conservative estimate
                    3600  # Maximum 1 hour
                )
                
                try:
                    validation_results = await asyncio.wait_for(
                        asyncio.gather(
                            *[validate_single_proxy(proxy) for proxy in proxies],
                            return_exceptions=True
                        ),
                        timeout=total_timeout
                    )
                except asyncio.TimeoutError:
                    click.echo(f"\n⚠️  Overall validation timeout reached ({total_timeout:.0f}s)")
                    click.echo(f"📊 Progress: {completed_tasks}/{len(proxies)} tasks processed")
                    validation_results = []  # Empty results on timeout

                # Restore the original executor (only if it was not None)
                if old_executor is not None:
                    loop.set_default_executor(old_executor)

        except KeyboardInterrupt:
            click.echo(f"\n🛑 Graceful shutdown initiated by user (Ctrl+C)")
            click.echo(f"⏳ Please wait for active connections to complete...")
            click.echo(f"📊 Progress: {completed_tasks}/{len(proxies)} tasks processed")
            click.echo(f"🔧 Active concurrent tasks: {active_tasks}")
            click.echo(f"🔧 Peak concurrent tasks: {max_active_tasks}")

            # Give some time for active tasks to complete gracefully
            try:
                # Cancel all pending tasks
                current_task = asyncio.current_task()
                all_tasks = [task for task in asyncio.all_tasks() if task != current_task]
                if all_tasks:
                    for task in all_tasks:
                        task.cancel()
                    
                    # Wait briefly for cancellation
                    await asyncio.sleep(0.5)
                    
                    # Clean up any remaining tasks
                    cancelled_count = sum(1 for task in all_tasks if task.cancelled())
                    click.echo(f"🔧 Cancelled {cancelled_count}/{len(all_tasks)} tasks")
                    
            except Exception as e:
                click.echo(f"⚠️  Cleanup error: {e}")

            click.echo("👋 Goodbye!")
            # Return empty list but don't raise exception to allow graceful exit
            return []
        except Exception as e:
            click.echo(f"❌ Validation error: {e}")
            # Give some time for cleanup
            try:
                await asyncio.sleep(0.1)
            except:
                pass
            return []

        click.echo(f"🔧 Peak concurrent tasks: {max_active_tasks}")

        # Process validation results efficiently
        valid_count = 0
        failed_count = 0
        exception_count = 0
        
        for validation_result in validation_results:
            # Check if this is an exception (due to return_exceptions=True)
            if isinstance(validation_result, Exception):
                failed_count += 1
                exception_count += 1
                continue
                
            # Check if the result is valid
            if not isinstance(validation_result, dict):
                failed_count += 1
                continue
                
            proxy = validation_result.get("proxy")
            result = validation_result.get("result")
            error = validation_result.get("error")
            http_success = validation_result.get("http_success")

            if not proxy:
                failed_count += 1
                continue

            host, port = proxy["host"], proxy["port"]

            if not error and result and result.is_valid:
                valid_proxies.append(proxy)
                valid_count += 1
                # Only show valid proxies to reduce noise
                proxy_type_name = test_proxy_type.upper()
                click.echo(f"✅ {host}:{port} - {proxy_type_name} validation successful")
                
                # Check if we have server response data from the validator
                if result.ip_info and isinstance(result.ip_info, dict):
                    server_response = result.ip_info
                    location_info = server_response.get("location_info")
                    
                    if location_info:
                        location = location_info.get("location", "Unknown")
                        source_field = location_info.get("source_field", "unknown")
                        ip = location_info.get("ip", "Unknown")
                        status_code = server_response.get("status_code", "Unknown")
                        click.echo(f"   🌐 IP: {ip} (Location: {location} from {source_field}) - Server: {status_code}")
                    else:
                        # Show basic server response info
                        status_code = server_response.get("status_code", "Unknown")
                        url = server_response.get("url", "Unknown")
                        click.echo(f"   🌐 Server test: {url} -> {status_code}")
                else:
                    # No additional server test was performed
                    click.echo(f"   ✅ Basic protocol validation only")
            else:
                failed_count += 1
                
        click.echo(f"\n📊 Validation summary:")
        click.echo(f"   ✅ Valid proxies: {valid_count}")
        click.echo(f"   ❌ Failed proxies: {failed_count}")
        if exception_count > 0:
            click.echo(f"   ⚠️  Exception errors: {exception_count}")
        click.echo(f"   📈 Success rate: {(valid_count/len(proxies)*100):.1f}%")

        return valid_proxies

    async def run_proxy_server_mode():
        """Run HTTP proxy server mode"""
        try:
            from ..server.proxy_server import HTTPProxyServer
        except ImportError:
            click.echo("❌ Failed to import proxy server module")
            click.echo("   Please ensure aiohttp and aiohttp-socks are installed")
            return

        click.echo("🚀 Starting HTTP Proxy Server")
        click.echo("=" * 50)

        # Parse proxy types and regions
        proxy_types = [t.strip() for t in proxy_server_use_types.split(',') if t.strip()]
        regions = [r.strip() for r in proxy_server_use_region.split(',') if r.strip()] if proxy_server_use_region else None

        # Check if we have any verified proxies with filters
        storage = ProxyStorage(proxy_storage)
        available_proxies = storage.get_valid_proxies(proxy_types=proxy_types, regions=regions)

        if not available_proxies:
            click.echo(f"❌ No verified proxy servers found in {proxy_storage}/ matching filters")
            click.echo(f"   Filters: types={proxy_types}, regions={regions}")
            click.echo(
                "   Please run proxy validation first: --test-proxy-server <proxy_file>"
            )
            return

        # Show filtering information
        all_proxies = storage.get_valid_proxies()
        click.echo(f"✅ Found {len(available_proxies)} verified proxy servers (filtered from {len(all_proxies)} total)")
        click.echo(f"🔧 Proxy type filter: {', '.join(proxy_types)}")
        if regions:
            click.echo(f"🌍 Region filter: {', '.join(regions)}")
        else:
            click.echo(f"🌍 Region filter: all regions")
        click.echo(f"🔐 Skip SSL cert check: {'enabled' if proxy_server_skip_cert_check else 'disabled'}")
        click.echo(f"🔄 Rotation mode: {proxy_server_rotation}")
        click.echo(f"📡 Server will listen on {proxy_server_host}:{proxy_server_port}")
        click.echo(
            f"📊 Stats endpoint: http://{proxy_server_host}:{proxy_server_port}/stats"
        )
        click.echo(
            f"🏥 Health endpoint: http://{proxy_server_host}:{proxy_server_port}/health"
        )
        click.echo("\n💡 Usage examples:")
        click.echo(
            f"   curl --proxy http://{proxy_server_host}:{proxy_server_port} http://httpbin.org/ip"
        )
        click.echo(
            f"   export http_proxy=http://{proxy_server_host}:{proxy_server_port}"
        )
        click.echo(
            f"   export https_proxy=http://{proxy_server_host}:{proxy_server_port}"
        )

        server = HTTPProxyServer(
            host=proxy_server_host,
            port=proxy_server_port,
            storage_dir=proxy_storage,
            rotation_mode=proxy_server_rotation.lower(),
            proxy_types=proxy_types,
            regions=regions,
            skip_cert_check=proxy_server_skip_cert_check,
        )

        await server.start()

    async def run_generate_config_mode():
        """Generate default configuration file"""
        click.echo("🚀 Generating default proxy server configuration")
        click.echo("=" * 50)

        config_file = proxy_server_config

        if os.path.exists(config_file):
            click.echo(f"⚠️  Configuration file {config_file} already exists")
            if not click.confirm("Do you want to overwrite it?"):
                click.echo("❌ Configuration generation cancelled")
                return

        # Parse proxy types and regions for default config
        proxy_types = [t.strip() for t in proxy_server_use_types.split(',') if t.strip()]
        regions = [r.strip() for r in proxy_server_use_region.split(',') if r.strip()] if proxy_server_use_region else None

        # Default configuration
        default_config = {
            "proxy_server": {
                "host": proxy_server_host,
                "port": proxy_server_port,
                "workers": proxy_server_workers or multiprocessing.cpu_count(),
                "worker_timeout": 30,
                "request_timeout": 30,
                "max_connections": 1000,
                "keepalive_timeout": 60,
                "use_types": proxy_types,
                "use_regions": regions,
                "skip_cert_check": proxy_server_skip_cert_check,
            },
            "load_balancing": {
                "strategy": proxy_server_strategy or "round_robin",
                "strategies": {
                    "round_robin": {
                        "description": "Distribute requests evenly across all proxies"
                    },
                    "random": {"description": "Select a random proxy for each request"},
                    "least_connections": {
                        "description": "Route to proxy with fewest active connections",
                        "track_connections": True,
                    },
                    "weighted": {
                        "description": "Route based on proxy weights",
                        "default_weight": 1,
                        "proxy_weights": {},
                    },
                    "response_time": {
                        "description": "Route to proxy with best average response time",
                        "window_size": 100,
                        "prefer_faster": True,
                    },
                    "fail_over": {
                        "description": "Primary/backup proxy selection",
                        "primary_proxies": [],
                        "backup_proxies": [],
                    },
                },
            },
            "health_checks": {
                "enabled": True,
                "interval": 86400,  # 24 hours
                "timeout": 15,
                "healthy_threshold": 2,
                "unhealthy_threshold": 5,
                "test_url": "http://httpbin.org/ip",
                "max_retries": 3,
                "failure_reset_time": 300,
                "parallel_checks": 5,  # Reduced from 10 to be more conservative
            },
            "circuit_breaker": {
                "enabled": True,
                "failure_threshold": 5,
                "recovery_timeout": 60,
                "half_open_max_calls": 3,
            },
            "rate_limiting": {
                "enabled": False,
                "requests_per_minute": 100,
                "burst_size": 20,
            },
            "logging": {
                "level": "DEBUG" if verbose else "INFO",
                "file": "proxy_server.log",
                "max_size": "10MB",
                "backup_count": 5,
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
            "monitoring": {
                "metrics_enabled": True,
                "stats_retention": 3600,
                "detailed_timing": False,
            },
        }

        try:
            with open(config_file, "w") as f:
                json.dump(default_config, f, indent=2)

            click.echo(f"✅ Configuration file generated: {config_file}")
            click.echo(f"🔧 Default settings:")
            click.echo(f"   Strategy: {default_config['load_balancing']['strategy']}")
            click.echo(f"   Workers: {default_config['proxy_server']['workers']}")
            click.echo(f"   Host: {default_config['proxy_server']['host']}")
            click.echo(f"   Port: {default_config['proxy_server']['port']}")
            click.echo(
                f"   Health checks: {'enabled' if default_config['health_checks']['enabled'] else 'disabled'}"
            )
            click.echo(
                f"   Circuit breaker: {'enabled' if default_config['circuit_breaker']['enabled'] else 'disabled'}"
            )
            click.echo("\n💡 Usage:")
            click.echo(
                f"   proxy-fleet --enhanced-proxy-server --proxy-server-config {config_file}"
            )

        except Exception as e:
            click.echo(f"❌ Failed to generate configuration file: {e}")

    async def run_enhanced_proxy_server_mode():
        """Run enhanced HTTP proxy server mode"""
        try:
            import multiprocessing
            import os

            from ..server.enhanced_proxy_server import EnhancedHTTPProxyServer
        except ImportError as e:
            click.echo("❌ Failed to import enhanced proxy server module")
            click.echo(f"   Error: {e}")
            click.echo("   Please ensure all required dependencies are installed:")
            click.echo("   pip install aiohttp aiohttp-socks")
            return

        click.echo("🚀 Starting Enhanced HTTP Proxy Server")
        click.echo("=" * 50)

        # Parse proxy types and regions
        proxy_types = [t.strip() for t in proxy_server_use_types.split(',') if t.strip()]
        regions = [r.strip() for r in proxy_server_use_region.split(',') if r.strip()] if proxy_server_use_region else None

        # Check if we have any verified proxies with filters
        storage = ProxyStorage(proxy_storage)
        available_proxies = storage.get_valid_proxies(proxy_types=proxy_types, regions=regions)

        if not available_proxies:
            click.echo(f"❌ No verified proxy servers found in {proxy_storage}/ matching filters")
            click.echo(f"   Filters: types={proxy_types}, regions={regions}")
            click.echo(
                "   Please run proxy validation first: --test-proxy-server <proxy_file>"
            )
            return

        # Show filtering information
        all_proxies = storage.get_valid_proxies()
        click.echo(f"✅ Found {len(available_proxies)} verified proxy servers (filtered from {len(all_proxies)} total)")
        click.echo(f"🔧 Proxy type filter: {', '.join(proxy_types)}")
        if regions:
            click.echo(f"🌍 Region filter: {', '.join(regions)}")
        else:
            click.echo(f"🌍 Region filter: all regions")
        click.echo(f"🔐 Skip SSL cert check: {'enabled' if proxy_server_skip_cert_check else 'disabled'}")

        # Load or check configuration
        if not os.path.exists(proxy_server_config):
            click.echo(f"⚠️  Configuration file {proxy_server_config} not found")
            click.echo("   Generating default configuration...")
            await run_generate_config_mode()

        try:
            with open(proxy_server_config, "r") as f:
                config = json.load(f)
        except Exception as e:
            click.echo(f"❌ Failed to load configuration file: {e}")
            return

        # Override config with command line arguments
        if proxy_server_host != "127.0.0.1":
            config.setdefault("proxy_server", {})["host"] = proxy_server_host
        if proxy_server_port != 8888:
            config.setdefault("proxy_server", {})["port"] = proxy_server_port
        if proxy_server_workers:
            config.setdefault("proxy_server", {})["workers"] = proxy_server_workers
        if proxy_server_strategy:
            config.setdefault("load_balancing", {})["strategy"] = proxy_server_strategy
        if verbose:
            config.setdefault("logging", {})["level"] = "DEBUG"
        
        # Add new proxy filtering and SSL configuration
        config.setdefault("proxy_server", {})["use_types"] = proxy_types
        config.setdefault("proxy_server", {})["use_regions"] = regions
        config.setdefault("proxy_server", {})["skip_cert_check"] = proxy_server_skip_cert_check

        # Display configuration summary
        server_config = config.get("proxy_server", {})
        lb_config = config.get("load_balancing", {})
        health_config = config.get("health_checks", {})

        click.echo(f"🔧 Configuration:")
        click.echo(
            f"   Load balancing strategy: {lb_config.get('strategy', 'round_robin')}"
        )
        click.echo(
            f"   Workers: {server_config.get('workers', multiprocessing.cpu_count())}"
        )
        click.echo(f"   Host: {server_config.get('host', '127.0.0.1')}")
        click.echo(f"   Port: {server_config.get('port', 8888)}")
        click.echo(
            f"   Health checks: {'enabled' if health_config.get('enabled', True) else 'disabled'}"
        )
        click.echo(
            f"   Circuit breaker: {'enabled' if config.get('circuit_breaker', {}).get('enabled', True) else 'disabled'}"
        )
        click.echo(f"   Single process mode: {'yes' if single_process else 'no'}")

        host = server_config.get("host", "127.0.0.1")
        port = server_config.get("port", 8888)

        click.echo(f"📡 Server endpoints:")
        click.echo(f"   Proxy: http://{host}:{port}")
        click.echo(f"   Stats: http://{host}:{port}/stats")
        click.echo(f"   Health: http://{host}:{port}/health")

        click.echo("\n💡 Usage examples:")
        click.echo(f"   curl --proxy http://{host}:{port} http://httpbin.org/ip")
        click.echo(f"   export http_proxy=http://{host}:{port}")
        click.echo(f"   export https_proxy=http://{host}:{port}")

        # Create and start server with filtering support
        server = EnhancedHTTPProxyServer(
            config_file=proxy_server_config, 
            proxy_types=proxy_types, 
            regions=regions, 
            skip_cert_check=proxy_server_skip_cert_check
        )
        # Override configuration from command line args
        server.config = config
        server.server_config = server_config
        server.host = host
        server.port = port
        server.workers = server_config.get("workers", multiprocessing.cpu_count())

        if single_process:
            click.echo("\n🔧 Running in single process mode (development)")
            await server.start_worker()
        else:
            click.echo(f"\n🚀 Starting {server.workers} worker processes...")
            server.start_multiprocess()

    # Add import for multiprocessing and os at the top level
    import multiprocessing
    import os

    try:
        asyncio.run(run_proxy_fleet())
    except KeyboardInterrupt:
        click.echo("\n🛑 Graceful shutdown initiated by user (Ctrl+C)")
        click.echo("⏳ Please wait for active connections to complete...")
        click.echo("👋 Goodbye!")
        sys.exit(130)  # Standard exit code for SIGINT


if __name__ == "__main__":
    main()

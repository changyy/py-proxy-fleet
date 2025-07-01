"""
Command-line interface for proxy-fleet.
"""

import asyncio
import json
import click
import sys
import logging
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..utils.socks_validator import SocksValidator, ValidationResult


# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ProxyStorage:
    """Manage proxy server storage and status with thread-safe file operations"""
    
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        self.proxy_file = self.storage_dir / "proxy.json"
        self.log_file = self.storage_dir / "test-proxy-server.log"
        
        # Thread lock for file operations
        self._file_lock = threading.RLock()
        
        # Set up log file
        self._setup_proxy_logger()
    
    def _setup_proxy_logger(self):
        """Set up proxy test logging"""
        self.proxy_logger = logging.getLogger('proxy_test')
        self.proxy_logger.setLevel(logging.INFO)
        
        # Avoid adding duplicate handlers
        if not self.proxy_logger.handlers:
            handler = logging.FileHandler(self.log_file)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.proxy_logger.addHandler(handler)
    
    def load_proxy_data(self) -> Dict[str, Any]:
        """Load proxy data with thread safety"""
        with self._file_lock:
            if self.proxy_file.exists():
                try:
                    with open(self.proxy_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Failed to load proxy data: {e}, using empty data")
                    return {"proxies": {}}
            return {"proxies": {}}
    
    def save_proxy_data(self, data: Dict[str, Any]):
        """Save proxy data with thread safety"""
        with self._file_lock:
            temp_file = self.proxy_file.with_suffix('.tmp')
            try:
                # Write to temporary file first, then rename for atomic operation
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                # Atomic rename operation
                temp_file.replace(self.proxy_file)
            except IOError as e:
                logger.error(f"Failed to save proxy data: {e}")
                # Clean up temporary file if it exists
                if temp_file.exists():
                    temp_file.unlink()
    
    def update_proxy_status(self, host: str, port: int, is_valid: bool, 
                          ip_info: Optional[Dict[str, Any]] = None, proxy_type: str = 'socks5', 
                          request_test_result: Optional[Dict[str, Any]] = None):
        """Update proxy status with thread safety"""
        with self._file_lock:
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
                    "is_valid": False
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
    
    def get_valid_proxies(self) -> List[Dict[str, Any]]:
        """Get list of valid proxies"""
        data = self.load_proxy_data()
        valid_proxies = []
        
        for proxy_key, proxy_data in data["proxies"].items():
            if proxy_data.get("is_valid", False):
                valid_proxies.append(proxy_data)
        
        return valid_proxies
    
    def clear_failed_tasks(self):
        """Clear failed task records"""
        if self.fail_file.exists():
            self.fail_file.unlink()
    
    def remove_failed_proxies(self) -> Dict[str, int]:
        """Remove failed proxies from storage and return statistics with thread safety"""
        with self._file_lock:
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
                "total_processed": original_count
            }


class TaskProcessor:
    """Process task requests"""
    
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.done_file = self.output_dir / "done.json"
        self.fail_file = self.output_dir / "fail.json"
    
    def save_result(self, task: Dict[str, Any], response: Dict[str, Any], is_success: bool):
        """Save task result"""
        result = {
            "id": task.get("id"),
            "request": {
                "url": task.get("url"),
                "headers": task.get("headers", [])
            },
            "response": response
        }
        
        target_file = self.done_file if is_success else self.fail_file
        
        # Load existing results
        results = []
        if target_file.exists():
            with open(target_file, 'r', encoding='utf-8') as f:
                results = json.load(f)
        
        results.append(result)
        
        # Save results
        with open(target_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    
    def get_failed_tasks(self) -> List[Dict[str, Any]]:
        """Get list of failed tasks"""
        if not self.fail_file.exists():
            return []
        
        with open(self.fail_file, 'r', encoding='utf-8') as f:
            failed_results = json.load(f)
        
        # Extract original task information
        failed_tasks = []
        for result in failed_results:
            task = {
                "id": result.get("id"),
                "url": result["request"]["url"],
                "headers": result["request"]["headers"],
                "method": result["request"].get("method", "GET")
            }
            failed_tasks.append(task)
        
        return failed_tasks
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """Get task statistics"""
        done_count = 0
        error_count = 0
        
        if self.done_file.exists():
            with open(self.done_file, 'r', encoding='utf-8') as f:
                done_results = json.load(f)
                done_count = len(done_results)
        
        if self.fail_file.exists():
            with open(self.fail_file, 'r', encoding='utf-8') as f:
                fail_results = json.load(f)
                error_count = len(fail_results)
        
        # Get last update time
        updated = None
        for file_path in [self.done_file, self.fail_file]:
            if file_path.exists():
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if updated is None or file_time > updated:
                    updated = file_time
        
        return {
            "updated": updated.isoformat() if updated else None,
            "total_tasks": done_count + error_count,
            "tasks_done": done_count,
            "tasks_error": error_count
        }
    
    def clear_failed_tasks(self):
        """Clear failed task records"""
        if self.fail_file.exists():
            self.fail_file.unlink()


def read_proxy_input(input_source: str) -> List[str]:
    """Read proxy input"""
    if input_source == "-":
        # Read from stdin
        return [line.strip() for line in sys.stdin if line.strip()]
    else:
        # Read from file
        with open(input_source, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]


def parse_proxy_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse proxy line"""
    if ':' not in line:
        return None
    
    try:
        parts = line.split(':')
        if len(parts) >= 2:
            host = parts[0].strip()
            port = int(parts[1].strip())
            return {"host": host, "port": port}
    except (ValueError, IndexError):
        pass
    
    return None


@click.command()
@click.option('--test-proxy-type', 
              type=click.Choice(['socks4', 'socks5', 'http'], case_sensitive=False),
              default='socks5',
              help='Proxy type (socks4/socks5/http), default is socks5')
@click.option('--test-proxy-timeout', default=10, 
              help='Proxy connection timeout in seconds')
@click.option('--test-proxy-with-request', 
              help='Additional HTTP request validation, e.g., "https://ipinfo.io/json"')
@click.option('--test-proxy-server',
              help='Proxy server input source: file path or "-" for stdin input')
@click.option('--test-proxy-storage', is_flag=True, default=False,
              help='Test existing proxy servers in proxy storage (default: off)')
@click.option('--proxy-storage', default='proxy',
              help='Proxy state storage directory for logging test results and statistics (default: proxy)')
@click.option('--list-proxy', is_flag=True, default=False,
              help='List all proxy server status from proxy storage in JSON format')
@click.option('--list-proxy-verified', is_flag=True, default=False,
              help='List only verified/valid proxy servers from proxy storage in JSON format')
@click.option('--list-proxy-failed', is_flag=True, default=False,
              help='List only failed/invalid proxy servers from proxy storage in JSON format')
@click.option('--remove-proxy-failed', is_flag=True, default=False,
              help='Remove all failed/invalid proxy servers from proxy storage')
@click.option('--list-task-result', is_flag=True, default=False,
              help='Display task execution result statistics in JSON format')
@click.option('--task-input',
              help='Task input file in JSON format or "-" to read from stdin, containing HTTP request list to execute')
@click.option('--task-retry', is_flag=True, default=False,
              help='Retry failed tasks')
@click.option('--task-output-dir', default='output',
              help='Task output directory for storing done.json and fail.json (default: output)')
@click.option('--concurrent', default=10, 
              help='Maximum concurrent connections for proxy testing and task execution')
@click.option('--verbose', '-v', is_flag=True, help='Show verbose output')
def main(test_proxy_type, test_proxy_timeout, test_proxy_with_request, 
         test_proxy_server, test_proxy_storage, proxy_storage, list_proxy, list_proxy_verified, list_proxy_failed, remove_proxy_failed, list_task_result,
         task_input, task_retry, task_output_dir, 
         concurrent, verbose):
    """
    proxy-fleet: High-performance proxy server management tool
    
    Main Features:
    1. Validate SOCKS/HTTP proxy servers
    2. Execute HTTP request tasks
    3. Log proxy status and usage statistics
    
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
    
    Scenario 4 - Remove failed proxy servers from storage:
    # Clean up failed/invalid proxies from storage
    proxy-fleet --remove-proxy-failed
    
    Scenario 5 - Execute HTTP requests through proxy servers:
    # Execute new tasks via proxy servers
    proxy-fleet --task-input tasks.json
    cat tasks.json | proxy-fleet --task-input -
    
    Scenario 6 - Retry failed tasks:
    # Retry failed tasks  
    proxy-fleet --task-retry
    
    Scenario 7 - List current task results:
    # Check task result statistics
    proxy-fleet --list-task-result
    """
    
    async def run_proxy_fleet():
        # Set log level
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        
        # Determine running mode
        if list_proxy:
            # List all proxy status
            await run_list_proxy_mode('all')
        elif list_proxy_verified:
            # List verified proxy status
            await run_list_proxy_mode('verified')
        elif list_proxy_failed:
            # List failed proxy status
            await run_list_proxy_mode('failed')
        elif remove_proxy_failed:
            # Remove failed proxies from storage
            await run_remove_failed_proxy_mode()
        elif list_task_result:
            # Display task result statistics
            await run_list_task_result_mode()
        elif test_proxy_server:
            # Mode 1: Validate proxies from input
            await run_proxy_test_mode()
        elif test_proxy_storage:
            # Mode 2: Test existing proxies in storage
            await run_test_storage_mode()
        elif task_retry:
            # Mode 3: Retry failed tasks
            await run_task_retry_mode()
        elif task_input:
            # Mode 4: Execute new tasks
            await run_task_execution_mode()
        else:
            click.echo("❌ Please specify a running mode:")
            click.echo("   Proxy validation mode: --test-proxy-server <file|-> or --test-proxy-storage")
            click.echo("   Proxy management mode: --list-proxy, --list-proxy-verified, --list-proxy-failed, or --remove-proxy-failed")
            click.echo("   Task execution mode: --task-input <file|-> or --task-retry")
            click.echo("   Task statistics mode: --list-task-result")
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
        
        click.echo(f"🔍 Starting validation of {len(proxies)} proxy servers (type: {test_proxy_type.upper()})")
        
        # Validate proxies
        valid_proxies = await validate_proxies(proxies, storage)
        
        click.echo(f"\n📊 Validation completed")
        click.echo(f"   Valid proxies: {len(valid_proxies)}")
        click.echo(f"   Invalid proxies: {len(proxies) - len(valid_proxies)}")
        click.echo(f"   Results saved to: {proxy_storage}/")
    
    async def run_task_execution_mode():
        """Run task execution mode"""
        storage = ProxyStorage(proxy_storage)
        
        click.echo("🎯 Starting task execution mode")
        click.echo("=" * 50)
        
        # Check if proxies are available
        available_proxies = storage.get_valid_proxies()
        
        if not available_proxies:
            click.echo(f"❌ No available proxy servers found in {proxy_storage}/")
            click.echo("   Please run proxy validation first: --test-proxy-server <proxy_file>")
            return
        
        click.echo(f"✅ Found {len(available_proxies)} available proxies")
        
        # Read task input
        try:
            if task_input == "-":
                # Read JSON from stdin
                task_data = sys.stdin.read()
                tasks = json.loads(task_data)
            else:
                # Read from file
                with open(task_input, 'r', encoding='utf-8') as f:
                    tasks = json.load(f)
            
            click.echo(f"📋 Loaded {len(tasks)} tasks")
        except Exception as e:
            click.echo(f"❌ Failed to read task input: {e}")
            return
        
        # Execute tasks
        await execute_tasks(tasks, available_proxies)
        click.echo(f"✅ Task execution completed, results saved to {task_output_dir}/")
    
    async def run_list_proxy_mode(filter_type='all'):
        """List proxy status mode with filtering"""
        storage = ProxyStorage(proxy_storage)
        proxy_data = storage.load_proxy_data()
        
        if filter_type == 'verified':
            # Filter only verified/valid proxies
            filtered_proxies = {}
            for proxy_key, proxy_info in proxy_data.get("proxies", {}).items():
                if proxy_info.get("is_valid", False):
                    filtered_proxies[proxy_key] = proxy_info
            proxy_data = {"proxies": filtered_proxies}
        elif filter_type == 'failed':
            # Filter only failed/invalid proxies
            filtered_proxies = {}
            for proxy_key, proxy_info in proxy_data.get("proxies", {}).items():
                if not proxy_info.get("is_valid", False):
                    filtered_proxies[proxy_key] = proxy_info
            proxy_data = {"proxies": filtered_proxies}
        # filter_type == 'all' shows all proxies (no filtering needed)
        
        # Output JSON format to stdout
        print(json.dumps(proxy_data, indent=2, ensure_ascii=False))
    
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
        
        if removal_stats['removed_count'] > 0:
            click.echo(f"📝 Cleanup log saved to: {storage.log_file}")
        else:
            click.echo("ℹ️  No failed proxies found to remove")
    
    async def run_list_task_result_mode():
        """Display task result statistics mode"""
        processor = TaskProcessor(task_output_dir)
        statistics = processor.get_task_statistics()
        
        # Output JSON format to stdout
        print(json.dumps(statistics, indent=2, ensure_ascii=False))
    
    async def run_test_storage_mode():
        """Test existing proxies in storage mode"""
        storage = ProxyStorage(proxy_storage)
        
        click.echo("🔍 Testing existing proxy servers")
        click.echo("=" * 50)
        
        # Get all proxies (including valid and invalid ones)
        proxy_data = storage.load_proxy_data()
        all_proxies = []
        
        for proxy_key, proxy_info in proxy_data.get("proxies", {}).items():
            proxy = {
                "host": proxy_info["host"],
                "port": proxy_info["port"]
            }
            all_proxies.append(proxy)
        
        if not all_proxies:
            click.echo(f"📭 No proxy servers found in {proxy_storage}/")
            click.echo("   Please add proxies first using --test-proxy-server")
            return
        
        click.echo(f"📥 Found {len(all_proxies)} existing proxy servers")
        click.echo(f"🔍 Starting re-validation (type: {test_proxy_type.upper()})")
        
        # Re-validate all proxies
        valid_proxies = await validate_proxies(all_proxies, storage)
        
        click.echo(f"\n📊 Re-validation completed")
        click.echo(f"   Valid proxies: {len(valid_proxies)}")
        click.echo(f"   Invalid proxies: {len(all_proxies) - len(valid_proxies)}")
        click.echo(f"   Results updated to: {proxy_storage}/")
    
    async def run_task_retry_mode():
        """Retry failed tasks mode"""
        storage = ProxyStorage(proxy_storage)
        processor = TaskProcessor(task_output_dir)
        
        click.echo("🔄 Retrying failed tasks")
        click.echo("=" * 50)
        
        # Check if proxies are available
        available_proxies = storage.get_valid_proxies()
        
        if not available_proxies:
            click.echo(f"❌ No available proxy servers found in {proxy_storage}/")
            click.echo("   Please run proxy validation first: --test-proxy-server <proxy_file>")
            return
        
        # Get failed tasks
        failed_tasks = processor.get_failed_tasks()
        
        if not failed_tasks:
            click.echo(f"✅ No failed tasks found in {task_output_dir}/")
            return
        
        click.echo(f"📋 Found {len(failed_tasks)} failed tasks")
        click.echo(f"🔧 Retrying with {len(available_proxies)} available proxies")
        
        # Clear old failed records
        processor.clear_failed_tasks()
        
        # Re-execute failed tasks
        await execute_tasks(failed_tasks, available_proxies)
        
        click.echo(f"✅ Task retry completed, results updated to {task_output_dir}/")
    
    async def validate_proxies(proxies, storage):
        """Validate proxy list"""
        # Initialize validator
        validator = SocksValidator(timeout=test_proxy_timeout, check_ip_info=True)
        valid_proxies = []
        
        # Use concurrency control to validate proxies
        semaphore = asyncio.Semaphore(concurrent)
        
        async def validate_single_proxy(proxy):
            async with semaphore:
                host, port = proxy["host"], proxy["port"]
                
                try:
                    # Choose validation method based on proxy type
                    if test_proxy_type.lower() == 'socks4':
                        result = await validator.async_validate_socks4(host, port)
                    elif test_proxy_type.lower() == 'socks5':
                        result = await validator.async_validate_socks5(host, port)
                    elif test_proxy_type.lower() == 'http':
                        result = await validator.async_validate_http(host, port)
                    else:
                        result = ValidationResult(is_valid=False, error="Unsupported proxy type")
                    
                    if result.is_valid:
                        # Additional HTTP request validation
                        http_success = True
                        http_response_data = None
                        if test_proxy_with_request:
                            try:
                                import aiohttp
                                from aiohttp_socks import ProxyConnector, ProxyType
                                
                                # Choose connector based on proxy type
                                if test_proxy_type.lower() in ['socks4', 'socks5']:
                                    proxy_type = ProxyType.SOCKS5 if test_proxy_type.lower() == 'socks5' else ProxyType.SOCKS4
                                    connector = ProxyConnector(
                                        proxy_type=proxy_type,
                                        host=host,
                                        port=port
                                    )
                                    session_kwargs = {'connector': connector}
                                else:  # http proxy
                                    connector = aiohttp.TCPConnector()
                                    session_kwargs = {
                                        'connector': connector,
                                        'proxy': f"http://{host}:{port}"
                                    }
                                
                                async with aiohttp.ClientSession(
                                    timeout=aiohttp.ClientTimeout(total=test_proxy_timeout),
                                    **session_kwargs
                                ) as session:
                                    async with session.get(test_proxy_with_request) as response:
                                        response_text = await response.text()
                                        http_success = response.status in [200, 301, 302]
                                        
                                        # Store HTTP request test result
                                        http_response_data = {
                                            "url": test_proxy_with_request,
                                            "status_code": response.status,
                                            "success": http_success,
                                            "response_body": response_text[:500] if response_text else None,  # Limit to 500 chars
                                            "headers": dict(response.headers)
                                        }
                            except Exception as e:
                                http_success = False
                                http_response_data = {
                                    "url": test_proxy_with_request,
                                    "success": False,
                                    "error": str(e)
                                }
                        
                        # If no additional HTTP validation required, or HTTP validation successful, consider proxy valid
                        if not test_proxy_with_request or http_success:
                            storage.update_proxy_status(host, port, True, result.ip_info, test_proxy_type.lower(), http_response_data)
                            return {"proxy": proxy, "result": result, "http_success": http_success}
                        else:
                            storage.update_proxy_status(host, port, False, result.ip_info, test_proxy_type.lower(), http_response_data)
                            return {"proxy": proxy, "result": result, "http_success": http_success}
                    else:
                        storage.update_proxy_status(host, port, False, proxy_type=test_proxy_type.lower())
                        return {"proxy": proxy, "result": result, "http_success": None}
                        
                except Exception as e:
                    storage.update_proxy_status(host, port, False, proxy_type=test_proxy_type.lower())
                    return {"proxy": proxy, "result": None, "error": str(e)}
        
        # Validate all proxies concurrently
        validation_results = await asyncio.gather(*[validate_single_proxy(proxy) for proxy in proxies])
        
        # Process validation results
        for i, validation_result in enumerate(validation_results, 1):
            proxy = validation_result["proxy"]
            result = validation_result.get("result")
            error = validation_result.get("error")
            http_success = validation_result.get("http_success")
            
            host, port = proxy["host"], proxy["port"]
            click.echo(f"[{i}/{len(proxies)}] Testing {host}:{port}")
            
            if error:
                click.echo(f"  💥 Validation error: {error}")
            elif result and result.is_valid:
                # Display validation success info based on proxy type
                proxy_type_name = test_proxy_type.upper()
                click.echo(f"  ✅ {proxy_type_name} validation successful")
                
                if test_proxy_with_request:
                    if http_success:
                        click.echo(f"  ✅ HTTP request successful")
                    else:
                        click.echo(f"  ❌ HTTP request failed")
                
                if not test_proxy_with_request or http_success:
                    valid_proxies.append(proxy)
                    
                    if result.ip_info:
                        ip = result.ip_info.get('ip', 'Unknown')
                        country = result.ip_info.get('country', 'Unknown')
                        click.echo(f"  🌐 IP: {ip} ({country})")
            else:
                error_msg = result.error if result else "Unknown error"
                proxy_type_name = test_proxy_type.upper()
                click.echo(f"  ❌ {proxy_type_name} validation failed: {error_msg}")
        
        return valid_proxies
    
    async def execute_tasks(tasks, available_proxies):
        """Execute task list"""
        # Initialize task processor
        processor = TaskProcessor(task_output_dir)
        
        # Execute tasks using valid proxies
        semaphore = asyncio.Semaphore(concurrent)
        
        async def execute_task(task):
            async with semaphore:
                # Randomly select a proxy
                import random
                proxy = random.choice(available_proxies)
                
                try:
                    import aiohttp
                    from aiohttp_socks import ProxyConnector, ProxyType
                    
                    # Set up proxy connector based on stored proxy type
                    proxy_protocol = proxy.get('protocol', 'socks5')
                    host, port = proxy['host'], proxy['port']
                    
                    if proxy_protocol in ['socks4', 'socks5']:
                        proxy_type = ProxyType.SOCKS5 if proxy_protocol == 'socks5' else ProxyType.SOCKS4
                        connector = ProxyConnector(
                            proxy_type=proxy_type,
                            host=host,
                            port=port
                        )
                        session_kwargs = {'connector': connector}
                    else:  # http proxy
                        connector = aiohttp.TCPConnector()
                        session_kwargs = {
                            'connector': connector,
                            'proxy': f"http://{host}:{port}"
                        }
                    
                    async with aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=test_proxy_timeout),
                        **session_kwargs
                    ) as session:
                        async with session.request(
                            task.get('method', 'GET'),
                            task.get('url'),
                            headers=dict(task.get('headers', {}))
                        ) as response:
                            body = await response.text()
                            
                            response_data = {
                                "code": response.status,
                                "headers": dict(response.headers),
                                "body": body
                            }
                            
                            is_success = 200 <= response.status < 400
                            processor.save_result(task, response_data, is_success)
                            
                            status = "✅" if is_success else "❌"
                            click.echo(f"  {status} {task.get('id')} - {response.status}")
                
                except asyncio.TimeoutError:
                    response_data = {"error": "timeout"}
                    processor.save_result(task, response_data, False)
                    click.echo(f"  ⏰ {task.get('id')} - Timeout")
                    
                except Exception as e:
                    response_data = {"error": str(e)}
                    processor.save_result(task, response_data, False)
                    click.echo(f"  💥 {task.get('id')} - Error: {e}")
        
        # Execute all tasks concurrently
        await asyncio.gather(*[execute_task(task) for task in tasks])
    
    asyncio.run(run_proxy_fleet())


if __name__ == '__main__':
    main()

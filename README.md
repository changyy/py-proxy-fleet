# proxy-fleet 🚢

[![PyPI version](https://img.shields.io/pypi/v/proxy-fleet.svg)](https://pypi.org/project/proxy-fleet)
[![PyPI Downloads](https://static.pepy.tech/badge/proxy-fleet)](https://pepy.tech/projects/proxy-fleet)

A high-performance Python library for managing concurrent HTTP requests through multiple proxy servers with intelligent health monitoring and automatic failover.

## ✨ Features

- 🔄 **Automated proxy health checking** - Continuously monitor proxy server availability
- ⚡ **Concurrent request processing** - Execute multiple HTTP requests simultaneously  
- 🎯 **Intelligent proxy rotation** - Automatically distribute load across healthy proxies
- 📊 **Failure tracking & recovery** - Smart failover with automatic proxy re-enablement
- 💾 **Persistent configuration** - JSON-based proxy management with state persistence
- 🛠️ **Flexible integration** - Use as a library or command-line tool
- 📝 **Comprehensive logging** - Detailed request/response tracking with proxy attribution
- 🔒 **Authentication support** - Handle username/password proxy authentication
- 🚫 **Automatic proxy blacklisting** - Remove unreliable proxies after consecutive failures
- 💿 **Response data storage** - Save successful responses with metadata
- 🧪 **SOCKS proxy validation** - Fast raw socket validation inspired by [TheSpeedX/socker](https://github.com/TheSpeedX/socker)
- 📥 **Automatic proxy discovery** - Download and validate proxies from [TheSpeedX/PROXY-List](https://github.com/TheSpeedX/PROXY-List)

## 🚀 Quick Start

### Installation

```bash
pip install proxy-fleet
```

### Command Line Usage

proxy-fleet provides six main usage scenarios:

#### Scenario 1 - Validate input proxy servers
```bash
# From file
proxy-fleet --test-proxy-server proxies.txt

# From stdin (thanks to https://github.com/TheSpeedX/PROXY-List for proxy contributions)
curl -sL 'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt' | proxy-fleet --test-proxy-server - --concurrent 100 --test-proxy-timeout 10 --test-proxy-with-request 'https://ipinfo.io'
```

#### Scenario 2 - Validate existing proxy servers in storage
```bash
# Test existing proxies
proxy-fleet --test-proxy-storage
```

#### Scenario 3 - List current proxy servers in storage
```bash
# List all proxy status in JSON format
proxy-fleet --list-proxy

# List only verified/valid proxies
proxy-fleet --list-proxy-verified

# List only failed/invalid proxies
proxy-fleet --list-proxy-failed
```

#### Scenario 4 - Remove failed proxy servers from storage
```bash
# Clean up failed/invalid proxies from storage
proxy-fleet --remove-proxy-failed
```

#### Scenario 5 - Execute HTTP requests through proxy servers
```bash
# Execute tasks from file
proxy-fleet --task-input tasks.json

# Execute tasks from stdin
cat tasks.json | proxy-fleet --task-input -
```

#### Scenario 6 - Retry failed tasks
```bash
# Retry previously failed tasks
proxy-fleet --task-retry
```

#### Scenario 7 - List current task results
```bash
# Show task execution statistics
proxy-fleet --list-task-result
```

### CLI Options

-- `--test-proxy-type [socks4|socks5|http]` - Proxy type (default: socks5)
-- `--test-proxy-timeout INTEGER` - Proxy connection timeout in seconds
-- `--test-proxy-with-request TEXT` - Additional HTTP request validation
-- `--proxy-storage TEXT` - Proxy state storage directory (default: proxy)
-- `--list-proxy` - List all proxy server status in JSON format
-- `--list-proxy-verified` - List only verified/valid proxy servers in JSON format
-- `--list-proxy-failed` - List only failed/invalid proxy servers in JSON format
-- `--remove-proxy-failed` - Remove all failed/invalid proxy servers from proxy storage
-- `--task-output-dir TEXT` - Task output directory (default: output)
-- `--concurrent INTEGER` - Maximum concurrent connections (default: 10)
-- `--verbose` - Show verbose outputct/proxy-fleet)

### Library Usage

```python
import asyncio
from proxy_fleet import ProxyFleet, HttpTask, HttpMethod, FleetConfig

async def main():
    # Create configuration
    config = FleetConfig(
        proxy_file="proxies.json",
        output_dir="output",
        max_concurrent_requests=20
    )
    
    # Initialize the proxy fleet
    fleet = ProxyFleet(config)
    
    # Load proxy servers
    proxy_list = [
        {"host": "proxy1.example.com", "port": 8080},
        {"host": "proxy2.example.com", "port": 8080, "username": "user", "password": "pass"},
        {"host": "proxy3.example.com", "port": 3128, "protocol": "https"}
    ]
    await fleet.load_proxies(proxy_list)
    
    # Create HTTP tasks
    tasks = [
        HttpTask(
            task_id="get_test",
            url="https://httpbin.org/get",
            method=HttpMethod.GET,
            headers={"User-Agent": "ProxyFleet/1.0"}
        ),
        HttpTask(
            task_id="post_test", 
            url="https://httpbin.org/post",
            method=HttpMethod.POST,
            data={"key": "value"},
            headers={"Content-Type": "application/json"}
        ),
        HttpTask(
            task_id="ip_check",
            url="https://ipinfo.io/json"
        )
    ]
    
    # Execute tasks with automatic proxy rotation
    results = await fleet.execute_tasks(tasks, output_dir="./results")
    
    for result in results:
        print(f"Task {result.task_id}: {result.status}")
        print(f"Used proxy: {result.proxy_used}")
        print(f"Response time: {result.response_time}s")

if __name__ == "__main__":
    asyncio.run(main())
```

## 📋 Task Configuration

Create a `tasks.json` file for HTTP request tasks:

```json
[
  {
    "id": "check_ip",
    "url": "https://ipinfo.io/json",
    "method": "GET",
    "headers": {
      "User-Agent": "proxy-fleet/1.0"
    }
  },
  {
    "id": "post_data",
    "url": "https://httpbin.org/post",
    "method": "POST",
    "headers": {
      "Content-Type": "application/json"
    },
    "data": {
      "test": "data"
    }
  }
]
```

## � Output Structure

proxy-fleet creates organized output directories:

```
proxy/               # Proxy storage directory (default)
├── proxy.json       # Proxy server status and statistics
└── test-proxy-server.log  # Proxy validation logs

output/              # Task execution results (default)
├── done.json        # Successful task results
└── fail.json        # Failed task results
```

## 🔍 Monitoring & Logging

### Built-in Monitoring

- **Health Checks**: Automatic proxy health monitoring
- **Failure Tracking**: Recent failure count with time windows  
- **Performance Metrics**: Response time tracking
- **Success Rates**: Per-proxy success/failure statistics

### Logging Configuration

```python
from proxy_fleet.utils import setup_logging

# Configure logging
setup_logging(log_file="proxy_fleet.log", level="INFO")
```

## 🚫 Failure Handling

proxy-fleet implements intelligent failure handling:

1. **Recent Failure Tracking**: Count failures in rolling time window
2. **Automatic Blacklisting**: Remove proxies exceeding failure threshold  
3. **Health Recovery**: Automatically re-test unhealthy proxies
4. **Graceful Degradation**: Continue with remaining healthy proxies
5. **Task Retries**: Configurable retry logic with different proxies

## 🎯 Use Cases

- **Web Scraping**: Distribute requests across multiple IPs
- **API Testing**: Test services through different proxy locations  
- **Load Testing**: Generate traffic from multiple sources
- **Data Collection**: Gather data while respecting rate limits
- **Proxy Maintenance**: Monitor and manage proxy server fleets

## 📊 Performance

- **Concurrent Execution**: Configurable concurrency limits
- **Async I/O**: Non-blocking request processing
- **Memory Efficient**: Streaming response handling
- **Scalable**: Supports hundreds of concurrent requests
- **Fast Failover**: Quick detection and bypass of failed proxies

## 🔧 Requirements

- Python 3.8+
- aiohttp >= 3.8.0
- aiofiles >= 0.8.0  
- pydantic >= 1.10.0
- click >= 8.0.0
- rich >= 12.0.0

Optional:
- aiohttp-socks >= 0.7.0 (for SOCKS proxy support)

## 📝 Examples

See the `examples/` directory for complete usage examples:

- `basic_usage.py` - Basic library usage
- `example_tasks.json` - Sample HTTP tasks
- `example_proxies.json` - Sample proxy configuration

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality  
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details.

## 🎉 Changelog

### v0.1.0
- Initial release
- Basic proxy fleet management
- Health monitoring system
- CLI tool
- Comprehensive documentation

---

**proxy-fleet** - Manage your proxy servers like a fleet! 🚢

### SOCKS Proxy Validation

proxy-fleet includes fast SOCKS proxy validation inspired by [TheSpeedX/socker](https://github.com/TheSpeedX/socker) and uses proxy lists from [TheSpeedX/PROXY-List](https://github.com/TheSpeedX/PROXY-List):

#### Quick Proxy Testing Example

Thanks to [TheSpeedX/PROXY-List](https://github.com/TheSpeedX/PROXY-List) for providing public proxy lists:

```bash
# Test SOCKS5 proxies from TheSpeedX repository
curl -sL 'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt' | proxy-fleet --test-proxy-server - --concurrent 100 --test-proxy-timeout 10 --test-proxy-with-request 'https://ipinfo.io'

# Test HTTP proxies
curl -sL 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt' | proxy-fleet --test-proxy-server - --test-proxy-type http --concurrent 50
```

#### Library Usage for SOCKS Validation

```python
from proxy_fleet.utils.socks_validator import SocksValidator

async def validate_socks_proxies():
    validator = SocksValidator(timeout=5.0, check_ip_info=True)
    
    # Validate SOCKS5 proxy
    result = await validator.async_validate_socks5('proxy.example.com', 1080)
    if result.is_valid:
        print(f"✅ Proxy is valid")
        if result.ip_info:
            print(f"   IP: {result.ip_info.get('ip')}")
            print(f"   Country: {result.ip_info.get('country')}")
    else:
        print(f"❌ Proxy validation failed: {result.error}")
```

### Two-Stage Proxy Validation

Combine fast SOCKS validation with HTTP testing for optimal proxy discovery:

```bash
# Stage 1: Download and validate SOCKS proxies (thanks to TheSpeedX/PROXY-List)
curl -sL 'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt' | proxy-fleet --test-proxy-server - --concurrent 100 --test-proxy-timeout 5

# Stage 2: Test HTTP requests through validated proxies
proxy-fleet --test-proxy-storage --test-proxy-with-request 'https://httpbin.org/ip' --test-proxy-timeout 10

# List final valid proxies
proxy-fleet --list-proxy
```

#### Using Library for Two-Stage Validation

```python
import asyncio
from proxy_fleet.utils.socks_validator import SocksValidator

async def two_stage_validation():
    validator = SocksValidator(timeout=3.0, check_ip_info=True)
    
    # Stage 1: Fast SOCKS handshake validation
    proxy_lines = [
        "proxy1.example.com:1080",
        "proxy2.example.com:1080", 
        "proxy3.example.com:1080"
    ]
    
    quick_valid = []
    for line in proxy_lines:
        host, port = line.split(':')
        result = await validator.async_validate_socks5(host, int(port))
        if result.is_valid:
            quick_valid.append({'host': host, 'port': int(port)})
    
    print(f"Stage 1: {len(quick_valid)}/{len(proxy_lines)} passed SOCKS validation")
    
    # Stage 2: Use CLI for HTTP validation
    # Save validated proxies to file and use --test-proxy-storage
    with open('validated_proxies.txt', 'w') as f:
        for proxy in quick_valid:
            f.write(f"{proxy['host']}:{proxy['port']}\n")
    
    print("Run: proxy-fleet --test-proxy-server validated_proxies.txt --test-proxy-with-request 'https://httpbin.org/ip'")
```

# proxy-fleet 🚢

[![PyPI version](https://img.shields.io/pypi/v/proxy-fleet.svg)](https://pypi.org/project/proxy-fleet)
[![PyPI Downloads](https://static.pepy.tech/badge/proxy-fleet)](https://pepy.tech/projects/proxy-fleet)

A high-performance Python library for managing concurrent HTTP requests through multiple proxy servers with intelligent health monitoring, automatic failover, and enterprise-grade proxy server capabilities.

## ✨ Features

### Core Features
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

### Enhanced Proxy Server (New!) 🚀
- 🏭 **Enterprise-grade proxy server** - Production-ready HTTP proxy server with advanced features
- ⚖️ **Multiple load balancing strategies** - Round-robin, random, least-connections, weighted, response-time, and fail-over
- 🔄 **Multi-process architecture** - Scale across multiple CPU cores for high concurrency
- 🏥 **Advanced health monitoring** - Circuit breakers, health checks, and automatic recovery
- 📈 **Real-time monitoring** - Live statistics, metrics, and performance tracking
- 🎛️ **Flexible configuration** - JSON-based configuration with hot-reload support
- 💪 **HAProxy-like features** - Enterprise load balancer capabilities for proxy rotation

## 🚀 Quick Start

### Installation

```bash
pip install proxy-fleet
```

### Enhanced Proxy Server (Recommended)

The enhanced proxy server provides enterprise-grade features for high-performance proxy management:

```bash
# Generate default configuration
proxy-fleet --generate-config

# Start enhanced server with intelligent load balancing
proxy-fleet --enhanced-proxy-server

# Start with specific strategy and custom configuration
proxy-fleet --enhanced-proxy-server --proxy-server-strategy least_connections --proxy-server-config my_config.json

# Start with multiple workers for high concurrency
proxy-fleet --enhanced-proxy-server --proxy-server-workers 8
```

**Key benefits:**
- **Multiple load balancing strategies** for optimal performance
- **Multi-process workers** for handling thousands of concurrent requests
- **Circuit breakers** and health checks for automatic failover
- **Real-time monitoring** with `/stats` and `/health` endpoints
- **Production-ready** with comprehensive logging and error handling

### Command Line Usage

proxy-fleet provides nine main usage scenarios:

#### Scenario 1 - Validate input proxy servers
```bash
# From file
proxy-fleet --test-proxy-server proxies.txt

# From stdin (thanks to https://github.com/TheSpeedX/PROXY-List for proxy contributions)
curl -sL 'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt' | proxy-fleet --test-proxy-server - --concurrent 100 --test-proxy-timeout 10 --test-proxy-with-request 'https://ipinfo.io/json'
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

#### Scenario 8 - Start basic HTTP proxy server
```bash
# Start basic proxy server with round-robin rotation
proxy-fleet --start-proxy-server --proxy-server-port 8888

# Start with random rotation
proxy-fleet --start-proxy-server --proxy-server-rotation random
```

#### Scenario 9 - Start enhanced HTTP proxy server (Recommended)
```bash
# Generate configuration file
proxy-fleet --generate-config

# Start enhanced server with intelligent load balancing
proxy-fleet --enhanced-proxy-server

# Start with custom settings
proxy-fleet --enhanced-proxy-server --proxy-server-strategy least_connections --proxy-server-workers 8

# Development mode (single process)
proxy-fleet --enhanced-proxy-server --single-process
```

### CLI Options

#### Proxy Validation
- `--test-proxy-type [socks4|socks5|http]` - Proxy type (default: socks5)
- `--test-proxy-timeout INTEGER` - Proxy connection timeout in seconds
- `--test-proxy-with-request TEXT` - Additional HTTP request validation
- `--test-proxy-server TEXT` - Validate proxies from file or stdin
- `--test-proxy-storage` - Test existing proxies in storage

#### Proxy Management
- `--proxy-storage TEXT` - Proxy state storage directory (default: proxy)
- `--list-proxy` - List all proxy server status in JSON format
- `--list-proxy-verified` - List only verified/valid proxy servers in JSON format
- `--list-proxy-failed` - List only failed/invalid proxy servers in JSON format
- `--remove-proxy-failed` - Remove all failed/invalid proxy servers from proxy storage

#### Task Execution
- `--task-input TEXT` - Execute HTTP tasks from file or stdin
- `--task-retry` - Retry previously failed tasks
- `--task-output-dir TEXT` - Task output directory (default: output)
- `--list-task-result` - Show task execution statistics

#### Basic Proxy Server
- `--start-proxy-server` - Start basic HTTP proxy server
- `--proxy-server-host TEXT` - Proxy server host (default: 127.0.0.1)
- `--proxy-server-port INTEGER` - Proxy server port (default: 8888)
- `--proxy-server-rotation [round-robin|random]` - Basic rotation mode

#### Enhanced Proxy Server (Recommended)
- `--enhanced-proxy-server` - Start enhanced HTTP proxy server with advanced features
- `--generate-config` - Generate default proxy server configuration file
- `--proxy-server-config TEXT` - Configuration file for enhanced server (default: proxy_server_config.json)
- `--proxy-server-workers INTEGER` - Number of worker processes (default: CPU count)
- `--proxy-server-strategy [round_robin|random|least_connections|weighted|response_time|fail_over]` - Load balancing strategy
- `--single-process` - Run enhanced server in single process mode (for development)

#### General Options
- `--concurrent INTEGER` - Maximum concurrent connections (default: 10)
- `--verbose` - Show verbose output

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

## 🏭 Enhanced Proxy Server

The enhanced proxy server provides enterprise-grade features for high-performance proxy management, similar to HAProxy but specifically designed for proxy rotation.

### Quick Start with Enhanced Server

```bash
# 1. First, validate some proxies
curl -sL 'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt' | proxy-fleet --test-proxy-server - --concurrent 50

# 2. Generate default configuration
proxy-fleet --generate-config

# 3. Start the enhanced server
proxy-fleet --enhanced-proxy-server

# 4. Test the server
curl --proxy http://127.0.0.1:8888 http://httpbin.org/ip
```

### Load Balancing Strategies

#### 1. **Least Connections** (Recommended for production)
```bash
proxy-fleet --enhanced-proxy-server --proxy-server-strategy least_connections
```
Routes requests to the proxy with the fewest active connections.

#### 2. **Response Time Based**
```bash
proxy-fleet --enhanced-proxy-server --proxy-server-strategy response_time
```
Routes requests to the proxy with the best average response time.

#### 3. **Weighted Round Robin**
```json
{
  "load_balancing": {
    "strategy": "weighted",
    "strategies": {
      "weighted": {
        "proxy_weights": {
          "fast-proxy.com:1080": 3,
          "medium-proxy.com:1080": 2,
          "slow-proxy.com:1080": 1
        }
      }
    }
  }
}
```

#### 4. **Fail Over**
```json
{
  "load_balancing": {
    "strategy": "fail_over",
    "strategies": {
      "fail_over": {
        "primary_proxies": ["primary1.com:1080", "primary2.com:1080"],
        "backup_proxies": ["backup1.com:1080", "backup2.com:1080"]
      }
    }
  }
}
```

### High Concurrency Setup

```bash
# For high-traffic scenarios
proxy-fleet --enhanced-proxy-server \
  --proxy-server-workers 8 \
  --proxy-server-strategy least_connections \
  --proxy-server-host 0.0.0.0 \
  --proxy-server-port 8888
```

### Monitoring & Statistics

```bash
# Get real-time statistics
curl http://127.0.0.1:8888/stats | jq .

# Health check endpoint
curl http://127.0.0.1:8888/health

# Monitor proxy performance
watch -n 1 'curl -s http://127.0.0.1:8888/stats | jq .rotator_stats.proxy_details'
```

### Example Statistics Output

```json
{
  "requests_total": 1000,
  "requests_success": 950,
  "requests_failed": 50,
  "uptime_seconds": 3600,
  "rotator_stats": {
    "strategy": "least_connections",
    "total_proxies": 10,
    "available_proxies": 8,
    "overall_success_rate": 95.0,
    "proxy_details": {
      "proxy1.com:1080": {
        "active_connections": 5,
        "total_requests": 100,
        "success_rate": 95.0,
        "average_response_time": 1.25,
        "is_healthy": true,
        "circuit_breaker_state": "closed"
      }
    }
  }
}
```

### Testing the Enhanced Server

```bash
# Run comprehensive tests
python test_enhanced_proxy_server.py

# Test with high concurrency
python test_enhanced_proxy_server.py --concurrent-workers 50 --concurrent-duration 60

# Test load balancing
python test_enhanced_proxy_server.py --load-balance-requests 500
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
curl -sL 'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt' | proxy-fleet --test-proxy-server - --concurrent 100 --test-proxy-timeout 10 --test-proxy-with-request 'https://ipinfo.io/json'

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

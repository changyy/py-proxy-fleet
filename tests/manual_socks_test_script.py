#!/usr/bin/env python3
"""
Manual test script for SOCKS validation functionality.
Run this to test the new SOCKS validator with real proxies.
Tests for proxy-fleet v2.1.0 API compatibility.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from proxy_fleet.utils.socks_validator import SocksValidator
    from proxy_fleet import ProxyFleet, HttpTask, HttpMethod
    from proxy_fleet.models.config import FleetConfig
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure proxy-fleet is installed: pip install -e .")
    sys.exit(1)


async def run_comprehensive_test():
    """Run comprehensive SOCKS validation tests"""
    print("🚀 Proxy Fleet - SOCKS Validation Test v2.1.0")
    print("=" * 50)
    
    # Test 1: Basic SOCKS validation
    print("\n📋 Test 1: Basic SOCKS Validation")
    validator = SocksValidator()
    
    # Test some common SOCKS proxies
    test_proxies = [
        "socks5://127.0.0.1:1080",
        "socks4://127.0.0.1:1080", 
        "http://127.0.0.1:8080"
    ]
    
    for proxy_url in test_proxies:
        try:
            print(f"🔍 Testing {proxy_url}...")
            result = await validator.validate_proxy(proxy_url)
            status = "✅ Valid" if result.is_valid else f"❌ Invalid: {result.error}"
            print(f"   {status}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    # Test 2: Integration with Proxy Fleet
    print("\n📋 Test 2: Integration with Proxy Fleet")
    try:
        # Test with local proxies if available
        test_proxy_configs = [
            {"host": "127.0.0.1", "port": 8080, "protocol": "http"},
            {"host": "127.0.0.1", "port": 1080, "protocol": "socks5"}
        ]
        
        print("🔍 Testing integration with fleet...")
        
        config = FleetConfig(
            max_concurrent_requests=2,
            health_check_timeout=10,
            default_timeout=10
        )
        
        fleet = ProxyFleet(config)
        await fleet.load_proxies(test_proxy_configs)
        
        # Test task
        task = HttpTask(
            task_id="integration_test",
            url="https://httpbin.org/ip",
            method=HttpMethod.GET,
            timeout=10,
            max_retries=1
        )
        
        results = await fleet.execute_tasks([task])
        result = results[0]
        
        if result.is_success:
            print(f"✅ Fleet test successful via {result.proxy_used}")
            print(f"   Response time: {result.response_time:.2f}s")
            print(f"   Status code: {result.status_code}")
        else:
            print(f"❌ Fleet test failed: {result.error_message}")
            print("   (This is expected if no local proxies are running)")
            
    except Exception as e:
        print(f"❌ Fleet integration test failed: {e}")
    
    print("\n✅ Comprehensive test completed!")
    print("\nNext steps:")
    print("- Run 'pytest tests/ -v' for full test suite")
    print("- Use SocksValidator in your own projects for fast proxy validation")
    print("- Start local proxies (HTTP on 8080, SOCKS5 on 1080) to test integration")


def main():
    """Main entry point"""
    try:
        asyncio.run(run_comprehensive_test())
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

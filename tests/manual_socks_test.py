#!/usr/bin/env python3
"""
Manual test script for SOCKS validation functionality.
Run this to test the new SOCKS validator with real proxies.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from proxy_fleet.utils.socks_validator import SocksValidator, ProxyDownloader, test_socks_validation


async def run_comprehensive_test():
    """Run comprehensive SOCKS validation tests"""
    print("🚀 Proxy Fleet - SOCKS Validation Test")
    print("=" * 50)
    
    # Test 1: Basic SOCKS validation
    print("\n📋 Test 1: Basic SOCKS Validation")
    await test_socks_validation()
    
    # Test 2: Compare with fleet testing
    print("\n📋 Test 2: Integration with Proxy Fleet")
    try:
        from proxy_fleet import ProxyFleet, HttpTask
        from proxy_fleet.models.config import FleetConfig
        
        downloader = ProxyDownloader()
        
        # Download a few HTTP proxies for comparison
        print("📥 Downloading HTTP proxies for fleet comparison...")
        http_proxies = await downloader.download_proxy_list('http', limit=3)
        
        if http_proxies:
            print(f"🔍 Testing {len(http_proxies)} HTTP proxies with fleet...")
            
            config = FleetConfig(
                max_concurrent_requests=2,
                health_check_timeout=10,
                default_timeout=10
            )
            
            fleet = ProxyFleet(config)
            await fleet.load_proxies(http_proxies)
            
            # Test task
            task = HttpTask(
                task_id="integration_test",
                url="https://ipinfo.io/json",
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
        else:
            print("⚠️  No HTTP proxies available for fleet test")
            
    except Exception as e:
        print(f"❌ Fleet integration test failed: {e}")
    
    print("\n✅ Comprehensive test completed!")
    print("\nNext steps:")
    print("- Run 'pytest tests/test_real_proxies.py::TestSocksRawValidation -v' for full test suite")
    print("- Use SocksValidator in your own projects for fast proxy validation")


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

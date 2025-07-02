#!/usr/bin/env python3
"""
Proxy integration test runner using TheSpeedX proxy lists.
Tests integration with current proxy-fleet v2.1.0 API.
"""

import asyncio
import aiohttp
import json
import sys
from pathlib import Path
from datetime import datetime

# Add proxy_fleet to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from proxy_fleet import ProxyFleet, HttpTask, HttpMethod
    from proxy_fleet.utils.socks_validator import SocksValidator
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure proxy-fleet is installed: pip install -e .")
    sys.exit(1)


async def download_proxy_list(proxy_type: str, limit: int = 5):
    """Download and parse proxy list."""
    sources = {
        'http': 'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt',
        'socks4': 'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt',
        'socks5': 'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt'
    }
    
    if proxy_type not in sources:
        raise ValueError(f"Unsupported proxy type: {proxy_type}")
    
    url = sources[proxy_type]
    proxies = []
    
    print(f"📥 Downloading {proxy_type} proxy list from GitHub...")
    
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    content = await response.text()
                    lines = content.strip().split('\n')
                    
                    for line in lines:
                        line = line.strip()
                        if ':' in line and not line.startswith('#'):
                            try:
                                host, port = line.split(':', 1)
                                proxy_config = {
                                    'host': host.strip(),
                                    'port': int(port.strip()),
                                    'protocol': proxy_type
                                }
                                proxies.append(proxy_config)
                                
                                if len(proxies) >= limit:
                                    break
                            except (ValueError, IndexError):
                                continue
                else:
                    print(f"❌ Failed to download proxy list: HTTP {response.status}")
                    return []
                    
    except Exception as e:
        print(f"❌ Error downloading proxy list: {e}")
        return []
    
    print(f"✅ Found {len(proxies)} valid {proxy_type} proxies")
    return proxies


async def test_proxy_type(proxy_type: str):
    """Test a specific proxy type using both fleet and validation."""
    print(f"\n🔍 Testing {proxy_type.upper()} Proxies")
    print("=" * 40)
    
    # Download proxies
    proxies = await download_proxy_list(proxy_type, limit=5)
    
    if not proxies:
        print(f"⚠️  No {proxy_type} proxies available for testing")
        return False
    
    # First, validate proxies with SocksValidator
    print(f"🔍 Pre-validating {len(proxies)} {proxy_type} proxies...")
    validator = SocksValidator(
        timeout=10,
        check_server_via_request=True,
        request_url="https://httpbin.org/ip"
    )
    validated_proxies = []
    
    for proxy_config in proxies:
        try:
            # Create proxy string with protocol
            proxy_string = f"{proxy_config['protocol']}://{proxy_config['host']}:{proxy_config['port']}"
            result = await validator.validate_proxy(proxy_string)
            if result.is_valid:
                validated_proxies.append(proxy_config)
                print(f"   ✅ {proxy_config['host']}:{proxy_config['port']} - Valid")
            else:
                print(f"   ❌ {proxy_config['host']}:{proxy_config['port']} - Invalid: {result.error}")
        except Exception as e:
            print(f"   ❌ {proxy_config['host']}:{proxy_config['port']} - Error: {e}")
    
    if not validated_proxies:
        print(f"⚠️  No working {proxy_type} proxies found after validation")
        return False
    
    # Setup fleet with validated proxies
    fleet = ProxyFleet()
    await fleet.load_proxies(validated_proxies)
    
    # Create test task
    test_task = HttpTask(
        task_id=f"{proxy_type}_test",
        url="https://httpbin.org/ip",
        method=HttpMethod.GET,
        timeout=20,
        max_retries=1,
        headers={"User-Agent": "proxy-fleet-integration-test/2.1.0"}
    )
    
    print(f"🚀 Testing {len(validated_proxies)} validated {proxy_type} proxies with fleet")
    
    # Execute test
    results = await fleet.execute_tasks([test_task])
    result = results[0]
    
    # Show results
    if result.is_success:
        print(f"✅ {proxy_type.upper()} proxy test SUCCESSFUL!")
        print(f"   Proxy used: {result.proxy_used}")
        print(f"   Response time: {result.response_time:.2f}s")
        print(f"   Status code: {result.status_code}")
        
        # Try to parse IP info
        try:
            response_data = json.loads(result.response_data.decode('utf-8'))
            detected_ip = response_data.get('origin', 'Unknown')
            print(f"   Detected IP: {detected_ip}")
        except:
            print("   (Could not parse response data)")
        
        return True
    else:
        print(f"❌ {proxy_type.upper()} proxy test FAILED")
        print(f"   Error: {result.error_message}")
        return False


async def test_all_proxy_types():
    """Test all supported proxy types."""
    print("🌐 Proxy Fleet Integration Test v2.1.0")
    print("Using TheSpeedX/PROXY-List project")
    print("=" * 50)
    
    test_results = {}
    
    # Test HTTP proxies
    test_results['http'] = await test_proxy_type('http')
    
    # Test SOCKS proxies - now natively supported
    test_results['socks4'] = await test_proxy_type('socks4')
    test_results['socks5'] = await test_proxy_type('socks5')
    
    # Summary
    print(f"\n📊 Test Summary")
    print("=" * 20)
    
    successful_tests = sum(1 for success in test_results.values() if success)
    total_tests = len(test_results)
    
    for proxy_type, success in test_results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   {proxy_type.upper()}: {status}")
    
    print(f"\nOverall: {successful_tests}/{total_tests} proxy types working")
    
    if successful_tests > 0:
        print("🎉 Integration test PASSED - at least one proxy type is working!")
        return True
    else:
        print("⚠️  Integration test INCONCLUSIVE - no proxies worked (expected with free public proxies)")
        return False


async def save_proxy_samples():
    """Download and save proxy samples for manual testing."""
    print("💾 Downloading proxy samples for manual testing...")
    
    Path("test_samples").mkdir(exist_ok=True)
    
    for proxy_type in ['http', 'socks4', 'socks5']:
        proxies = await download_proxy_list(proxy_type, limit=10)
        
        if proxies:
            sample_data = {
                'proxies': proxies,
                'downloaded_at': datetime.now().isoformat(),
                'source': f'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/{proxy_type}.txt',
                'count': len(proxies)
            }
            
            with open(f"test_samples/{proxy_type}_sample.json", 'w') as f:
                json.dump(sample_data, f, indent=2)
            
            print(f"   💾 Saved {len(proxies)} {proxy_type} proxies to test_samples/{proxy_type}_sample.json")


async def main():
    """Main test runner."""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "download":
            await save_proxy_samples()
        elif command in ['http', 'socks4', 'socks5']:
            await test_proxy_type(command)
        else:
            print(f"Unknown command: {command}")
            print("Usage: python integration_test.py [download|http|socks4|socks5]")
    else:
        # Run full test suite
        await test_all_proxy_types()


if __name__ == "__main__":
    asyncio.run(main())

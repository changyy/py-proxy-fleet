#!/usr/bin/env python3
"""
Example: Using SOCKS Validator for Fast Proxy Verification

This example demonstrates how to use the SocksValidator class directly
for fast proxy validation without going through the CLI interface.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from proxy_fleet.utils.socks_validator import SocksValidator, ValidationResult


async def example_basic_socks_validation():
    """Basic example of SOCKS proxy validation"""
    print("🔍 Example 1: Basic SOCKS Validation")
    print("-" * 40)

    # Initialize validator with custom timeout
    validator = SocksValidator(timeout=5.0, check_ip_info=True)

    # Example proxy (this is a placeholder - replace with real proxy)
    test_proxy_host = "127.0.0.1"
    test_proxy_port = 1080

    print(f"Testing SOCKS proxy: {test_proxy_host}:{test_proxy_port}")

    # Test SOCKS4
    result4 = await validator.async_validate_socks4(test_proxy_host, test_proxy_port)
    print(f"SOCKS4 validation: {'✅ Valid' if result4.is_valid else '❌ Invalid'}")
    if not result4.is_valid:
        print(f"   Error: {result4.error}")

    # Test SOCKS5
    result5 = await validator.async_validate_socks5(test_proxy_host, test_proxy_port)
    print(f"SOCKS5 validation: {'✅ Valid' if result5.is_valid else '❌ Invalid'}")
    if not result5.is_valid:
        print(f"   Error: {result5.error}")
    else:
        if result5.ip_info:
            print(f"   IP: {result5.ip_info.get('ip', 'Unknown')}")
            print(f"   Country: {result5.ip_info.get('country', 'Unknown')}")


async def example_bulk_validation():
    """Example of bulk proxy validation"""
    print("\n🔍 Example 2: Bulk Proxy Validation")
    print("-" * 40)

    # Sample proxy list (replace with real proxies)
    sample_proxies = [
        {"host": "127.0.0.1", "port": 1080},
        {"host": "192.168.1.100", "port": 1080},
        {"host": "10.0.0.100", "port": 1080},
        {"host": "192.168.1.200", "port": 8080},  # This will be tested as HTTP
    ]

    validator = SocksValidator(timeout=3.0, check_ip_info=True)

    print(f"Testing {len(sample_proxies)} proxies...")

    valid_socks4 = []
    valid_socks5 = []
    valid_http = []

    for i, proxy in enumerate(sample_proxies, 1):
        host, port = proxy["host"], proxy["port"]
        print(f"\n[{i}/{len(sample_proxies)}] Testing {host}:{port}")

        # Test SOCKS4
        result4 = await validator.async_validate_socks4(host, port)
        if result4.is_valid:
            valid_socks4.append(proxy)
            print(f"   ✅ SOCKS4: Valid")
        else:
            print(f"   ❌ SOCKS4: {result4.error}")

        # Test SOCKS5
        result5 = await validator.async_validate_socks5(host, port)
        if result5.is_valid:
            valid_socks5.append(proxy)
            print(f"   ✅ SOCKS5: Valid")
            if result5.ip_info:
                print(f"      IP: {result5.ip_info.get('ip', 'Unknown')}")
        else:
            print(f"   ❌ SOCKS5: {result5.error}")

        # Test HTTP
        result_http = await validator.async_validate_http(host, port)
        if result_http.is_valid:
            valid_http.append(proxy)
            print(f"   ✅ HTTP: Valid")
        else:
            print(f"   ❌ HTTP: {result_http.error}")

    print(f"\n📊 Validation Results:")
    print(f"   SOCKS4: {len(valid_socks4)}/{len(sample_proxies)} valid")
    print(f"   SOCKS5: {len(valid_socks5)}/{len(sample_proxies)} valid")
    print(f"   HTTP:   {len(valid_http)}/{len(sample_proxies)} valid")

    # Save results
    results = {
        "socks4_proxies": valid_socks4,
        "socks5_proxies": valid_socks5,
        "http_proxies": valid_http,
        "validation_timestamp": asyncio.get_event_loop().time(),
    }

    output_file = Path(__file__).parent / "validation_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n💾 Results saved to: {output_file}")


async def example_concurrent_validation():
    """Example of concurrent proxy validation for better performance"""
    print("\n🔍 Example 3: Concurrent Validation")
    print("-" * 40)

    # Sample proxy list
    sample_proxies = [
        {"host": "127.0.0.1", "port": 1080},
        {"host": "192.168.1.100", "port": 1080},
        {"host": "192.168.1.101", "port": 1080},
        {"host": "10.0.0.100", "port": 1080},
        {"host": "10.0.0.101", "port": 1080},
    ]

    validator = SocksValidator(
        timeout=2.0, check_ip_info=False
    )  # Faster without IP info

    # Concurrent validation with semaphore for rate limiting
    semaphore = asyncio.Semaphore(3)  # Max 3 concurrent validations

    async def validate_proxy(proxy):
        async with semaphore:
            host, port = proxy["host"], proxy["port"]

            # Test SOCKS5 only for speed
            result = await validator.async_validate_socks5(host, port)

            return {
                "proxy": proxy,
                "is_valid": result.is_valid,
                "error": result.error if not result.is_valid else None,
            }

    print(f"Testing {len(sample_proxies)} proxies concurrently...")
    start_time = asyncio.get_event_loop().time()

    # Run all validations concurrently
    results = await asyncio.gather(*[validate_proxy(proxy) for proxy in sample_proxies])

    end_time = asyncio.get_event_loop().time()
    duration = end_time - start_time

    # Process results
    valid_proxies = [r for r in results if r["is_valid"]]

    print(f"\n📊 Concurrent Validation Results:")
    print(f"   Total tested: {len(sample_proxies)}")
    print(f"   Valid proxies: {len(valid_proxies)}")
    print(f"   Duration: {duration:.2f} seconds")
    print(f"   Rate: {len(sample_proxies)/duration:.1f} proxies/second")

    # Show details
    for result in results:
        proxy = result["proxy"]
        status = "✅" if result["is_valid"] else "❌"
        error = f" ({result['error']})" if result["error"] else ""
        print(f"   {status} {proxy['host']}:{proxy['port']}{error}")


async def main():
    """Run all examples"""
    print("🚀 SOCKS Validator Examples")
    print("=" * 50)

    await example_basic_socks_validation()
    await example_bulk_validation()
    await example_concurrent_validation()

    print("\n✅ All examples completed!")
    print("\n💡 Tips:")
    print("- Replace example IPs with real proxy servers")
    print("- Use lower timeouts for faster bulk validation")
    print("- Enable check_ip_info=True for detailed proxy information")
    print("- Use semaphores to control concurrent validation rate")


async def main():
    """Run all examples"""
    print("🚀 SOCKS Validator Examples")
    print("=" * 50)
    print("Inspired by TheSpeedX/socker for fast proxy validation")
    print("=" * 50)

    try:
        # Run all examples
        await example_basic_socks_validation()
        await example_bulk_validation()
        await example_concurrent_validation()

        print("\n✅ All examples completed!")
        print("\nKey Benefits of SOCKS Raw Validation:")
        print("- ⚡ Fast validation without HTTP requests")
        print("- 🔍 Direct protocol-level verification")
        print("- 📊 Efficient bulk proxy filtering")
        print("- 🛠️  Perfect for proxy discovery workflows")

    except KeyboardInterrupt:
        print("\n⚠️  Examples interrupted by user")
    except Exception as e:
        print(f"\n❌ Example failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
示例：展示修正後的多協議支持

這個示例展示了如何使用新的 SocksValidator 來處理：
1. SOCKS4 代理 + 服務器請求驗證
2. SOCKS5 代理 + 服務器請求驗證  
3. HTTP 代理 + 服務器請求驗證

修正前的問題：check_server_via_proxy 只支持 SOCKS4/5，不支持 HTTP
修正後：支持所有三種代理類型
"""

import asyncio
import json
from proxy_fleet.utils.socks_validator import SocksValidator


async def demo_protocol_specific_validation():
    """展示不同協議的驗證方式"""
    print("🔧 多協議服務器請求驗證示例")
    print("=" * 50)
    
    # 測試 URL (您可以替換為自己的 API)
    test_urls = [
        "https://httpbin.org/ip",
        "https://ipinfo.io/json",
        "https://api.ipify.org?format=json"
    ]
    
    for test_url in test_urls:
        print(f"\n📋 使用測試 URL: {test_url}")
        print("-" * 40)
        
        # 1. SOCKS5 代理驗證
        print("1. SOCKS5 代理 + 服務器請求驗證:")
        socks5_validator = SocksValidator(
            timeout=10,
            check_server_via_request=True,
            request_url=test_url
        )
        print(f"   ✅ 配置完成 - 會通過 SOCKS5 代理測試 {test_url}")
        print("   📡 使用 aiohttp-socks ProxyConnector (ProxyType.SOCKS5)")
        
        # 在實際環境中的使用示例:
        # result = await socks5_validator.async_validate_socks5("proxy-host", 1080)
        
        # 2. SOCKS4 代理驗證
        print("\n2. SOCKS4 代理 + 服務器請求驗證:")
        socks4_validator = SocksValidator(
            timeout=10,
            check_server_via_request=True,
            request_url=test_url
        )
        print(f"   ✅ 配置完成 - 會通過 SOCKS4 代理測試 {test_url}")
        print("   📡 使用 aiohttp-socks ProxyConnector (ProxyType.SOCKS4)")
        
        # 3. HTTP 代理驗證 (修正後新增支持)
        print("\n3. HTTP 代理 + 服務器請求驗證 (修正後新增):")
        http_validator = SocksValidator(
            timeout=10,
            check_server_via_request=True,
            request_url=test_url
        )
        print(f"   ✅ 配置完成 - 會通過 HTTP 代理測試 {test_url}")
        print("   📡 使用 aiohttp 標準 proxy 參數")
        
        # 在實際環境中的使用示例:
        # result = await http_validator.async_validate_http("proxy-host", 8080)


def show_implementation_details():
    """展示實現細節"""
    print("\n🔍 實現細節")
    print("=" * 50)
    
    print("修正前的問題:")
    print("❌ check_server_via_proxy 只處理 SOCKS4/5:")
    print("   proxy_type = ProxyType.SOCKS5 if protocol == 'socks5' else ProxyType.SOCKS4")
    print("   connector = ProxyConnector(proxy_type=proxy_type, host=host, port=port)")
    print("   # HTTP 代理會失敗 ❌")
    
    print("\n修正後的解決方案:")
    print("✅ 根據協議類型選擇不同的連接方式:")
    print("""
    if protocol in ["socks4", "socks5"]:
        # 使用 aiohttp-socks 處理 SOCKS 代理
        from aiohttp_socks import ProxyConnector, ProxyType
        proxy_type = ProxyType.SOCKS5 if protocol == "socks5" else ProxyType.SOCKS4
        connector = ProxyConnector(proxy_type=proxy_type, host=host, port=port)
        session_kwargs = {"connector": connector}
        
    elif protocol == "http":
        # 使用標準 HTTP 代理 ✅
        connector = aiohttp.TCPConnector()
        proxy_url = f"http://{host}:{port}"
        session_kwargs = {
            "connector": connector,
            "proxy": proxy_url
        }
    """)


def show_usage_comparison():
    """展示使用方式對比"""
    print("\n📊 使用方式對比")
    print("=" * 50)
    
    print("CLI 使用 (所有協議都支持):")
    print("✅ SOCKS5:")
    print("proxy-fleet --test-proxy-server proxies.txt --test-proxy-type socks5 --test-proxy-with-request 'https://ipinfo.io/json'")
    
    print("\n✅ SOCKS4:")
    print("proxy-fleet --test-proxy-server proxies.txt --test-proxy-type socks4 --test-proxy-with-request 'https://ipinfo.io/json'")
    
    print("\n✅ HTTP (修正後支持):")
    print("proxy-fleet --test-proxy-server proxies.txt --test-proxy-type http --test-proxy-with-request 'https://ipinfo.io/json'")
    
    print("\n程式化使用:")
    print("""
# 所有協議都可以這樣使用
validator = SocksValidator(
    check_server_via_request=True,
    request_url='https://myapi.com/location'
)

# SOCKS5
result = await validator.async_validate_socks5(host, port)

# SOCKS4  
result = await validator.async_validate_socks4(host, port)

# HTTP (修正後支持)
result = await validator.async_validate_http(host, port)
""")


def show_expected_responses():
    """展示預期的回應格式"""
    print("\n📋 預期的回應格式")
    print("=" * 50)
    
    print("所有協議的服務器請求驗證都會返回統一格式:")
    
    sample_response = {
        "url": "https://ipinfo.io/json",
        "status_code": 200,
        "success": True,
        "response_body": '{"ip":"1.2.3.4","country":"TW","region":"Asia"}',
        "headers": {
            "content-type": "application/json",
            "server": "nginx"
        },
        "location_info": {
            "location": "TW",
            "source_field": "country",
            "ip": "1.2.3.4",
            "full_response": {
                "ip": "1.2.3.4",
                "country": "TW",
                "region": "Asia"
            }
        }
    }
    
    print(json.dumps(sample_response, indent=2, ensure_ascii=False))
    
    print("\n🎯 重要特性:")
    print("✅ 統一的回應格式 - 無論使用哪種代理協議")
    print("✅ 2XX/3XX 狀態碼驗證 - 只有成功的回應才視為有效")
    print("✅ 智能位置提取 - country → region 優先順序")
    print("✅ 完整錯誤處理 - 依賴包缺失、網路錯誤等")


async def test_error_scenarios():
    """測試錯誤場景"""
    print("\n🚨 錯誤場景測試")
    print("=" * 50)
    
    print("1. 缺少 aiohttp-socks 依賴 (SOCKS 代理):")
    print("   ImportError: aiohttp-socks package required...")
    print("   ✅ 會優雅地處理，返回 None")
    
    print("\n2. 不支持的協議:")
    print("   logger.warning(f'Unsupported proxy protocol: {protocol}')")
    print("   ✅ 會記錄警告，返回 None")
    
    print("\n3. 網路連接失敗:")
    print("   logger.debug(f'Failed to test {url} via {protocol} {host}:{port}: {e}')")
    print("   ✅ 會記錄調試信息，返回 None")
    
    print("\n4. HTTP 狀態碼非 2XX/3XX:")
    print("   logger.debug(f'HTTP test via {protocol} {host}:{port} -> {url}: {status} FAILED')")
    print("   ✅ 會記錄失敗，返回 None")


async def main():
    """執行示例"""
    print("🌐 多協議支持修正示例")
    print("=" * 60)
    
    await demo_protocol_specific_validation()
    show_implementation_details()
    show_usage_comparison()
    show_expected_responses()
    await test_error_scenarios()
    
    print(f"\n✅ 示例完成！")
    print("\n🎯 修正總結:")
    print("1. ✅ 修正了 HTTP 代理無法進行服務器請求驗證的問題")
    print("2. ✅ 統一了所有協議的驗證邏輯")
    print("3. ✅ 保持了向後相容性")
    print("4. ✅ 改善了錯誤處理和日誌記錄")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
範例：使用新的 SocksValidator 進行自定義 API 測試

此範例展示如何：
1. 使用 check_server_via_request 參數進行額外的 HTTP 驗證
2. 只有在 HTTP 回應為 2XX 或 3XX 時才判定代理為有效
3. 自動提取 API 回應中的 country 或 region 欄位
4. 統一的驗證邏輯
"""

import json
import asyncio
from proxy_fleet.utils.socks_validator import SocksValidator
from proxy_fleet.cli.main import ProxyStorage


async def demo_basic_validation():
    """展示基本驗證 (無額外 HTTP 請求)"""
    print("🔍 基本 SOCKS 驗證 (無額外 HTTP 請求)")
    print("-" * 50)
    
    # 基本驗證，只檢查 SOCKS 握手
    validator = SocksValidator(timeout=5)
    
    print(f"設定:")
    print(f"  check_server_via_request: {validator.check_server_via_request}")
    print(f"  request_url: {validator.request_url}")
    print(f"  這個模式只會進行基本的 SOCKS 握手驗證")
    
    # 在實際環境中，您可以這樣測試:
    # result = await validator.async_validate_socks5("your-proxy-host", 1080)
    # print(f"驗證結果: {result}")


async def demo_enhanced_validation():
    """展示增強驗證 (含額外 HTTP 請求)"""
    print("\n🔍 增強 SOCKS 驗證 (含額外 HTTP 請求)")
    print("-" * 50)
    
    # 啟用服務器請求驗證
    test_url = "https://httpbin.org/ip"
    validator = SocksValidator(
        timeout=10,
        check_server_via_request=True,
        request_url=test_url
    )
    
    print(f"設定:")
    print(f"  check_server_via_request: {validator.check_server_via_request}")
    print(f"  request_url: {validator.request_url}")
    print(f"  check_ip_info (自動設定): {validator.check_ip_info}")
    print()
    print("這個模式會:")
    print("1. 首先進行基本的 SOCKS 握手驗證")
    print("2. 如果成功，再通過代理向指定 URL 發送 HTTP 請求")
    print("3. 只有當 HTTP 回應為 2XX 或 3XX 時才判定代理為有效")
    
    # 在實際環境中測試的示例:
    # result = await validator.async_validate_socks5("your-proxy-host", 1080)
    # if result.is_valid:
    #     print("✅ 代理驗證成功 (包含 HTTP 請求測試)")
    #     if result.ip_info:
    #         print(f"服務器回應: {result.ip_info}")
    # else:
    #     print(f"❌ 代理驗證失敗: {result.error}")


async def demo_custom_api_validation():
    """展示自定義 API 驗證"""
    print("\n🔍 自定義 API 驗證")
    print("-" * 50)
    
    # 使用自定義 API 進行驗證
    custom_api_url = "https://ipinfo.io/json"  # 或您自己的 API
    validator = SocksValidator(
        timeout=15,
        check_server_via_request=True,
        request_url=custom_api_url
    )
    
    print(f"設定:")
    print(f"  request_url: {validator.request_url}")
    print()
    print("自定義 API 的優勢:")
    print("1. 可以使用您自己的位置檢測 API")
    print("2. 自動提取 'country' 欄位，回退到 'region' 欄位")
    print("3. 儲存完整的 API 回應以供後續分析")
    print("4. 只有在 API 回應 2XX/3XX 狀態碼時才視為有效")
    
    print("\n期望的 API 回應格式:")
    sample_response = {
        "ip": "1.2.3.4",
        "country": "TW",  # 優先使用
        "region": "Asia",  # 回退選項
        "city": "Taipei",
        "org": "Example ISP"
    }
    print(json.dumps(sample_response, indent=2, ensure_ascii=False))


def demo_cli_integration():
    """展示 CLI 整合方式"""
    print("\n🔧 CLI 整合方式")
    print("-" * 50)
    
    print("1. 基本驗證 (快速，無額外 HTTP 請求):")
    print("proxy-fleet --test-proxy-server proxies.txt")
    print()
    
    print("2. 使用 httpbin.org 進行額外驗證:")
    print("proxy-fleet --test-proxy-server proxies.txt --test-proxy-with-request 'https://httpbin.org/ip'")
    print()
    
    print("3. 使用 ipinfo.io 進行驗證 (含位置信息):")
    print("proxy-fleet --test-proxy-server proxies.txt --test-proxy-with-request 'https://ipinfo.io/json'")
    print()
    
    print("4. 使用自定義 API 進行驗證:")
    print("proxy-fleet --test-proxy-server proxies.txt --test-proxy-with-request 'https://myapi.com/location'")
    print()
    
    print("5. 使用位置過濾啟動代理服務器:")
    print("proxy-fleet --start-proxy-server --proxy-server-use-region TW,US")
    print()
    
    print("CLI 內部邏輯:")
    print("```python")
    print("if test_proxy_with_request:")
    print("    validator = SocksValidator(")
    print("        timeout=test_proxy_timeout,")
    print("        check_server_via_request=True,")
    print("        request_url=test_proxy_with_request")
    print("    )")
    print("else:")
    print("    validator = SocksValidator(timeout=test_proxy_timeout)")
    print("```")


def demo_response_structure():
    """展示回應數據結構"""
    print("\n� 回應數據結構")
    print("-" * 50)
    
    print("當啟用 check_server_via_request 時，result.ip_info 包含:")
    
    sample_response = {
        "url": "https://myapi.com/location",
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
    
    print("\n重要特性:")
    print("✅ success: 只有在狀態碼為 2XX 或 3XX 時才為 True")
    print("✅ location_info: 自動提取的位置信息 (country → region 優先順序)")
    print("✅ full_response: 完整的 JSON 回應，供進階分析使用")
    print("✅ 統一格式: 無論使用哪種 API 都有一致的數據結構")


def demo_status_code_validation():
    """展示狀態碼驗證邏輯"""
    print("\n🎯 狀態碼驗證邏輯")
    print("-" * 50)
    
    print("有效狀態碼 (代理判定為成功):")
    valid_codes = [200, 201, 202, 204, 301, 302, 303, 304, 307, 308]
    for code in valid_codes:
        print(f"  ✅ {code}")
    
    print("\n無效狀態碼 (代理判定為失敗):")
    invalid_codes = [400, 401, 403, 404, 500, 502, 503, 504]
    for code in invalid_codes:
        print(f"  ❌ {code}")
    
    print(f"\n驗證邏輯: 200 <= status_code < 400")
    print("這確保了:")
    print("- 成功的回應 (2XX) 被接受")
    print("- 重定向 (3XX) 也被接受 (表示服務器可達)")
    print("- 客戶端錯誤 (4XX) 和服務器錯誤 (5XX) 被拒絕")


async def main():
    """執行所有示範"""
    print("🌐 proxy-fleet 新版驗證系統示範")
    print("=" * 60)
    
    await demo_basic_validation()
    await demo_enhanced_validation()
    await demo_custom_api_validation()
    demo_cli_integration()
    demo_response_structure()
    demo_status_code_validation()
    
    print(f"\n✅ 示範完成！")
    print("\n🎯 主要優勢:")
    print("1. 統一的驗證邏輯，無重複代碼")
    print("2. 靈活的配置，支援基本和增強驗證")
    print("3. 智能的狀態碼判定 (2XX/3XX 才有效)")
    print("4. 自動的位置信息提取 (country → region)")
    print("5. 向後相容，保持現有 API 不變")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
SOCKS 代理驗證示例，包含 ipinfo.io 查詢功能

這個示例展示如何使用增強的 SOCKS 驗證器來：
1. 驗證 SOCKS 代理的連接性
2. 查詢通過代理的真實 IP 信息
"""

import asyncio
import logging

from proxy_fleet.utils.socks_validator import SocksValidator, ValidationResult

# 設置日誌
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_proxy_with_ip_info():
    """測試代理並獲取 IP 信息"""

    # 測試用的 SOCKS5 代理（這個是示例，實際使用時請替換為真實的代理）
    test_proxies = [
        {"host": "176.65.149.147", "port": 8081, "protocol": "socks5"},
        {"host": "127.0.0.1", "port": 1080, "protocol": "socks5"},  # 本地測試代理
    ]

    print("🚀 開始 SOCKS 代理驗證（包含 IP 信息檢查）")
    print("=" * 60)

    # 初始化驗證器，啟用 IP 信息檢查
    validator = SocksValidator(timeout=15, check_ip_info=True)

    for i, proxy in enumerate(test_proxies, 1):
        print(f"\n📡 [{i}] 測試代理: {proxy['host']}:{proxy['port']}")
        print("-" * 40)

        try:
            # 執行 SOCKS5 驗證
            result = await validator.async_validate_socks5(proxy["host"], proxy["port"])

            if result.is_valid:
                print(f"✅ SOCKS5 握手成功")

                if result.ip_info:
                    print(f"🌐 IP 信息:")
                    print(f"   📍 IP 地址: {result.ip_info.get('ip', 'Unknown')}")
                    print(f"   🏙️  城市: {result.ip_info.get('city', 'Unknown')}")
                    print(f"   🏳️  國家: {result.ip_info.get('country', 'Unknown')}")
                    print(f"   🏢 組織: {result.ip_info.get('org', 'Unknown')}")
                    print(f"   🕐 時區: {result.ip_info.get('timezone', 'Unknown')}")

                    # 顯示原始 JSON (格式化)
                    import json

                    print(
                        f"   📄 完整信息: {json.dumps(result.ip_info, indent=2, ensure_ascii=False)}"
                    )
                else:
                    print(f"⚠️  無法獲取 IP 信息（可能需要安裝 aiohttp-socks）")

            else:
                print(f"❌ SOCKS5 驗證失敗: {result.error}")

        except Exception as e:
            print(f"💥 驗證過程出錯: {e}")

    print(f"\n🎯 驗證完成！")


async def test_batch_validation():
    """批量驗證多個代理"""

    print(f"\n🔄 批量驗證示例")
    print("=" * 60)

    # 從 TheSpeedX/PROXY-List 下載一些代理進行測試
    from proxy_fleet.utils.socks_validator import ProxyDownloader

    try:
        downloader = ProxyDownloader()
        validator = SocksValidator(timeout=10, check_ip_info=True)

        print("📥 下載 SOCKS5 代理列表...")
        proxies = await downloader.download_proxy_list("socks5", limit=3)

        print(f"🔍 測試 {len(proxies)} 個 SOCKS5 代理...")

        for i, proxy in enumerate(proxies, 1):
            host, port = proxy["host"], proxy["port"]
            print(f"\n[{i}/{len(proxies)}] 測試 {host}:{port}")

            result = await validator.async_validate_socks5(host, port)

            if result.is_valid and result.ip_info:
                ip = result.ip_info.get("ip", "Unknown")
                country = result.ip_info.get("country", "Unknown")
                city = result.ip_info.get("city", "Unknown")
                print(f"✅ 有效 - IP: {ip} ({city}, {country})")
            elif result.is_valid:
                print(f"✅ 連接有效，但無法獲取 IP 信息")
            else:
                print(f"❌ 無效 - {result.error}")

    except Exception as e:
        print(f"❌ 批量測試失敗: {e}")


if __name__ == "__main__":
    print("🎪 SOCKS 代理驗證器 - IP 信息檢查功能演示")
    print("=" * 60)

    async def main():
        await test_proxy_with_ip_info()
        await test_batch_validation()

        print(f"\n💡 使用提示:")
        print(f"   - 確保已安裝 aiohttp-socks: pip install aiohttp-socks")
        print(f"   - 測試真實代理時請替換示例中的 IP 和端口")
        print(f"   - 可以通過 check_ip_info=False 禁用 IP 檢查以提高速度")

    asyncio.run(main())

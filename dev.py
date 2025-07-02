#!/usr/bin/env python3
"""
開發工具腳本 - 用於 proxy-fleet 項目的常見開發任務
使用方法: python dev.py <command>
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

# 確保我們在正確的目錄
PROJECT_ROOT = Path(__file__).parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"

def run_command(cmd, description=None):
    """執行命令並顯示結果"""
    if description:
        print(f"🔧 {description}")
    
    print(f"💻 Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)
        print("✅ 完成")
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ 失敗 (exit code: {e.returncode})")
        sys.exit(e.returncode)

def install():
    """安裝項目依賴"""
    print("📦 安裝項目依賴...")
    
    # 以開發模式安裝項目（包含開發依賴）
    run_command([str(VENV_PYTHON), "-m", "pip", "install", "-e", ".[dev]"], 
                "安裝項目及開發依賴")
    
    print("✅ 所有依賴安裝完成！")

def test():
    """執行測試"""
    print("🧪 執行測試...")
    run_command([str(VENV_PYTHON), "-m", "pytest", "tests/", "-v"], 
                "執行單元測試")

def test_coverage():
    """執行測試並生成覆蓋率報告"""
    print("🧪 執行測試並生成覆蓋率報告...")
    run_command([str(VENV_PYTHON), "-m", "pytest", "tests/", 
                "--cov=proxy_fleet", "--cov-report=html", "--cov-report=term"], 
                "執行測試並生成覆蓋率報告")
    print("📊 覆蓋率報告已生成到 htmlcov/ 目錄")

def format_code():
    """格式化代碼"""
    print("🎨 格式化代碼...")
    
    # 使用 black 格式化
    run_command([str(VENV_PYTHON), "-m", "black", "proxy_fleet/", "tests/", "examples/"], 
                "使用 black 格式化代碼")
    
    # 使用 isort 排序 imports
    run_command([str(VENV_PYTHON), "-m", "isort", "proxy_fleet/", "tests/", "examples/"], 
                "使用 isort 排序 imports")

def lint():
    """檢查代碼質量"""
    print("🔍 檢查代碼質量...")
    
    # flake8 檢查
    run_command([str(VENV_PYTHON), "-m", "flake8", "proxy_fleet/", "tests/"], 
                "使用 flake8 檢查代碼")
    
    # mypy 類型檢查
    run_command([str(VENV_PYTHON), "-m", "mypy", "proxy_fleet/"], 
                "使用 mypy 進行類型檢查")

def clean():
    """清理生成的文件"""
    print("🧹 清理生成的文件...")
    
    patterns = [
        "build/",
        "dist/",
        "*.egg-info/",
        "__pycache__/",
        "*.pyc",
        "*.pyo",
        ".pytest_cache/",
        ".coverage",
        "htmlcov/",
        ".mypy_cache/"
    ]
    
    for pattern in patterns:
        for path in PROJECT_ROOT.rglob(pattern):
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                    print(f"🗑️  刪除目錄: {path}")
                else:
                    path.unlink()
                    print(f"🗑️  刪除文件: {path}")

def build():
    """構建發布包"""
    print("📦 構建發布包...")
    
    # 清理舊的構建文件
    clean()
    
    # 構建 wheel 和 sdist
    run_command([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "build"], 
                "安裝構建工具")
    
    run_command([str(VENV_PYTHON), "-m", "build"], 
                "構建發布包")
    
    print("📦 發布包已生成到 dist/ 目錄")

def install_local():
    """從本地構建的包安裝"""
    print("📦 從本地構建的包安裝...")
    
    # 先構建
    build()
    
    # 查找最新的 wheel 文件
    dist_dir = PROJECT_ROOT / "dist"
    wheel_files = list(dist_dir.glob("*.whl"))
    
    if not wheel_files:
        print("❌ 沒有找到 wheel 文件")
        sys.exit(1)
    
    latest_wheel = max(wheel_files, key=lambda p: p.stat().st_mtime)
    
    # 安裝
    run_command([str(VENV_PYTHON), "-m", "pip", "install", "--force-reinstall", str(latest_wheel)], 
                f"安裝 {latest_wheel.name}")

def run_example():
    """執行示例"""
    print("🚀 執行基本示例...")
    example_file = PROJECT_ROOT / "examples" / "basic_usage.py"
    
    if not example_file.exists():
        print("❌ 找不到示例文件")
        sys.exit(1)
    
    run_command([str(VENV_PYTHON), str(example_file)], 
                "執行基本使用示例")

def run_server():
    """啟動代理服務器"""
    print("🚀 啟動增強型代理服務器...")
    print("💡 使用 Ctrl+C 停止服務器")
    
    cmd = [
        str(VENV_PYTHON), "-m", "proxy_fleet.cli.main",
        "--enhanced-proxy-server",
        "--single-process",
        "--verbose"
    ]
    
    try:
        subprocess.run(cmd, cwd=PROJECT_ROOT)
    except KeyboardInterrupt:
        print("\n🛑 服務器已停止")

def check_version():
    """檢查版本信息"""
    print("📋 版本信息:")
    
    # Python 版本
    print(f"Python: {sys.version}")
    
    # 項目版本
    try:
        result = subprocess.run([str(VENV_PYTHON), "setup.py", "--version"], 
                              capture_output=True, text=True, cwd=PROJECT_ROOT)
        if result.returncode == 0:
            print(f"proxy-fleet: {result.stdout.strip()}")
        else:
            print("❌ 無法獲取項目版本")
    except Exception as e:
        print(f"❌ 版本檢查失敗: {e}")

def show_help():
    """顯示幫助信息"""
    help_text = """
🚀 proxy-fleet 開發工具

可用命令:
  install        安裝項目依賴 (生產 + 開發)
  test          執行測試
  test-cov      執行測試並生成覆蓋率報告
  format        格式化代碼 (black + isort)
  lint          檢查代碼質量 (flake8 + mypy)
  clean         清理生成的文件
  build         構建發布包
  install-local 從本地構建的包安裝
  run-example   執行基本示例
  run-server    啟動代理服務器
  version       顯示版本信息
  help          顯示此幫助信息

使用方法:
  python dev.py <command>

示例:
  python dev.py install      # 安裝依賴
  python dev.py test         # 執行測試
  python dev.py format       # 格式化代碼
  python dev.py run-server   # 啟動服務器
"""
    print(help_text)

def main():
    """主函數"""
    if len(sys.argv) < 2:
        show_help()
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    # 檢查虛擬環境
    if not VENV_PYTHON.exists():
        print("❌ 未找到虛擬環境，請先創建虛擬環境:")
        print("   python -m venv .venv")
        print("   source .venv/bin/activate  # (on macOS/Linux)")
        sys.exit(1)
    
    commands = {
        "install": install,
        "test": test,
        "test-cov": test_coverage,
        "format": format_code,
        "lint": lint,
        "clean": clean,
        "build": build,
        "install-local": install_local,
        "run-example": run_example,
        "run-server": run_server,
        "version": check_version,
        "help": show_help,
    }
    
    if command in commands:
        commands[command]()
    else:
        print(f"❌ 未知命令: {command}")
        show_help()
        sys.exit(1)

if __name__ == "__main__":
    main()

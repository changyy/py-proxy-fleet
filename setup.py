# setup.py
from setuptools import setup, find_packages
import pathlib
import re

here = pathlib.Path(__file__).parent.resolve()

# 讀取 README.md 作為長描述
def get_long_description():
    readme_path = here / "README.md"
    try:
        content = readme_path.read_text(encoding="utf-8")
        
        # 可選：處理相對路徑，轉換為絕對 GitHub URL
        # 如果 README.md 中有相對路徑的圖片，可以在這裡處理
        # 例如：content = content.replace("](docs/", "](https://github.com/changyy/py-proxy-fleet/blob/main/docs/")
        
        return content
    except FileNotFoundError:
        print("Warning: README.md not found, using short description")
        return "A production-ready proxy server with intelligent load balancing and health monitoring"
    except Exception as e:
        print(f"Warning: Could not read README.md: {e}")
        return "A production-ready proxy server with intelligent load balancing and health monitoring"

long_description = get_long_description()

# 從 __init__.py 讀取版本號碼
def get_version():
    init_py = here / "proxy_fleet" / "__init__.py"
    with open(init_py, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if match:
        return match.group(1)
    raise RuntimeError("Cannot find version string")

setup(
    name="proxy-fleet",
    version=get_version(),
    author="changyy",
    author_email="changyy.csie@gmail.com",
    description="A production-ready proxy server with intelligent load balancing and health monitoring",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/changyy/py-proxy-fleet",
    project_urls={
        "Bug Reports": "https://github.com/changyy/py-proxy-fleet/issues",
        "Source": "https://github.com/changyy/py-proxy-fleet",
        "Documentation": "https://github.com/changyy/py-proxy-fleet/blob/main/docs/README.md",
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators", 
        "Topic :: Internet :: Proxy Servers",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
        "Topic :: System :: Networking",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Environment :: Console",
        "Framework :: AsyncIO",
    ],
    keywords=[
        "proxy", "proxy-server", "load-balancer", "haproxy", "nginx",
        "health-check", "failover", "rotation", "socks", "http-proxy",
        "networking", "async", "aiohttp", "monitoring", "graceful-shutdown"
    ],
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "aiohttp>=3.8.0,<4.0.0",
        "aiohttp-socks>=0.7.0,<1.0.0", 
        "click>=8.0.0,<9.0.0",
        "pydantic>=2.0.0,<3.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "black>=22.0.0",
            "isort>=5.0.0",
            "flake8>=5.0.0",
            "mypy>=0.991",
            "pre-commit>=2.20.0",
        ],
        "test": [
            "pytest>=7.0.0", 
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
        ],
        "monitoring": [
            "prometheus-client>=0.14.0",
            "psutil>=5.9.0",
        ],
        "all": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0", 
            "pytest-cov>=4.0.0",
            "black>=22.0.0",
            "flake8>=5.0.0",
            "mypy>=0.991",
            "pre-commit>=2.20.0",
            "prometheus-client>=0.14.0",
            "psutil>=5.9.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "proxy-fleet=proxy_fleet.cli.main:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)

#!/usr/bin/env python3
"""
Basic usage examples for proxy-fleet CLI tool.

This file demonstrates how to use the proxy-fleet command-line interface
for common proxy management and testing scenarios.
"""

import json
import os
import subprocess
from pathlib import Path


def run_command(cmd, description):
    """Run a shell command and display results"""
    print(f"\n� {description}")
    print(f"Command: {cmd}")
    print("-" * 50)

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"Error: {result.stderr}")
        return result.returncode == 0
    except Exception as e:
        print(f"Error running command: {e}")
        return False


def main():
    """Run basic usage examples"""
    print("🚀 Proxy Fleet CLI - Basic Usage Examples")
    print("=" * 60)

    # Example 1: Test proxies from a file
    print("\n📝 Example 1: Test proxy servers from file")
    run_command(
        "python -m proxy_fleet.cli.main --test-proxy-server examples/sample_proxies.txt --proxy-storage examples/demo_storage",
        "Testing proxy servers from file",
    )

    # Example 2: List all proxy statuses
    print("\n� Example 2: List all proxy server statuses")
    run_command(
        "python -m proxy_fleet.cli.main --list-proxy --proxy-storage examples/demo_storage",
        "Listing all proxy server statuses",
    )

    # Example 3: List only verified proxies
    print("\n📝 Example 3: List only verified/valid proxies")
    run_command(
        "python -m proxy_fleet.cli.main --list-proxy-verified --proxy-storage examples/demo_storage",
        "Listing only verified proxies",
    )

    # Example 4: Clean up failed proxies
    print("\n📝 Example 4: Remove failed proxies from storage")
    run_command(
        "python -m proxy_fleet.cli.main --remove-proxy-failed --proxy-storage examples/demo_storage",
        "Removing failed proxies from storage",
    )

    print("\n✅ All examples completed!")
    print("\nNext steps:")
    print("- Check the results in examples/demo_storage/")
    print("- Start the enhanced proxy server: proxy-fleet --enhanced-proxy-server")
    print(
        "- Use any HTTP client with the proxy: export http_proxy=http://127.0.0.1:8888"
    )
    print("Next steps:")
    print("- Check the results in examples/demo_storage/")
    print("- Start the enhanced proxy server: proxy-fleet --enhanced-proxy-server")
    print(
        "- Use any HTTP client with the proxy: export http_proxy=http://127.0.0.1:8888"
    )


if __name__ == "__main__":
    main()

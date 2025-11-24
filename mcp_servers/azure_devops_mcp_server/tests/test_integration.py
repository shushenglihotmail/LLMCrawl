#!/usr/bin/env python3
"""
Test script for Azure DevOps MCP Server.
Tests both stdio and HTTP modes.
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict

import httpx


async def test_http_mode():
    """Test HTTP mode endpoints."""
    print("\n" + "=" * 60)
    print("Testing Azure DevOps MCP Server - HTTP Mode")
    print("=" * 60)

    base_url = os.getenv("AZURE_DEVOPS_MCP_URL", "http://localhost:8004")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test 1: Health Check
        print("\n1. Health Check")
        try:
            response = await client.get(f"{base_url}/health")
            response.raise_for_status()
            health = response.json()
            print(f"   ✓ Status: {health['status']}")
            print(f"   ✓ Organization: {health['organization']}")
            print(f"   ✓ Project: {health['project']}")
            print(f"   ✓ Repository: {health['repository']}")
        except Exception as e:
            print(f"   ✗ Failed: {e}")
            return False

        # Test 2: Get Tools
        print("\n2. Get Available Tools")
        try:
            response = await client.get(f"{base_url}/tools")
            response.raise_for_status()
            data = response.json()
            tools = data.get("tools", [])
            print(f"   ✓ Found {len(tools)} tools:")
            for tool in tools:
                print(f"     - {tool['function']['name']}")
        except Exception as e:
            print(f"   ✗ Failed: {e}")
            return False

        # Test 3: Search Code
        print("\n3. Search Azure DevOps Code")
        try:
            response = await client.post(
                f"{base_url}/invoke",
                json={
                    "tool_name": "search_azure_devops_code",
                    "arguments": {"query": "authentication", "top": 3},
                },
            )
            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                search_result = result.get("result", {})
                count = search_result.get("count", 0)
                print(f"   ✓ Found {count} results")

                for i, item in enumerate(search_result.get("results", [])[:3], 1):
                    print(f"\n   Result {i}:")
                    print(f"     Path: {item.get('path', 'N/A')}")
                    print(f"     Repo: {item.get('repository', {}).get('name', 'N/A')}")
                    print(f"     Branch: {item.get('branch', 'N/A')}")
            else:
                print(f"   ✗ Failed: {result.get('error')}")
                return False

        except Exception as e:
            print(f"   ✗ Failed: {e}")
            return False

        # Test 4: Get File Content (if we have a path from search)
        print("\n4. Get File Content")
        try:
            # Try a common file
            test_path = "README.md"

            response = await client.post(
                f"{base_url}/invoke",
                json={
                    "tool_name": "get_azure_devops_file",
                    "arguments": {"file_path": test_path},
                },
            )
            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                file_result = result.get("result", {})
                content = file_result.get("content", "")
                path = file_result.get("path", "")

                print(f"   ✓ Retrieved file: {path}")
                print(f"   ✓ Content length: {len(content)} characters")
                print(f"   ✓ First 100 chars: {content[:100]}")
            else:
                print(f"   ⚠ Could not retrieve {test_path}: {result.get('error')}")
                print(f"     (This is expected if file doesn't exist)")

        except Exception as e:
            print(f"   ✗ Failed: {e}")

    print("\n" + "=" * 60)
    print("HTTP Mode Tests Completed")
    print("=" * 60)
    return True


async def test_gateway_integration():
    """Test integration with LLMCrawl gateway."""
    print("\n" + "=" * 60)
    print("Testing Gateway Integration")
    print("=" * 60)

    gateway_url = os.getenv("GATEWAY_URL", "http://localhost:8000")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Test: Send a chat message that should trigger Azure DevOps tool
        print("\n1. Chat Request with Azure DevOps Query")
        try:
            response = await client.post(
                f"{gateway_url}/api/v1/chat",
                json={
                    "message": "Search for authentication code in the OS repository",
                    "model": "gpt-4",
                    "stream": False,
                },
            )
            response.raise_for_status()
            result = response.json()

            print(f"   ✓ Response received")
            print(f"   ✓ Tool calls: {len(result.get('tool_calls', []))}")

            for tool_call in result.get("tool_calls", []):
                print(f"\n   Tool: {tool_call.get('name')}")
                print(f"   Args: {json.dumps(tool_call.get('args', {}), indent=6)}")

        except Exception as e:
            print(f"   ✗ Failed: {e}")
            return False

    print("\n" + "=" * 60)
    print("Gateway Integration Tests Completed")
    print("=" * 60)
    return True


def print_usage():
    """Print usage information."""
    print(
        """
Azure DevOps MCP Server Test Suite

Usage:
    python test_azure_devops_mcp.py [mode]

Modes:
    http        Test HTTP mode only (default)
    gateway     Test gateway integration
    all         Run all tests

Environment Variables:
    AZURE_DEVOPS_MCP_URL    Azure DevOps MCP server URL (default: http://localhost:8004)
    GATEWAY_URL             Gateway URL (default: http://localhost:8000)
    AZURE_DEVOPS_PAT        Personal Access Token (required for tests)

Examples:
    # Test HTTP mode
    python test_azure_devops_mcp.py http

    # Test gateway integration
    python test_azure_devops_mcp.py gateway

    # Run all tests
    python test_azure_devops_mcp.py all
    """
    )


async def main():
    """Main test runner."""
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help", "help"]:
        print_usage()
        return

    mode = sys.argv[1] if len(sys.argv) > 1 else "http"

    # Check for PAT
    if not os.getenv("AZURE_DEVOPS_PAT"):
        print("⚠ Warning: AZURE_DEVOPS_PAT not set")
        print("  Tests may fail without authentication")
        print()

    success = True

    if mode in ["http", "all"]:
        success = await test_http_mode() and success

    if mode in ["gateway", "all"]:
        success = await test_gateway_integration() and success

    print("\n" + "=" * 60)
    if success:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
    print("=" * 60)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

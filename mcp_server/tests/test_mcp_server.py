"""
Test script for MCP server local file operations.
"""

import asyncio
import json

import httpx


async def test_mcp_server():
    """Test MCP server endpoints."""
    base_url = "http://localhost:8003"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test 1: Health check
        print("=" * 60)
        print("Test 1: Health Check")
        print("=" * 60)
        response = await client.get(f"{base_url}/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

        # Test 2: Get available tools
        print("\n" + "=" * 60)
        print("Test 2: Get Available Tools")
        print("=" * 60)
        response = await client.get(f"{base_url}/tools")
        data = response.json()
        print(f"Status: {response.status_code}")
        print(f"Number of tools: {len(data.get('tools', []))}")
        for tool in data.get("tools", []):
            print(
                f"  - {tool['function']['name']}: "
                f"{tool['function']['description'][:80]}..."
            )

        # Test 3: List files in root folder
        print("\n" + "=" * 60)
        print("Test 3: List Files")
        print("=" * 60)
        response = await client.post(
            f"{base_url}/invoke",
            json={
                "tool_name": "list_files",
                "arguments": {"folder_path": ".", "recursive": False},
            },
        )
        data = response.json()
        print(f"Status: {response.status_code}")
        print(f"Success: {data.get('success')}")
        if data.get("success"):
            result = data.get("result", {})
            print(f"Files found: {result.get('count', 0)}")
            for file in result.get("files", [])[:5]:  # Show first 5
                print(f"  - {file['name']} ({file['size']} bytes)")

        # Test 4: Try to read a file (will fail if no files exist)
        print("\n" + "=" * 60)
        print("Test 4: Read File (will skip if no files)")
        print("=" * 60)
        # First, check if there are any files
        if data.get("success") and data["result"].get("files"):
            first_file = data["result"]["files"][0]["path"]
            response = await client.post(
                f"{base_url}/invoke",
                json={
                    "tool_name": "read_local_file",
                    "arguments": {"file_path": first_file},
                },
            )
            read_data = response.json()
            print(f"Status: {response.status_code}")
            print(f"Success: {read_data.get('success')}")
            if read_data.get("success"):
                result = read_data.get("result", {})
                content = result.get("content", "")
                print(f"File: {result.get('name')}")
                print(f"Size: {result.get('size')} bytes")
                print(f"Content preview: {content[:200]}...")
        else:
            print("No files to read. Create some test files in ./data/files/")

        # Test 5: Index files
        print("\n" + "=" * 60)
        print("Test 5: Index Files")
        print("=" * 60)
        response = await client.post(
            f"{base_url}/invoke",
            json={
                "tool_name": "index_files",
                "arguments": {
                    "folder_path": ".",
                    "recursive": True,
                    "extensions": [],
                },
            },
        )
        data = response.json()
        print(f"Status: {response.status_code}")
        print(f"Success: {data.get('success')}")
        if data.get("success"):
            result = data.get("result", {})
            print(f"Indexed: {result.get('indexed', 0)} files")
            print(f"Skipped: {result.get('skipped', 0)} files")
            print(f"Total: {result.get('total', 0)} files")

        # Test 6: Search file content (only if files were indexed)
        if data.get("success") and data["result"].get("indexed", 0) > 0:
            print("\n" + "=" * 60)
            print("Test 6: Search File Content")
            print("=" * 60)
            response = await client.post(
                f"{base_url}/invoke",
                json={
                    "tool_name": "search_file_content",
                    "arguments": {"query": "configuration", "top_k": 3},
                },
            )
            search_data = response.json()
            print(f"Status: {response.status_code}")
            print(f"Success: {search_data.get('success')}")
            if search_data.get("success"):
                result = search_data.get("result", {})
                print(f"Query: {result.get('query')}")
                print(f"Results: {result.get('count', 0)}")
                for hit in result.get("results", []):
                    print(f"  - {hit['file_name']} (score: {hit['score']:.3f})")
                    print(f"    {hit['text_snippet'][:100]}...")
        else:
            print("\n" + "=" * 60)
            print("Test 6: Search File Content - SKIPPED")
            print("=" * 60)
            print(
                "No files indexed. Add some text files to ./data/files/ "
                "and rerun tests."
            )


if __name__ == "__main__":
    print("Testing MCP Server")
    print("=" * 60)
    print("Ensure the MCP server is running on http://localhost:8003")
    print("and ./data/files/ contains some test files")
    print("=" * 60)
    asyncio.run(test_mcp_server())

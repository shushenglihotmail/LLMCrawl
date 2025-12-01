#!/usr/bin/env python3
"""
Test script for Azure DevOps URI parsing and Code Search.

Usage:
    python test_azdo_uri.py "azdo:/onecore/vm/compute:HCS ext:md"
    python test_azdo_uri.py "azdo:/vm/compute:ext:xml"
    python test_azdo_uri.py "azdo:/:file:*manifest*.xml"
    python test_azdo_uri.py --test-all
"""

import argparse
import asyncio
import sys
import os

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "gateway"))

from gateway.utils.azdo_uri import parse_azdo_uri, is_azdo_uri, AzdoUri


def print_separator(title: str = ""):
    """Print a separator line."""
    print("\n" + "=" * 60)
    if title:
        print(f"  {title}")
        print("=" * 60)


def test_parse_uri(uri: str) -> AzdoUri | None:
    """Test parsing a single URI and print results."""
    print(f"\nInput URI: {uri}")
    print(f"  is_azdo_uri: {is_azdo_uri(uri)}")

    result = parse_azdo_uri(uri)

    if result:
        print(f"  ✅ Parsed successfully:")
        print(f"     path:        '{result.path}'")
        print(f"     search_text: '{result.search_text}'")
        print(f"     project:     '{result.project}'")
        print(f"     repository:  '{result.repository}'")
        print(f"     branch:      '{result.branch}'")
        print(f"     is_search:   {result.is_search_query()}")
        print(f"     has_repo:    {result.has_repo_override()}")
    else:
        print(f"  ❌ Failed to parse URI")

    return result


def run_all_tests():
    """Run all test cases."""
    print_separator("Azure DevOps URI Parser Tests")

    test_cases = [
        # Basic search patterns
        (
            "azdo:/onecore/vm/compute:HCS ext:md",
            {
                "path": "/onecore/vm/compute",
                "search_text": "HCS ext:md",
                "project": None,
                "is_search": True,
            },
        ),
        (
            "azdo:/vm/compute:ext:xml",
            {
                "path": "/vm/compute",
                "search_text": "ext:xml",
                "project": None,
                "is_search": True,
            },
        ),
        (
            "azdo:/:ext:cpp",
            {
                "path": "/",
                "search_text": "ext:cpp",
                "project": None,
                "is_search": True,
            },
        ),
        (
            "azdo:/path:file:*manifest*.xml",
            {
                "path": "/path",
                "search_text": "file:*manifest*.xml",
                "project": None,
                "is_search": True,
            },
        ),
        # Search with spaces in search text
        (
            "azdo:/src:keyword1 AND keyword2 ext:cs",
            {
                "path": "/src",
                "search_text": "keyword1 AND keyword2 ext:cs",
                "project": None,
                "is_search": True,
            },
        ),
        (
            "azdo:/docs:(term1 OR term2) ext:md",
            {
                "path": "/docs",
                "search_text": "(term1 OR term2) ext:md",
                "project": None,
                "is_search": True,
            },
        ),
        # With space after colon
        (
            "azdo:/onecore/vm/compute: HCS ext:md",
            {
                "path": "/onecore/vm/compute",
                "search_text": "HCS ext:md",
                "project": None,
                "is_search": True,
            },
        ),
        # With project/repo override
        (
            "azdo://OS/os.2020/src:ext:h",
            {
                "path": "/src",
                "search_text": "ext:h",
                "project": "OS",
                "repository": "os.2020",
                "is_search": True,
            },
        ),
        (
            "azdo://OneCore/WindowsCompositionData/path:file:*.config?branch=main",
            {
                "path": "/path",
                "search_text": "file:*.config",
                "project": "OneCore",
                "repository": "WindowsCompositionData",
                "branch": "main",
                "is_search": True,
            },
        ),
        # Direct file paths (no search)
        (
            "azdo:/path/to/file.cpp",
            {
                "path": "/path/to/file.cpp",
                "search_text": None,
                "project": None,
                "is_search": False,
            },
        ),
        (
            "azdo://OS/os.2020/src/main.cpp?branch=main",
            {
                "path": "/src/main.cpp",
                "search_text": None,
                "project": "OS",
                "repository": "os.2020",
                "branch": "main",
                "is_search": False,
            },
        ),
        # Edge cases
        (
            "azdo:/",
            {
                "path": "/",
                "search_text": None,
                "project": None,
                "is_search": False,
            },
        ),
        (
            "azdo:/:*",
            {
                "path": "/",
                "search_text": "*",
                "project": None,
                "is_search": True,
            },
        ),
    ]

    passed = 0
    failed = 0

    for uri, expected in test_cases:
        print(f"\n--- Test: {uri} ---")
        result = test_parse_uri(uri)

        # Validate results
        if result:
            errors = []
            if result.path != expected.get("path"):
                errors.append(
                    f"path: expected '{expected.get('path')}', got '{result.path}'"
                )
            if result.search_text != expected.get("search_text"):
                errors.append(
                    f"search_text: expected '{expected.get('search_text')}', got '{result.search_text}'"
                )
            if result.project != expected.get("project"):
                errors.append(
                    f"project: expected '{expected.get('project')}', got '{result.project}'"
                )
            if expected.get("repository") and result.repository != expected.get(
                "repository"
            ):
                errors.append(
                    f"repository: expected '{expected.get('repository')}', got '{result.repository}'"
                )
            if expected.get("branch") and result.branch != expected.get("branch"):
                errors.append(
                    f"branch: expected '{expected.get('branch')}', got '{result.branch}'"
                )
            if result.is_search_query() != expected.get("is_search", False):
                errors.append(
                    f"is_search: expected {expected.get('is_search')}, got {result.is_search_query()}"
                )

            if errors:
                print(f"  ⚠️  VALIDATION ERRORS:")
                for e in errors:
                    print(f"      - {e}")
                failed += 1
            else:
                print(f"  ✅ PASSED")
                passed += 1
        else:
            print(f"  ❌ FAILED - parse returned None")
            failed += 1

    print_separator("Test Summary")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Total:  {len(test_cases)}")

    return failed == 0


async def test_search_api(uri: str):
    """Test the actual Azure DevOps Code Search API with parsed URI."""
    print_separator("Testing Azure DevOps Code Search API")

    result = parse_azdo_uri(uri)
    if not result or not result.is_search_query():
        print(f"❌ URI is not a valid search query: {uri}")
        return

    print(f"Parsed URI:")
    print(f"  path:        {result.path}")
    print(f"  search_text: {result.search_text}")

    # Try to import and use the Azure DevOps MCP client
    try:
        import httpx

        # Call the MCP server's invoke endpoint
        mcp_url = os.environ.get("AZURE_DEVOPS_MCP_URL", "http://localhost:8004")

        arguments = {
            "search_text": result.search_text,
            "path": result.path,
        }
        if result.project:
            arguments["project"] = result.project
        if result.repository:
            arguments["repository"] = result.repository
        if result.branch:
            arguments["branch"] = result.branch

        print(f"\nCalling MCP server at {mcp_url}/invoke")
        print(f"Arguments: {arguments}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{mcp_url}/invoke",
                json={
                    "tool_name": "search_azure_devops_code",
                    "arguments": arguments,
                },
            )
            response.raise_for_status()
            data = response.json()

        print(f"\nResponse:")
        if data.get("success"):
            result_data = data.get("result", {})
            results = result_data.get("results", [])
            print(f"  ✅ Success! Found {len(results)} results")
            for i, r in enumerate(results[:10]):  # Show first 10
                print(f"    {i+1}. {r.get('file_path', r.get('path', 'unknown'))}")
            if len(results) > 10:
                print(f"    ... and {len(results) - 10} more")
        else:
            print(f"  ❌ Search failed: {data}")

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure httpx is installed: pip install httpx")
    except httpx.ConnectError:
        print(f"❌ Cannot connect to MCP server at {mcp_url}")
        print("   Make sure the Azure DevOps MCP server is running")
    except Exception as e:
        print(f"❌ Error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Test Azure DevOps URI parsing and Code Search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_azdo_uri.py "azdo:/onecore/vm/compute:HCS ext:md"
  python test_azdo_uri.py "azdo:/vm/compute:ext:xml"
  python test_azdo_uri.py --test-all
  python test_azdo_uri.py --api "azdo:/src:ext:cpp"
        """,
    )
    parser.add_argument(
        "uri", nargs="?", help="Azure DevOps URI to parse (e.g., 'azdo:/path:ext:xml')"
    )
    parser.add_argument("--test-all", action="store_true", help="Run all test cases")
    parser.add_argument(
        "--api",
        metavar="URI",
        help="Test the actual Azure DevOps Code Search API with given URI",
    )

    args = parser.parse_args()

    if args.test_all:
        success = run_all_tests()
        sys.exit(0 if success else 1)
    elif args.api:
        asyncio.run(test_search_api(args.api))
    elif args.uri:
        test_parse_uri(args.uri)
    else:
        parser.print_help()
        print("\n" + "=" * 60)
        print("Quick test with sample URIs:")
        print("=" * 60)
        test_parse_uri("azdo:/onecore/vm/compute:HCS ext:md")
        test_parse_uri("azdo:/vm/compute:ext:xml")


if __name__ == "__main__":
    main()

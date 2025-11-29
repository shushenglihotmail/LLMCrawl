#!/usr/bin/env python
"""
Test script for _expand_paths() and _gather_files() functions.

Usage:
    python test_expand_paths.py <path>                    # Expand paths only
    python test_expand_paths.py <path> --gather           # Expand and gather file content

Examples:
    python test_expand_paths.py "gateway/"
    python test_expand_paths.py "gateway/**"
    python test_expand_paths.py "*.py"
    python test_expand_paths.py "gateway/*.py"
    python test_expand_paths.py "azdo:/src/folder/" --gather
    python test_expand_paths.py "azdo:/src/folder/**" --gather
"""

import argparse
import asyncio
import logging
import os
import sys

# Enable logging to see debug info
logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")

# Add project root to path (two levels up from gateway/tests)
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, project_root)

from gateway.agents import AgentConfig
from gateway.routers.agent import _expand_paths, _gather_files
from gateway.utils.azdo_uri import is_azdo_uri, parse_azdo_uri


def create_agent_config() -> AgentConfig:
    """Create agent config with default MCP URLs."""
    return AgentConfig(
        mcp_url=os.getenv("MCP_URL", "http://localhost:8003"),
        crawler_url=os.getenv("CRAWLER_URL", "http://localhost:8001"),
        indexer_url=os.getenv("INDEXER_URL", "http://localhost:8002"),
        azure_devops_mcp_url=os.getenv("AZURE_DEVOPS_MCP_URL", "http://localhost:8004"),
    )


async def test_expand(path: str) -> list[str]:
    """Test expanding a single path."""
    agent = create_agent_config()

    print(f"\n{'='*60}")
    print(f"Testing path expansion for: {path}")
    print(f"{'='*60}")
    print(f"\nMCP URL: {agent.mcp_url}")
    print(f"Azure DevOps MCP URL: {agent.azure_devops_mcp_url}")

    # Debug: Show parsed URI info
    if is_azdo_uri(path):
        parsed = parse_azdo_uri(path)
        print(f"\nParsed azdo URI:")
        print(f"  path: '{parsed.path}'")
        print(f"  project: {parsed.project}")
        print(f"  repository: {parsed.repository}")
        print(f"  branch: {parsed.branch}")
        print(f"  ends with '/': {parsed.path.endswith('/')}")
        print(f"  ends with '/**': {parsed.path.endswith('/**')}")

    print(f"\nExpanding...")

    try:
        expanded = await _expand_paths(agent, [path])

        print(f"\nExpanded to {len(expanded)} file(s):")
        print("-" * 40)
        for i, file_path in enumerate(expanded, 1):
            print(f"  {i:3}. {file_path}")

        if not expanded:
            print("  (no files found)")

        return expanded

    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()
        return []


async def test_gather(paths: list[str]):
    """Test gathering file content from expanded paths."""
    if not paths:
        print("\nNo paths to gather content from.")
        return

    agent = create_agent_config()
    # Initialize with the key we'll use for gathering
    context_gathered = {"test_files": 0}

    print(f"\n{'='*60}")
    print(f"Gathering content from {len(paths)} file(s)")
    print(f"{'='*60}")

    try:
        contents = await _gather_files(
            agent, paths, context_gathered, "test_files", "File"
        )

        print(f"\nGathered {context_gathered['test_files']} file(s) successfully:")
        print("-" * 60)

        for i, content in enumerate(contents, 1):
            # Content format is "File: <path>\n\n<content>"
            # Split header from content
            lines = content.split("\n", 2)
            header = lines[0] if lines else "Unknown"
            file_content = lines[2] if len(lines) > 2 else "(empty or no content)"

            print(f"\n[{i}] {header}")
            print("-" * 40)
            # Truncate long content for display
            if len(file_content) > 2000:
                print(file_content[:2000])
                print(f"\n... (truncated, {len(file_content)} total chars)")
            else:
                print(file_content if file_content else "(empty)")
            print("-" * 40)

        if not contents:
            print("  (no content gathered)")

    except Exception as e:
        print(f"\nError gathering content: {e}")
        import traceback

        traceback.print_exc()


async def main():
    parser = argparse.ArgumentParser(
        description="Test path expansion and file gathering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("path", help="Path to expand (supports local and azdo: paths)")
    parser.add_argument(
        "--gather",
        "-g",
        action="store_true",
        help="Also gather and display file content",
    )

    args = parser.parse_args()

    # First, expand the paths
    expanded = await test_expand(args.path)

    # If --gather flag is set, also gather file content
    if args.gather and expanded:
        await test_gather(expanded)


if __name__ == "__main__":
    asyncio.run(main())

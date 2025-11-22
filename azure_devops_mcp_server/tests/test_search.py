"""
Test script for Azure DevOps file search with command-line interface.

Usage:
    python test_search.py --path /src/MergedComponents --filter "Azure ext:json"
    python test_search.py --path /src/MergedComponents --filter "Azure AND connection ext:json"
    python test_search.py --path /src/MergedComponents --filter '"Azure devops" AND file:*.cpp'
    python test_search.py --filter "ext:yml" --recursive
    python test_search.py --get-file ".gitignore"
"""

import argparse
import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from azure_devops_mcp_server.azure_client import AzureDevOpsClient


def parse_filter(filter_str: str) -> dict:
    """
    Parse filter string into components.

    Examples:
        "Azure ext:json" -> {"keyword": "Azure", "extension": "json"}
        "file:*.cpp ext:cpp" -> {"file_pattern": "*.cpp", "extension": "cpp"}
        "path:**/test/** ext:yml" -> {"path_pattern": "**/test/**", "extension": "yml"}
    """
    filters = {
        "path_pattern": None,
        "file_pattern": None,
        "extension": None,
        "keyword": None,
    }

    if not filter_str:
        return filters

    # Split by spaces but respect quotes
    parts = []
    current = []
    in_quotes = False

    for char in filter_str:
        if char == '"':
            in_quotes = not in_quotes
        elif char == " " and not in_quotes:
            if current:
                parts.append("".join(current))
                current = []
        else:
            current.append(char)

    if current:
        parts.append("".join(current))

    # Process parts
    for part in parts:
        part = part.strip()
        if not part or part.upper() in ["AND", "OR"]:  # Skip logical operators for now
            continue

        if part.startswith("path:"):
            filters["path_pattern"] = part[5:]
        elif part.startswith("file:"):
            filters["file_pattern"] = part[5:]
        elif part.startswith("ext:"):
            filters["extension"] = part[4:]
        else:
            # Treat as keyword
            if filters["keyword"]:
                filters["keyword"] += " " + part
            else:
                filters["keyword"] = part

    return filters


async def search_files(args):
    """Execute file search based on arguments."""

    # Get PAT from environment
    pat = os.environ.get("AZURE_DEVOPS_PAT")
    if not pat:
        print("❌ Error: AZURE_DEVOPS_PAT environment variable not set")
        sys.exit(1)

    # Initialize client
    client = AzureDevOpsClient(
        organization=args.organization,
        project=args.project,
        repository=args.repository,
        pat=pat,
        branch=args.branch,
        max_results=args.max_results,
    )

    # Authenticate
    if not await client.authenticate(use_interactive=False):
        print("❌ Authentication failed")
        sys.exit(1)

    # Parse filters
    filters = parse_filter(args.filter) if args.filter else {}

    # Override with path if specified separately
    if args.path:
        filters["path_pattern"] = args.path

    # Execute search
    print(f"\n🔍 Searching in {args.organization}/{args.project}/{args.repository}")
    print(f"   Branch: {args.branch}")
    print(f"   Recursive: {args.recursive}")
    if args.path or filters.get("path_pattern"):
        print(f"   Path: {args.path or filters.get('path_pattern')}")
    if filters.get("file_pattern"):
        print(f"   File pattern: {filters['file_pattern']}")
    if filters.get("extension"):
        print(f"   Extension: {filters['extension']}")
    if filters.get("keyword"):
        print(f"   Keyword: {filters['keyword']}")
    print()

    results = await client.search_files(
        path_pattern=args.path or filters.get("path_pattern"),
        file_pattern=filters.get("file_pattern"),
        extension=filters.get("extension"),
        keyword=filters.get("keyword"),
        branch=args.branch,
        max_results=args.max_results,
        recursive=args.recursive,
    )

    # Display results
    print(f"✓ Found {len(results)} file(s):")
    print("=" * 80)

    for i, result in enumerate(results, 1):
        print(f"{i:3}. {result['path']}")
        if args.verbose:
            print(f"     Size: {result.get('size', 0)} bytes")
            print(f"     Object ID: {result.get('objectId', 'N/A')}")

    if not results:
        print("No files found matching the criteria.")


async def get_file(args):
    """Get file content."""

    # Get PAT from environment
    pat = os.environ.get("AZURE_DEVOPS_PAT")
    if not pat:
        print("❌ Error: AZURE_DEVOPS_PAT environment variable not set")
        sys.exit(1)

    # Initialize client
    client = AzureDevOpsClient(
        organization=args.organization,
        project=args.project,
        repository=args.repository,
        pat=pat,
        branch=args.branch,
    )

    # Authenticate
    if not await client.authenticate(use_interactive=False):
        print("❌ Authentication failed")
        sys.exit(1)

    # Get file content
    print(f"\n📄 Getting file: {args.get_file}")
    print(f"   Repository: {args.organization}/{args.project}/{args.repository}")
    print(f"   Branch: {args.branch}")
    print()

    file_content = await client.get_file_content(args.get_file, args.branch)

    if file_content:
        print(f"✓ File: {file_content.get('file_path', 'unknown')}")
        print(f"  Size: {file_content.get('size', 0)} bytes")
        print(f"  Content Type: {file_content.get('content_type', 'unknown')}")
        print("=" * 80)

        content = file_content.get("content", "")
        if args.max_lines:
            lines = content.split("\n")
            content = "\n".join(lines[: args.max_lines])
            if len(lines) > args.max_lines:
                print(
                    f"... (showing first {args.max_lines} lines of {len(lines)} total)"
                )
                print()

        print(content)
    else:
        print("❌ Failed to get file content")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Azure DevOps file search and retrieval tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search for files with extension
  python test_search.py --filter "ext:json"

  # Search in specific path
  python test_search.py --path /src/MergedComponents --filter "Azure ext:json"

  # Search with file pattern
  python test_search.py --filter "file:*.cpp ext:cpp"

  # Search recursively
  python test_search.py --path /src --filter "ext:yml" --recursive

  # Get file content
  python test_search.py --get-file ".gitignore"

  # Get file content with line limit
  python test_search.py --get-file "README.md" --max-lines 50
        """,
    )

    # Repository configuration
    parser.add_argument(
        "--organization",
        type=str,
        default=os.getenv("AZURE_DEVOPS_ORG", "microsoft"),
        help="Azure DevOps organization (default: microsoft)",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=os.getenv("AZURE_DEVOPS_PROJECT", "OS"),
        help="Azure DevOps project (default: OS)",
    )
    parser.add_argument(
        "--repository",
        type=str,
        default=os.getenv("AZURE_DEVOPS_REPO", "os.2020"),
        help="Azure DevOps repository (default: os.2020)",
    )
    parser.add_argument(
        "--branch",
        type=str,
        default=os.getenv("AZURE_DEVOPS_BRANCH", "official/rs_sparc_ctr_exp"),
        help="Branch name (default: official/rs_sparc_ctr_exp)",
    )

    # Search parameters
    parser.add_argument(
        "--path",
        type=str,
        help="Path pattern (e.g., /src/MergedComponents, /src/**, **/**/test/**)",
    )
    parser.add_argument(
        "--filter",
        type=str,
        help='Filter string (e.g., "Azure ext:json", "file:*.cpp ext:cpp")',
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search recursively in subdirectories (default: False)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Maximum number of results (default: 50)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed information",
    )

    # File retrieval
    parser.add_argument(
        "--get-file",
        type=str,
        help="Get content of specific file (e.g., .gitignore, src/main.cpp)",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        help="Maximum number of lines to display from file content",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.get_file:
        asyncio.run(get_file(args))
    elif args.filter or args.path:
        asyncio.run(search_files(args))
    else:
        parser.print_help()
        print("\n❌ Error: Either --filter, --path, or --get-file must be specified")
        sys.exit(1)


if __name__ == "__main__":
    main()

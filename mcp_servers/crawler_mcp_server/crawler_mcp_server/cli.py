"""
Simple CLI for crawler MCP server.

Just an MCP wrapper that connects to existing LLMCrawl crawler service.
"""

import argparse
import asyncio
import sys


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Crawler MCP Server - Connect LLMCrawl to VS Code AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run MCP server (default: connects to http://localhost:8001)
  crawler-mcp-server

  # Connect to custom crawler URL
  crawler-mcp-server --base-url http://my-crawler:8001

  # Show version
  crawler-mcp-server --version
        """,
    )

    parser.add_argument(
        "--base-url",
        default="http://localhost:8001",
        help="Crawler service URL (default: http://localhost:8001)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Request timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version and exit",
    )

    args = parser.parse_args()

    if args.version:
        from . import __version__

        print(f"crawler-mcp-server {__version__}")
        return 0

    # Run MCP server
    from .stdio_server import run_stdio_server

    try:
        asyncio.run(run_stdio_server(base_url=args.base_url, timeout_s=args.timeout))
        return 0
    except KeyboardInterrupt:
        print("\nShutting down...")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

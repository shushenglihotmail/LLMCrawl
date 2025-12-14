"""CLI entry point for the Crawler MCP Server."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Crawler MCP Server (stdio) - forwards to LLMCrawl crawler HTTP API"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.getenv("CRAWLER_MCP_BASE_URL", "http://localhost:8001"),
        help="Base URL of the crawler service (default: http://localhost:8001)",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=float(os.getenv("CRAWLER_MCP_TIMEOUT_S", "120")),
        help="HTTP timeout in seconds (default: 120)",
    )

    args = parser.parse_args()

    from .stdio_server import run_stdio_server

    asyncio.run(run_stdio_server(base_url=args.base_url, timeout_s=args.timeout_s))


if __name__ == "__main__":
    main()

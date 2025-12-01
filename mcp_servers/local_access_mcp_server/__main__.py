"""
Main entry point for Local Access MCP Server.
Supports both stdio (VS Code) and HTTP (LLMCrawl) modes.
"""

import argparse
import asyncio
import logging
import os
import sys


def main():
    """Main entry point for the MCP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        description="Local Access MCP Server - Dual Mode (stdio/HTTP)"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["stdio", "http"],
        default=os.getenv("MCP_MODE", "http"),
        help="Server mode: stdio (VS Code) or http (LLMCrawl gateway)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8003")),
        help="HTTP server port (only for HTTP mode)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("MCP_HOST", "0.0.0.0"),
        help="HTTP server host (only for HTTP mode)",
    )
    parser.add_argument(
        "--root-folder",
        type=str,
        default=os.getenv("MCP_ROOT_FOLDER", "/data/files"),
        help="Root folder for file operations",
    )

    args = parser.parse_args()

    if args.mode == "stdio":
        # Run in stdio mode for VS Code
        from .stdio_server import run_stdio_server

        logger.info("Starting Local Access MCP Server in stdio mode")
        asyncio.run(run_stdio_server(args.root_folder))
    else:
        # Run in HTTP mode for LLMCrawl
        import uvicorn

        from .main import ROOT_FOLDER, app

        # Override config with args
        os.environ["MCP_ROOT_FOLDER"] = args.root_folder

        logger.info(
            f"Starting Local Access MCP Server in HTTP mode on {args.host}:{args.port}"
        )
        logger.info(f"Root folder: {args.root_folder}")

        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()

"""CLI entry point for the Crawler MCP Server.

This module provides the main entry point for the crawler-mcp-server command.
It supports multiple subcommands:
  - start/stop/restart: Manage Docker containers
  - status: Check service health
  - logs: View container logs
  - auth: Authenticate to internal sites
  - mcp: Run MCP server for VS Code integration
  - serve: Run crawler service natively (without Docker)

For backward compatibility, running without a subcommand starts the MCP server.
"""

from __future__ import annotations


def main() -> None:
    """Main entry point - delegates to the CLI module."""
    from .cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()

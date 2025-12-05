#!/usr/bin/env python3
"""
LLMCrawl CLI - Main entry point

Provides subcommands for deployment, authentication, and WCD bridge.

Usage:
    llmcrawl deploy --init              # Initialize deployment folder
    llmcrawl deploy --up                # Start all services
    llmcrawl auth <url>                 # Authenticate to internal site
    llmcrawl wcd-bridge --build <path>  # Start WCD bridge service
"""

import sys


def main() -> None:
    """Main entry point for llmcrawl CLI."""
    if len(sys.argv) < 2 or sys.argv[1] in ["-h", "--help"]:
        print_help()
        sys.exit(0)

    if sys.argv[1] in ["-v", "--version"]:
        print("llmcrawl version 1.0.0")
        sys.exit(0)

    command = sys.argv[1]
    # Reconstruct sys.argv for the subcommand
    sys.argv = ["llmcrawl " + command] + sys.argv[2:]

    if command == "deploy":
        from llmcrawl_cli.deploy import main as deploy_main

        deploy_main()

    elif command == "auth":
        from llmcrawl_cli.auth import main as auth_main

        auth_main()

    elif command == "wcd-bridge":
        from llmcrawl_cli.wcd_bridge import main as wcd_main

        wcd_main()

    else:
        print(f"Unknown command: {command}")
        print_help()
        sys.exit(1)


def print_help() -> None:
    """Print help message."""
    print(
        """usage: llmcrawl [-h] [--version] {deploy,auth,wcd-bridge} ...

LLMCrawl - Web RAG System CLI

positional arguments:
  {deploy,auth,wcd-bridge}
                        Available commands
    deploy              Manage LLMCrawl deployment (Docker Compose)
    auth                Authenticate to internal sites for crawling
    wcd-bridge          Start Windows Composition Database bridge

options:
  -h, --help            show this help message and exit
  --version, -v         Show version information

Examples:
  llmcrawl deploy --init                    Initialize deployment folder
  llmcrawl deploy --up                      Start all services
  llmcrawl deploy --down                    Stop all services
  llmcrawl auth https://www.osgwiki.com     Authenticate to internal site
  llmcrawl wcd-bridge --build "\\\\winbuilds\\release\\..."
"""
    )


if __name__ == "__main__":
    main()

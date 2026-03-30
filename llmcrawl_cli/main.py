#!/usr/bin/env python3
"""
LLMCrawl CLI - Main entry point

Provides subcommands for deployment, authentication, WCD bridge, and Claude bridge.

Usage:
    llmcrawl deploy --init              # Initialize deployment folder
    llmcrawl deploy --up                # Start all services
    llmcrawl auth <url>                 # Authenticate to internal site
    llmcrawl wcd-bridge --build <path>  # Start WCD bridge service
    llmcrawl claude-bridge              # Start Claude bridge service
"""

import sys


def main() -> None:
    """Main entry point for llmcrawl CLI."""
    if len(sys.argv) < 2 or sys.argv[1] in ["-h", "--help"]:
        print_help()
        sys.exit(0)

    if sys.argv[1] in ["-v", "--version"]:
        print("llmcrawl version 1.0.4")
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

    elif command == "claude-bridge":
        from llmcrawl_cli.claude_bridge import main as claude_bridge_main

        claude_bridge_main()

    elif command == "copilot-bridge":
        from llmcrawl_cli.copilot_bridge import main as copilot_bridge_main

        copilot_bridge_main()

    else:
        print(f"Unknown command: {command}")
        print_help()
        sys.exit(1)


def print_help() -> None:
    """Print help message."""
    print(
        """usage: llmcrawl [-h] [--version] {deploy,auth,wcd-bridge,claude-bridge,copilot-bridge} ...

LLMCrawl - Web RAG System CLI

positional arguments:
  {deploy,auth,wcd-bridge,claude-bridge,copilot-bridge}
                        Available commands
    deploy              Manage LLMCrawl deployment (Docker Compose)
    auth                Authenticate to internal sites for crawling
    wcd-bridge          Start Windows Composition Database bridge
    claude-bridge       Start Claude Code CLI bridge for LLM routing
    copilot-bridge      Start GitHub Copilot CLI bridge for LLM routing

options:
  -h, --help            show this help message and exit
  --version, -v         Show version information

Examples:
  llmcrawl deploy --init                    Initialize deployment folder
  llmcrawl deploy --up                      Start all services
  llmcrawl deploy --down                    Stop all services
  llmcrawl deploy --status                  Check service status
  llmcrawl deploy --health                  Check service health endpoints
  llmcrawl auth https://www.osgwiki.com     Authenticate to internal site
  llmcrawl wcd-bridge --build "\\\\winbuilds\\release\\..."
  llmcrawl claude-bridge                    Start Claude Bridge (port 8006)
  llmcrawl claude-bridge --port 8007        Start Claude Bridge on custom port
  llmcrawl copilot-bridge                   Start Copilot Bridge (port 8009)
  llmcrawl copilot-bridge --port 8010       Start Copilot Bridge on custom port
"""
    )


if __name__ == "__main__":
    main()

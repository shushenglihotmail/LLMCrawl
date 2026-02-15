#!/usr/bin/env python3
"""
LLMCrawl Claude Bridge CLI

Starts the Claude Bridge service on the host, enabling Docker-based gateway
containers to route LLM requests through the Claude Code CLI.

Usage:
    llmcrawl claude-bridge                  # Start with defaults (port 8006)
    llmcrawl claude-bridge --port 8007      # Start on custom port
    llmcrawl claude-bridge --claude-path /path/to/claude  # Custom CLI path
"""

import os
import signal
import sys
from pathlib import Path


def get_tools_dir() -> Path:
    """Get the tools directory from the installed package."""
    package_dir = Path(__file__).parent.parent
    tools_dir = package_dir / "tools"

    if tools_dir.exists():
        return tools_dir

    # Fallback: try to find it in common locations
    for candidate in [
        Path.cwd() / "tools",
        Path(__file__).parent.parent.parent / "tools",
    ]:
        if candidate.exists():
            return candidate

    return tools_dir


def find_claude_cli() -> str | None:
    """
    Find the Claude CLI executable.

    Searches in order:
    1. CLAUDE_CLI_PATH environment variable
    2. ~/.claude-cli/currentVersion/claude.exe (Windows)
    3. System PATH (claude / claude.exe)
    """
    # Check env var first
    env_path = os.environ.get("CLAUDE_CLI_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    # Windows default location
    if sys.platform == "win32":
        default = os.path.join(
            os.environ.get("USERPROFILE", ""),
            ".claude-cli",
            "currentVersion",
            "claude.exe",
        )
        if os.path.isfile(default):
            return default

    # Check system PATH
    import shutil

    which = shutil.which("claude")
    if which:
        return which

    return None


def main() -> None:
    """Main entry point for Claude Bridge CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="llmcrawl claude-bridge",
        description="Start the Claude Bridge service for LLM request routing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start with defaults (port 8006)
  llmcrawl claude-bridge

  # Start on a custom port
  llmcrawl claude-bridge --port 8007

  # Specify Claude CLI path explicitly
  llmcrawl claude-bridge --claude-path "C:\\Users\\me\\.claude-cli\\currentVersion\\claude.exe"

Prerequisites:
  - Claude Code CLI installed (claude.exe / claude)
  - Docker containers running (gateway needs to reach this bridge)

The bridge service:
  - Runs on port 8006 by default
  - Accepts chat completion requests from the gateway container
  - Routes them through claude.exe subprocess
  - Must remain running while using Claude models in LLMCrawl

Configure in .env:
  CLAUDE_BRIDGE_URL=http://host.docker.internal:8006
""",
    )

    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8006,
        help="Port to run the bridge service on (default: 8006)",
    )
    parser.add_argument(
        "--claude-path",
        help=("Full path to claude CLI executable. " "Auto-detected if not specified."),
    )

    args = parser.parse_args()

    # Validate Claude CLI is available
    claude_path = args.claude_path or find_claude_cli()
    if not claude_path:
        print("Error: Claude CLI not found.")
        print()
        print("Install Claude Code CLI or specify the path:")
        print("  llmcrawl claude-bridge --claude-path /path/to/claude")
        print()
        print("Search locations:")
        print("  - CLAUDE_CLI_PATH environment variable")
        if sys.platform == "win32":
            print("  - %USERPROFILE%\\.claude-cli\\currentVersion\\claude.exe")
        print("  - System PATH")
        sys.exit(1)

    if args.claude_path and not os.path.isfile(args.claude_path):
        print(f"Error: Claude CLI not found at: {args.claude_path}")
        sys.exit(1)

    # Set environment variables for the bridge module
    os.environ["CLAUDE_BRIDGE_PORT"] = str(args.port)
    if args.claude_path:
        os.environ["CLAUDE_CLI_PATH"] = args.claude_path

    print("Claude Bridge Configuration:")
    print(f"  Claude CLI:   {claude_path}")
    print(f"  Port:         {args.port}")
    print(f"  Bridge URL:   http://localhost:{args.port}")
    print(f"  Gateway URL:  http://host.docker.internal:{args.port}")
    print()

    # Import and run the bridge
    try:
        import uvicorn

        from tools.claude_bridge import app
    except ImportError:
        # Try alternative import path
        try:
            tools_dir = get_tools_dir()
            sys.path.insert(0, str(tools_dir.parent))
            import uvicorn

            from tools.claude_bridge import app
        except ImportError as e:
            print(f"Error: Could not import Claude bridge module: {e}")
            print("Make sure the tools package is installed correctly.")
            print("Required: pip install fastapi uvicorn httpx")
            sys.exit(1)

    # Handle Ctrl+C gracefully
    def signal_handler(sig: int, frame: object) -> None:
        print("\nShutting down Claude Bridge...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("Starting Claude Bridge...")
    print("Press Ctrl+C to stop\n")

    # Configure uvicorn
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["fmt"] = (
        "%(asctime)s - %(levelname)s - %(client_addr)s - "
        '"%(request_line)s" %(status_code)s'
    )
    log_config["formatters"]["access"]["datefmt"] = "%Y-%m-%d %H:%M:%S"

    uvicorn.run(app, host="0.0.0.0", port=args.port, log_config=log_config)


if __name__ == "__main__":
    main()

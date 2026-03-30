#!/usr/bin/env python3
"""
LLMCrawl Copilot Bridge CLI

Starts the Copilot Bridge service on the host, enabling the gateway
to route LLM requests through the GitHub Copilot CLI.

Usage:
    llmcrawl copilot-bridge                    # Start with defaults (port 8009)
    llmcrawl copilot-bridge --port 8010        # Start on custom port
    llmcrawl copilot-bridge --copilot-path /path/to/copilot
"""

import os
import shutil
import signal
import sys
from pathlib import Path


def get_tools_dir() -> Path:
    """Get the tools directory from the installed package."""
    package_dir = Path(__file__).parent.parent
    tools_dir = package_dir / "tools"

    if tools_dir.exists():
        return tools_dir

    for candidate in [
        Path.cwd() / "tools",
        Path(__file__).parent.parent.parent / "tools",
    ]:
        if candidate.exists():
            return candidate

    return tools_dir


def find_copilot_cli() -> str | None:
    """
    Find the Copilot CLI executable.

    Searches in order:
    1. COPILOT_CLI_PATH environment variable
    2. System PATH (copilot / copilot.exe)
    3. Windows default locations
    """
    env_path = os.environ.get("COPILOT_CLI_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    which = shutil.which("copilot")
    if which:
        return which

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(local_app_data, "Microsoft", "WinGet", "Links", "copilot.exe"),
            os.path.join(
                os.environ.get("USERPROFILE", ""),
                ".copilot",
                "bin",
                "copilot.exe",
            ),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c

    return None


def main() -> None:
    """Main entry point for Copilot Bridge CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="llmcrawl copilot-bridge",
        description="Start the Copilot Bridge service for LLM request routing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start with defaults (port 8009)
  llmcrawl copilot-bridge

  # Start on a custom port
  llmcrawl copilot-bridge --port 8010

  # Specify Copilot CLI path explicitly
  llmcrawl copilot-bridge --copilot-path "C:\\path\\to\\copilot.exe"

Prerequisites:
  - GitHub Copilot CLI installed (copilot.exe / copilot)
  - Authenticated: run `copilot login` first

The bridge service:
  - Runs on port 8009 by default
  - Accepts chat completion requests from the gateway
  - Routes them through copilot.exe subprocess

Configure in .env:
  COPILOT_BRIDGE_URL=http://localhost:8009
""",
    )

    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8009,
        help="Port to run the bridge service on (default: 8009)",
    )
    parser.add_argument(
        "--copilot-path",
        help="Full path to copilot CLI executable. Auto-detected if not specified.",
    )

    args = parser.parse_args()

    copilot_path = args.copilot_path or find_copilot_cli()
    if not copilot_path:
        print("Error: Copilot CLI not found.")
        print()
        print("Install GitHub Copilot CLI or specify the path:")
        print("  llmcrawl copilot-bridge --copilot-path /path/to/copilot")
        print()
        print("Search locations:")
        print("  - COPILOT_CLI_PATH environment variable")
        print("  - System PATH")
        if sys.platform == "win32":
            print("  - %LOCALAPPDATA%\\Microsoft\\WinGet\\Links\\copilot.exe")
        sys.exit(1)

    if args.copilot_path and not os.path.isfile(args.copilot_path):
        print(f"Error: Copilot CLI not found at: {args.copilot_path}")
        sys.exit(1)

    os.environ["COPILOT_BRIDGE_PORT"] = str(args.port)
    if args.copilot_path:
        os.environ["COPILOT_CLI_PATH"] = args.copilot_path

    print("Copilot Bridge Configuration:")
    print(f"  Copilot CLI: {copilot_path}")
    print(f"  Port:        {args.port}")
    print(f"  Bridge URL:  http://localhost:{args.port}")
    print()

    try:
        import uvicorn

        from tools.copilot_bridge import app
    except ImportError:
        try:
            tools_dir = get_tools_dir()
            sys.path.insert(0, str(tools_dir.parent))
            import uvicorn

            from tools.copilot_bridge import app
        except ImportError as e:
            print(f"Error: Could not import Copilot bridge module: {e}")
            print("Make sure the tools package is installed correctly.")
            print("Required: pip install fastapi uvicorn")
            sys.exit(1)

    def signal_handler(sig: int, frame: object) -> None:
        print("\nShutting down Copilot Bridge...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("Starting Copilot Bridge...")
    print("Press Ctrl+C to stop\n")

    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["fmt"] = (
        "%(asctime)s - %(levelname)s - %(client_addr)s - "
        '"%(request_line)s" %(status_code)s'
    )
    log_config["formatters"]["access"]["datefmt"] = "%Y-%m-%d %H:%M:%S"

    uvicorn.run(app, host="0.0.0.0", port=args.port, log_config=log_config)


if __name__ == "__main__":
    main()

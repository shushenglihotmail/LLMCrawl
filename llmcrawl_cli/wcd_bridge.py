#!/usr/bin/env python3
"""
LLMCrawl WCD Bridge CLI

Starts the Windows Composition Database bridge service.

Usage:
    llmcrawl wcd-bridge --build <path>      # Start with build share path
    llmcrawl wcd-bridge --cmd <full_path>   # Start with full CMD path
"""

import argparse
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


def construct_wcd_cmd_path(build_path: str, arch: str = "amd64fre") -> str:
    """
    Construct the full path to InteractViaPowerShell.cmd.

    Args:
        build_path: Base path to Windows build
        arch: Architecture folder name (default: amd64fre)

    Returns:
        Full path to InteractViaPowerShell.cmd
    """
    # Normalize path separators
    build_path = build_path.replace("/", "\\")

    # Construct full path
    full_path = os.path.join(
        build_path,
        arch,
        "WindowsCompositionData",
        "SDK",
        "InteractViaPowerShell.cmd",
    )

    return full_path


def main() -> None:
    """Main entry point for WCD bridge CLI."""
    parser = argparse.ArgumentParser(
        prog="llmcrawl wcd-bridge",
        description="Start Windows Composition Database bridge service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using build share path (recommended)
  llmcrawl wcd-bridge --build "\\\\winbuilds\\release\\branch\\build"

  # With specific architecture
  llmcrawl wcd-bridge --build "\\\\winbuilds\\..." --arch arm64fre

  # Using full CMD path directly
  llmcrawl wcd-bridge --cmd "\\\\winbuilds\\...\\InteractViaPowerShell.cmd"

Prerequisites:
  - Windows host machine
  - Access to Windows build shares
  - Network connectivity to \\\\winbuilds

The bridge service:
  - Runs on port 8005
  - Maintains a persistent PowerShell session with WCD tools
  - Receives queries from the Docker container via HTTP
  - Must remain running while using WCD queries

Configure in .env:
  WIN_COMP_BRIDGE_URL=http://host.docker.internal:8005
""",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--build",
        "-b",
        help="Base path to Windows build release folder",
    )
    group.add_argument(
        "--cmd",
        "-c",
        help="Full path to InteractViaPowerShell.cmd",
    )

    parser.add_argument(
        "--arch",
        "-a",
        default="amd64fre",
        help="Architecture folder name (default: amd64fre)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8005,
        help="Port to run the bridge service on (default: 8005)",
    )

    args = parser.parse_args()

    # Determine the CMD path
    if args.build:
        cmd_path = construct_wcd_cmd_path(args.build, args.arch)
        print("Configuration:")
        print(f"  Build Path:     {args.build}")
        print(f"  Architecture:   {args.arch}")
        print(f"  Full CMD Path:  {cmd_path}")
    else:
        cmd_path = args.cmd
        print("Configuration:")
        print(f"  CMD Path: {cmd_path}")

    # Set environment variable
    os.environ["WIN_COMP_SHARE_CMD"] = cmd_path

    print(f"  Port:           {args.port}")
    print()

    # Import and run the bridge
    try:
        import uvicorn

        from tools.windows_composition_bridge import app
    except ImportError:
        # Try alternative import path
        try:
            tools_dir = get_tools_dir()
            sys.path.insert(0, str(tools_dir.parent))
            import uvicorn

            from tools.windows_composition_bridge import app
        except ImportError as e:
            print(f"Error: Could not import WCD bridge module: {e}")
            print("Make sure the tools package is installed correctly.")
            print("Required: pip install fastapi uvicorn")
            sys.exit(1)

    # Handle Ctrl+C gracefully
    def signal_handler(sig: int, frame: object) -> None:
        print("\nShutting down WCD bridge...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("Starting Windows Composition Bridge...")
    print(f"Bridge URL: http://localhost:{args.port}")
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

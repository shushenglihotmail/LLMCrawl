#!/usr/bin/env python3
"""
LLMCrawl Auth CLI

Wrapper for the authentication tool to authenticate to internal sites.

Usage:
    llmcrawl auth <url>                     # Authenticate to internal site
    llmcrawl auth https://www.osgwiki.com   # Example
"""

import argparse
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


def main() -> None:
    """Main entry point for auth CLI."""
    parser = argparse.ArgumentParser(
        prog="llmcrawl auth",
        description="Authenticate to internal sites for crawling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  llmcrawl auth https://www.osgwiki.com/wiki/Main_Page
  llmcrawl auth https://internal-site.com --name my_site
  llmcrawl auth https://www.osgwiki.com --no-apply
  llmcrawl auth https://www.osgwiki.com --no-restart

The tool will:
  1. Launch Edge with remote debugging enabled
  2. Wait for you to sign in
  3. Extract authentication cookies
  4. Save to .auth/ directory
  5. Apply to deploy/.env file (use --no-apply to skip)
  6. Recreate crawler container (use --no-restart to skip)
  7. Test authentication (use --no-test to skip)

Cookie Expiration:
  Authentication cookies expire after some time. Re-run this command
  to refresh cookies when crawling starts failing.
""",
    )

    parser.add_argument(
        "url",
        nargs="?",
        help="URL to authenticate to (e.g., https://www.osgwiki.com/wiki/Main_Page)",
    )
    parser.add_argument(
        "--name",
        "-n",
        help="Profile name for saved credentials (default: derived from domain)",
    )
    parser.add_argument(
        "--cookie",
        "-c",
        default="AppServiceAuthSession",
        help="Target cookie name to find (default: AppServiceAuthSession)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=9222,
        help="Remote debugging port (default: 9222)",
    )
    parser.add_argument(
        "--no-apply",
        action="store_true",
        help="Don't apply credentials to .env file",
    )
    parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Don't restart crawler container",
    )
    parser.add_argument(
        "--no-test",
        action="store_true",
        help="Don't test authentication after setup",
    )

    args = parser.parse_args()

    if not args.url:
        parser.print_help()
        print("\nError: URL is required")
        sys.exit(1)

    # Import and run the authentication module
    try:
        from tools.msauth.authenticate import authenticate
    except ImportError:
        # Try alternative import path
        try:
            tools_dir = get_tools_dir()
            sys.path.insert(0, str(tools_dir.parent))
            from tools.msauth.authenticate import authenticate
        except ImportError as e:
            print(f"Error: Could not import authentication module: {e}")
            print("Make sure the tools package is installed correctly.")
            sys.exit(1)

    result = authenticate(
        url=args.url,
        name=args.name,
        target_cookie=args.cookie,
        debug_port=args.port,
        auto_apply=not args.no_apply,
        auto_restart=not args.no_restart,
        auto_test=not args.no_test,
    )

    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()

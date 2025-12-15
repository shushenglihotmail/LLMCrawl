"""
CLI for the Crawler MCP Server.

Provides commands to:
- Start/stop/restart crawler containers
- Run the MCP server for VS Code integration
- Authenticate to internal sites
- Run the crawler service natively (without Docker)
"""

import argparse
import logging
import os
import sys


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def cmd_start(args: argparse.Namespace) -> int:
    """Start crawler services."""
    from .containers import check_docker, start_services

    if not check_docker():
        print("Error: Docker is not available.")
        print("Please install Docker Desktop or Docker Engine.")
        return 1

    services = args.services if hasattr(args, "services") and args.services else None
    success = start_services(
        services=services,
        build=args.build if hasattr(args, "build") else False,
    )
    return 0 if success else 1


def cmd_stop(args: argparse.Namespace) -> int:
    """Stop crawler services."""
    from .containers import stop_services

    services = args.services if hasattr(args, "services") and args.services else None
    success = stop_services(
        services=services,
        remove_volumes=args.volumes if hasattr(args, "volumes") else False,
    )
    return 0 if success else 1


def cmd_restart(args: argparse.Namespace) -> int:
    """Restart crawler services."""
    from .containers import restart_services

    services = args.services if hasattr(args, "services") and args.services else None
    success = restart_services(
        services=services,
        build=args.build if hasattr(args, "build") else False,
    )
    return 0 if success else 1


def cmd_status(args: argparse.Namespace) -> int:
    """Show service status."""
    from .containers import get_service_status, health_check

    print("=== Container Status ===")
    status = get_service_status()
    if not status:
        print("(No containers running or unable to get status)")

    print("\n=== Health Check ===")
    health = health_check()
    for service, state in health.items():
        icon = "✓" if state == "healthy" else "✗"
        print(f"  {icon} {service}: {state}")

    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    """Show service logs."""
    from .containers import show_logs

    services = args.services if hasattr(args, "services") and args.services else None
    show_logs(
        services=services,
        follow=not args.no_follow if hasattr(args, "no_follow") else True,
        tail=args.tail if hasattr(args, "tail") else 100,
    )
    return 0


def cmd_auth(args: argparse.Namespace) -> int:
    """Authenticate to internal site."""
    from .auth import authenticate, clear_credentials, list_saved_credentials

    if args.list:
        credentials = list_saved_credentials()
        if credentials:
            print("Saved credentials:")
            for cred in credentials:
                name = cred["name"]
                count = cred["cookies"]
                path = cred["file"]
                print(f"    {name}: {count} cookies ({path})")
        else:
            print("No saved credentials found.")
        return 0

    if args.clear:
        name = args.clear if args.clear is not True else None
        if clear_credentials(name):
            print("Credentials cleared.")
        else:
            print("No credentials found to clear.")
        return 0

    if not args.url:
        print("Error: URL is required for authentication.")
        print("Usage: crawler-mcp-server auth <url>")
        return 1

    result = authenticate(
        url=args.url,
        name=args.name,
        target_cookie=args.cookie,
        debug_port=args.port,
        auto_apply=not args.no_apply,
        auto_restart=not args.no_restart,
        auto_test=not args.no_test,
    )

    return 0 if result.get("success") else 1


def cmd_mcp(args: argparse.Namespace) -> int:
    """Run MCP server (stdio mode)."""
    import asyncio

    from .stdio_server import run_stdio_server

    base_url = args.base_url or os.getenv(
        "CRAWLER_MCP_BASE_URL", "http://localhost:8001"
    )
    timeout = args.timeout or float(os.getenv("CRAWLER_MCP_TIMEOUT_S", "120"))

    asyncio.run(run_stdio_server(base_url=base_url, timeout_s=timeout))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Run crawler service natively (without Docker)."""
    from .service import run_crawler_service

    run_crawler_service(
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
        workers=args.workers,
    )
    return 0


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="crawler-mcp-server",
        description="Crawler MCP Server - Manage crawler services and VS Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start all crawler services
  crawler-mcp-server start

  # Start with rebuild
  crawler-mcp-server start --build

  # Stop services
  crawler-mcp-server stop

  # Restart just the crawler
  crawler-mcp-server restart crawler

  # Check status
  crawler-mcp-server status

  # Authenticate to internal site
  crawler-mcp-server auth https://www.osgwiki.com/wiki/Main_Page

  # Run MCP server for VS Code (stdio mode)
  crawler-mcp-server mcp

  # Run crawler service natively (no Docker)
  crawler-mcp-server serve --port 8001
""",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start crawler services")
    start_parser.add_argument("services", nargs="*", help="Specific services to start")
    start_parser.add_argument(
        "--build", "-b", action="store_true", help="Rebuild images"
    )
    start_parser.set_defaults(func=cmd_start)

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop crawler services")
    stop_parser.add_argument("services", nargs="*", help="Specific services to stop")
    stop_parser.add_argument(
        "--volumes", "-v", action="store_true", help="Also remove volumes"
    )
    stop_parser.set_defaults(func=cmd_stop)

    # Restart command
    restart_parser = subparsers.add_parser("restart", help="Restart crawler services")
    restart_parser.add_argument(
        "services", nargs="*", help="Specific services to restart"
    )
    restart_parser.add_argument(
        "--build", "-b", action="store_true", help="Rebuild images"
    )
    restart_parser.set_defaults(func=cmd_restart)

    # Status command
    status_parser = subparsers.add_parser("status", help="Show service status")
    status_parser.set_defaults(func=cmd_status)

    # Logs command
    logs_parser = subparsers.add_parser("logs", help="Show service logs")
    logs_parser.add_argument(
        "services", nargs="*", help="Specific services to show logs for"
    )
    logs_parser.add_argument(
        "--no-follow", action="store_true", help="Don't follow log output"
    )
    logs_parser.add_argument(
        "--tail", "-n", type=int, default=100, help="Number of lines to show"
    )
    logs_parser.set_defaults(func=cmd_logs)

    # Auth command
    auth_parser = subparsers.add_parser("auth", help="Authenticate to internal site")
    auth_parser.add_argument("url", nargs="?", help="URL to authenticate to")
    auth_parser.add_argument("--name", "-n", help="Profile name for credentials")
    auth_parser.add_argument(
        "--cookie", "-c", default="AppServiceAuthSession", help="Target cookie name"
    )
    auth_parser.add_argument("--port", "-p", type=int, default=9222, help="Debug port")
    auth_parser.add_argument(
        "--no-apply", action="store_true", help="Don't apply to .env"
    )
    auth_parser.add_argument(
        "--no-restart", action="store_true", help="Don't restart container"
    )
    auth_parser.add_argument(
        "--no-test", action="store_true", help="Don't test authentication"
    )
    auth_parser.add_argument(
        "--list", "-l", action="store_true", help="List saved credentials"
    )
    auth_parser.add_argument("--clear", nargs="?", const=True, help="Clear credentials")
    auth_parser.set_defaults(func=cmd_auth)

    # MCP command (for VS Code integration)
    mcp_parser = subparsers.add_parser("mcp", help="Run MCP server (stdio mode)")
    mcp_parser.add_argument("--base-url", help="Crawler service URL")
    mcp_parser.add_argument("--timeout", type=float, help="Request timeout in seconds")
    mcp_parser.set_defaults(func=cmd_mcp)

    # Serve command (native service)
    serve_parser = subparsers.add_parser("serve", help="Run crawler service natively")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    serve_parser.add_argument("--port", type=int, default=8001, help="Port to bind to")
    serve_parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload"
    )
    serve_parser.add_argument("--log-level", default="info", help="Log level")
    serve_parser.add_argument(
        "--workers", type=int, default=1, help="Number of workers"
    )
    serve_parser.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command is None:
        # Default to MCP mode for backward compatibility
        args.base_url = None
        args.timeout = None
        sys.exit(cmd_mcp(args))

    if hasattr(args, "func"):
        sys.exit(args.func(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

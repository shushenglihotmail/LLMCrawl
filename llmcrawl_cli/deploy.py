#!/usr/bin/env python3
"""
LLMCrawl Deploy CLI

Manages deployment of LLMCrawl services using Docker Compose.

Usage:
    llmcrawl deploy --init              # Initialize deployment folder
    llmcrawl deploy --up                # Start all services
    llmcrawl deploy --down              # Stop all services
    llmcrawl deploy --logs              # View service logs
    llmcrawl deploy --status            # Check service status
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def get_package_deploy_dir() -> Path:
    """Get the deploy directory from the installed package."""
    # When installed via pip, the deploy folder is included as package data
    # It's located relative to this file's location
    package_dir = Path(__file__).parent.parent
    deploy_dir = package_dir / "deploy"

    if deploy_dir.exists():
        return deploy_dir

    # Fallback: try to find it in common locations
    for candidate in [
        Path.cwd() / "deploy",
        Path(__file__).parent.parent.parent / "deploy",
    ]:
        if candidate.exists():
            return candidate

    return deploy_dir  # Return expected path even if not found


def get_local_deploy_dir() -> Path:
    """Get the local deployment directory."""
    return Path.cwd() / "llmcrawl-deploy"


def check_docker() -> bool:
    """Check if Docker is installed and running."""
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_docker_compose() -> bool:
    """Check if Docker Compose is available."""
    # Try docker compose (v2)
    try:
        result = subprocess.run(
            ["docker", "compose", "version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Try docker-compose (v1)
    try:
        result = subprocess.run(
            ["docker-compose", "version"], capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_compose_command() -> list:
    """Get the appropriate docker compose command."""
    # Prefer docker compose v2
    try:
        result = subprocess.run(
            ["docker", "compose", "version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return ["docker", "compose"]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return ["docker-compose"]


def init_deployment(target_dir: Path, force: bool = False) -> bool:
    """Initialize the deployment folder with config files."""
    source_dir = get_package_deploy_dir()

    if not source_dir.exists():
        print(f"❌ Error: Deploy source directory not found: {source_dir}")
        print("   Make sure LLMCrawl is properly installed.")
        return False

    if target_dir.exists() and not force:
        print(f"⚠️  Directory already exists: {target_dir}")
        print("   Use --force to overwrite, or --dir to specify a different location.")
        return False

    print(f"📦 Initializing LLMCrawl deployment...")
    print(f"   Source: {source_dir}")
    print(f"   Target: {target_dir}")

    # Create target directory
    target_dir.mkdir(parents=True, exist_ok=True)

    # Files to copy
    files_to_copy = [
        "docker-compose.yml",
        ".env.example",
        "prometheus.yml",
    ]

    # Directories to copy
    dirs_to_copy = [
        "requirements",
        "grafana-provisioning",
    ]

    # Dockerfiles to copy
    dockerfiles = [
        "Dockerfile.crawler",
        "Dockerfile.gateway",
        "Dockerfile.indexer",
        "Dockerfile.mcp_server",
        "Dockerfile.demo",
    ]

    # Copy files
    for filename in files_to_copy + dockerfiles:
        src = source_dir / filename
        dst = target_dir / filename
        if src.exists():
            shutil.copy2(src, dst)
            print(f"   ✓ Copied {filename}")
        else:
            print(f"   ⚠ Skipped {filename} (not found)")

    # Copy directories
    for dirname in dirs_to_copy:
        src = source_dir / dirname
        dst = target_dir / dirname
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"   ✓ Copied {dirname}/")
        else:
            print(f"   ⚠ Skipped {dirname}/ (not found)")

    # Copy service config directories (gateway, crawler, indexer, mcp_servers)
    for service_dir in ["gateway", "crawler", "indexer", "mcp_servers"]:
        src = source_dir / service_dir
        dst = target_dir / service_dir
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"   ✓ Copied {service_dir}/")

    # Create logs directory
    logs_dir = target_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    print("   ✓ Created logs/")

    # Create data/files directory (default MCP mount point)
    data_files_dir = target_dir / "data" / "files"
    data_files_dir.mkdir(parents=True, exist_ok=True)
    # Copy README if exists
    src_readme = source_dir / "data" / "files" / "README.md"
    if src_readme.exists():
        shutil.copy2(src_readme, data_files_dir / "README.md")
    print("   ✓ Created data/files/")

    # Create .env from .env.example if not exists
    env_example = target_dir / ".env.example"
    env_file = target_dir / ".env"
    if env_example.exists() and not env_file.exists():
        shutil.copy2(env_example, env_file)
        print(f"   ✓ Created .env from .env.example")

    print()
    print("=" * 60)
    print("✅ Deployment initialized successfully!")
    print("=" * 60)
    print()
    print("Next steps:")
    print(f"  1. cd {target_dir}")
    print("  2. Edit .env with your API keys and settings")
    print("  3. Run: llmcrawl deploy --up")
    print()

    return True


def run_compose(args: list, deploy_dir: Path) -> int:
    """Run docker compose with the given arguments."""
    if not deploy_dir.exists():
        print(f"❌ Error: Deployment directory not found: {deploy_dir}")
        print("   Run 'llmcrawl deploy --init' first.")
        return 1

    compose_file = deploy_dir / "docker-compose.yml"
    if not compose_file.exists():
        print(f"❌ Error: docker-compose.yml not found in {deploy_dir}")
        return 1

    compose_cmd = get_compose_command()
    cmd = compose_cmd + ["-f", str(compose_file)] + args

    print(f"🐳 Running: {' '.join(cmd)}")
    print()

    # Run with inherited stdout/stderr for interactive output
    result = subprocess.run(cmd, cwd=deploy_dir)
    return result.returncode


def cmd_up(deploy_dir: Path, detach: bool = True) -> int:
    """Start all services."""
    if not check_docker():
        print("❌ Error: Docker is not running or not installed.")
        print("   Please install and start Docker Desktop.")
        return 1

    print("🚀 Starting LLMCrawl services...")
    args = ["up", "--build"]
    if detach:
        args.append("-d")

    result = run_compose(args, deploy_dir)

    if result == 0 and detach:
        print()
        print("=" * 60)
        print("✅ Services started successfully!")
        print("=" * 60)
        print()
        print("Access points:")
        print("  • HiChat Web UI:    http://localhost:8080")
        print("  • Gateway API:      http://localhost:8000")
        print("  • Gateway Docs:     http://localhost:8000/docs")
        print("  • Qdrant Dashboard: http://localhost:6333/dashboard")
        print("  • Grafana:          http://localhost:3001")
        print()
        print("Commands:")
        print("  • View logs:   llmcrawl deploy --logs")
        print("  • Stop:        llmcrawl deploy --down")
        print("  • Status:      llmcrawl deploy --status")
        print()

    return result


def cmd_down(deploy_dir: Path) -> int:
    """Stop all services."""
    print("🛑 Stopping LLMCrawl services...")
    return run_compose(["down"], deploy_dir)


def cmd_logs(deploy_dir: Path, follow: bool = True, service: str = None) -> int:
    """View service logs."""
    args = ["logs"]
    if follow:
        args.append("-f")
    if service:
        args.append(service)
    return run_compose(args, deploy_dir)


def cmd_status(deploy_dir: Path) -> int:
    """Check service status."""
    print("📊 LLMCrawl Service Status")
    print("=" * 60)
    return run_compose(["ps"], deploy_dir)


def cmd_restart(deploy_dir: Path, service: str = None) -> int:
    """Restart services."""
    args = ["restart"]
    if service:
        args.append(service)
    return run_compose(args, deploy_dir)


def cmd_pull(deploy_dir: Path) -> int:
    """Pull latest images."""
    print("📥 Pulling latest images...")
    return run_compose(["pull"], deploy_dir)


def main() -> None:
    """Main entry point for the deploy CLI."""
    parser = argparse.ArgumentParser(
        description="LLMCrawl Deployment Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  llmcrawl deploy --init              Initialize deployment folder
  llmcrawl deploy --up                Start all services
  llmcrawl deploy --down              Stop all services
  llmcrawl deploy --logs              View logs (Ctrl+C to exit)
  llmcrawl deploy --logs gateway      View logs for specific service
  llmcrawl deploy --status            Check service status
  llmcrawl deploy --restart           Restart all services
  llmcrawl deploy --restart gateway   Restart specific service
""",
    )

    # Action arguments (mutually exclusive)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--init",
        action="store_true",
        help="Initialize deployment folder with config files",
    )
    action_group.add_argument("--up", action="store_true", help="Start all services")
    action_group.add_argument("--down", action="store_true", help="Stop all services")
    action_group.add_argument("--logs", action="store_true", help="View service logs")
    action_group.add_argument(
        "--status", action="store_true", help="Check service status"
    )
    action_group.add_argument("--restart", action="store_true", help="Restart services")
    action_group.add_argument(
        "--pull", action="store_true", help="Pull latest Docker images"
    )

    # Optional arguments
    parser.add_argument(
        "--dir",
        type=str,
        default=None,
        help="Deployment directory (default: ./llmcrawl-deploy)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing files (for --init)",
    )
    parser.add_argument(
        "--no-detach", action="store_true", help="Run in foreground (for --up)"
    )
    parser.add_argument(
        "--no-follow", action="store_true", help="Don't follow logs (for --logs)"
    )
    parser.add_argument(
        "service",
        nargs="?",
        default=None,
        help="Specific service name (for --logs, --restart)",
    )

    args = parser.parse_args()

    # Determine deployment directory
    if args.dir:
        deploy_dir = Path(args.dir)
    else:
        deploy_dir = get_local_deploy_dir()

    # Execute action
    exit_code = 0

    if args.init:
        success = init_deployment(deploy_dir, force=args.force)
        exit_code = 0 if success else 1
    elif args.up:
        exit_code = cmd_up(deploy_dir, detach=not args.no_detach)
    elif args.down:
        exit_code = cmd_down(deploy_dir)
    elif args.logs:
        exit_code = cmd_logs(
            deploy_dir, follow=not args.no_follow, service=args.service
        )
    elif args.status:
        exit_code = cmd_status(deploy_dir)
    elif args.restart:
        exit_code = cmd_restart(deploy_dir, service=args.service)
    elif args.pull:
        exit_code = cmd_pull(deploy_dir)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

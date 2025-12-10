#!/usr/bin/env python3
"""
LLMCrawl Deploy CLI

Manages deployment of LLMCrawl services using Docker Compose.

Usage:
    llmcrawl deploy --init              # Initialize deployment folder
    llmcrawl deploy --upgrade           # Upgrade deployment after pip upgrade
    llmcrawl deploy --up                # Start all services
    llmcrawl deploy --down              # Stop all services
    llmcrawl deploy --logs              # View service logs
    llmcrawl deploy --status            # Check service status
"""

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


def get_package_root_dir() -> Path:
    """Get the package root directory (where gateway/, crawler/, etc. are).

    When installed from wheel, these are top-level packages in site-packages.
    We find them by importing and getting their __file__ path.
    """
    try:
        import gateway

        # Return the parent of the gateway package (site-packages or project root)
        return Path(gateway.__file__).parent.parent
    except ImportError:
        # Fallback to relative path from this file
        return Path(__file__).parent.parent


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

    print("📦 Initializing LLMCrawl deployment...")
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

    # Copy directories from deploy folder
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

    # Copy service source code from package root (for Docker builds)
    package_root = get_package_root_dir()
    for service_dir in ["gateway", "crawler", "indexer", "mcp_servers"]:
        src = package_root / service_dir
        dst = target_dir / service_dir
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"   ✓ Copied {service_dir}/")
        else:
            print(f"   ⚠ Skipped {service_dir}/ (not found in package)")

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

    # Copy documentation files from deploy folder (included in wheel)
    # Copy README.md to root of deployment
    readme_src = source_dir / "README.md"
    if readme_src.exists():
        shutil.copy2(readme_src, target_dir / "README.md")
        print("   ✓ Copied README.md")

    # Copy docs folder
    docs_dir = target_dir / "docs"
    docs_dir.mkdir(exist_ok=True)
    docs_to_copy = ["INSTALL.md", "DIAGNOSTICS.md", "MONITORING.md", "CONFIGURATION.md"]
    for doc_name in docs_to_copy:
        doc_src = source_dir / "docs" / doc_name
        if doc_src.exists():
            shutil.copy2(doc_src, docs_dir / doc_name)
            print(f"   ✓ Copied docs/{doc_name}")

    # Create .env from .env.example if not exists
    env_example = target_dir / ".env.example"
    env_file = target_dir / ".env"
    if env_example.exists() and not env_file.exists():
        shutil.copy2(env_example, env_file)
        print("   ✓ Created .env from .env.example")

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


def parse_env_file(env_path: Path) -> Dict[str, str]:
    """Parse a .env file and return a dictionary of key-value pairs."""
    env_vars: Dict[str, str] = {}
    if not env_path.exists():
        return env_vars

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            # Parse KEY=VALUE
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Remove surrounding quotes if present
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                env_vars[key] = value
    return env_vars


def merge_env_files(old_env: dict, new_example: Path) -> str:
    """Merge old .env values into new .env.example template."""
    if not new_example.exists():
        return ""

    with open(new_example, "r", encoding="utf-8") as f:
        template = f.read()

    # Replace values in template with old values where keys match
    lines = template.split("\n")
    result_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in old_env and old_env[key]:
                # Preserve the old value
                value = old_env[key]
                # Don't add quotes around JSON values (starts with [ or {)
                # Docker Compose handles unquoted JSON fine
                # Only quote simple values with special chars (but not JSON)
                if not (value.startswith("[") or value.startswith("{")):
                    if " " in value or "=" in value:
                        value = f'"{value}"'
                result_lines.append(f"{key}={value}")
                continue
        result_lines.append(line)

    return "\n".join(result_lines)


def upgrade_deployment(target_dir: Path, restart: bool = True) -> bool:
    """Upgrade deployment files while preserving user configuration."""
    source_dir = get_package_deploy_dir()

    if not source_dir.exists():
        print(f"❌ Error: Deploy source directory not found: {source_dir}")
        print("   Make sure LLMCrawl is properly installed.")
        return False

    if not target_dir.exists():
        print(f"❌ Error: Deployment directory not found: {target_dir}")
        print("   Run 'llmcrawl deploy --init' first.")
        return False

    print("🔄 Upgrading LLMCrawl deployment...")
    print(f"   Source: {source_dir}")
    print(f"   Target: {target_dir}")
    print()

    # Step 1: Backup current .env
    env_file = target_dir / ".env"
    backup_dir = target_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if env_file.exists():
        backup_env = backup_dir / f".env.backup_{timestamp}"
        shutil.copy2(env_file, backup_env)
        print(f"   ✓ Backed up .env to backups/.env.backup_{timestamp}")

        # Parse old .env
        old_env_vars = parse_env_file(env_file)
    else:
        old_env_vars = {}
        print("   ⚠ No .env file found, will use defaults")

    # Step 2: Copy new config files
    files_to_copy = [
        "docker-compose.yml",
        ".env.example",
        "prometheus.yml",
    ]

    dockerfiles = [
        "Dockerfile.crawler",
        "Dockerfile.gateway",
        "Dockerfile.indexer",
        "Dockerfile.mcp_server",
        "Dockerfile.demo",
    ]

    for filename in files_to_copy + dockerfiles:
        src = source_dir / filename
        dst = target_dir / filename
        if src.exists():
            # Backup old file if it exists and is different
            if dst.exists():
                backup_file = backup_dir / f"{filename}.backup_{timestamp}"
                shutil.copy2(dst, backup_file)
            shutil.copy2(src, dst)
            print(f"   ✓ Updated {filename}")
        else:
            print(f"   ⚠ Skipped {filename} (not found in package)")

    # Step 3: Update directories from deploy folder
    dirs_to_copy = [
        "requirements",
        "grafana-provisioning",
    ]

    for dirname in dirs_to_copy:
        src = source_dir / dirname
        dst = target_dir / dirname
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"   ✓ Updated {dirname}/")

    # Update service source code from package root
    package_root = get_package_root_dir()
    for service_dir in ["gateway", "crawler", "indexer", "mcp_servers"]:
        src = package_root / service_dir
        dst = target_dir / service_dir
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"   ✓ Updated {service_dir}/")

    # Step 3b: Copy/Update documentation files from deploy folder (included in wheel)
    # Copy README.md to root of deployment
    readme_src = source_dir / "README.md"
    if readme_src.exists():
        shutil.copy2(readme_src, target_dir / "README.md")
        print("   ✓ Updated README.md")

    # Copy docs folder
    docs_dir = target_dir / "docs"
    docs_dir.mkdir(exist_ok=True)
    docs_to_copy = ["INSTALL.md", "DIAGNOSTICS.md", "MONITORING.md", "CONFIGURATION.md"]
    for doc_name in docs_to_copy:
        doc_src = source_dir / "docs" / doc_name
        if doc_src.exists():
            shutil.copy2(doc_src, docs_dir / doc_name)
            print(f"   ✓ Updated docs/{doc_name}")

    # Step 4: Merge .env with new .env.example
    new_example = target_dir / ".env.example"
    if old_env_vars and new_example.exists():
        merged_env = merge_env_files(old_env_vars, new_example)
        with open(env_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(merged_env)
        print("   ✓ Merged your settings into new .env")
    elif new_example.exists():
        shutil.copy2(new_example, env_file)
        print("   ✓ Created .env from .env.example")

    print()
    print("=" * 60)
    print("✅ Deployment upgraded successfully!")
    print("=" * 60)
    print()
    print(f"Backups saved to: {backup_dir}")
    print()

    # Step 5: Restart services if requested
    if restart:
        print("🔄 Rebuilding and restarting services...")
        print()
        result = cmd_up(target_dir, detach=True)
        if result != 0:
            print()
            print("⚠️  Services may need manual restart.")
            print("   Run: llmcrawl deploy --up")
            return False
    else:
        print("Next steps:")
        print("  1. Review the merged .env file")
        print("  2. Check backups/ folder if you need to restore anything")
        print("  3. Run: llmcrawl deploy --up")
        print()

    return True


def ensure_docker_network(network_name: str = "webrag-network") -> bool:
    """Ensure the Docker network exists, create if not."""
    try:
        # Check if network exists
        result = subprocess.run(
            ["docker", "network", "inspect", network_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True

        # Network doesn't exist, create it
        print(f"🌐 Creating Docker network: {network_name}")
        result = subprocess.run(
            ["docker", "network", "create", network_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            print(f"   ✓ Network {network_name} created")
            return True
        else:
            print(f"   ⚠ Failed to create network: {result.stderr}")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"   ⚠ Error checking/creating network: {e}")
        return False


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


def cmd_up(deploy_dir: Path, detach: bool = True, profile: Optional[str] = None) -> int:
    """Start all services."""
    if not check_docker():
        print("❌ Error: Docker is not running or not installed.")
        print("   Please install and start Docker Desktop.")
        return 1

    # Ensure the Docker network exists
    ensure_docker_network("webrag-network")

    print("🚀 Starting LLMCrawl services...")
    args = []
    if profile:
        args.extend(["--profile", profile])
    args.extend(["up", "--build"])
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
        if profile == "monitoring":
            print("  • Prometheus:       http://localhost:9090")
            print("  • Grafana:          http://localhost:3001 (admin/admin)")
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


def cmd_logs(
    deploy_dir: Path, follow: bool = True, service: Optional[str] = None
) -> int:
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


def cmd_restart(deploy_dir: Path, service: Optional[str] = None) -> int:
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
  llmcrawl deploy --upgrade           Upgrade after pip install (preserves .env)
  llmcrawl deploy --up                Start all services
  llmcrawl deploy --up --profile monitoring  Start with monitoring stack
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
    action_group.add_argument(
        "--upgrade",
        action="store_true",
        help="Upgrade deployment after pip upgrade (preserves .env settings)",
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
        "--no-restart",
        action="store_true",
        help="Don't restart services after upgrade (for --upgrade)",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Docker Compose profile to use (e.g., 'monitoring' for Prometheus/Grafana)",
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
    elif args.upgrade:
        success = upgrade_deployment(deploy_dir, restart=not args.no_restart)
        exit_code = 0 if success else 1
    elif args.up:
        exit_code = cmd_up(deploy_dir, detach=not args.no_detach, profile=args.profile)
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

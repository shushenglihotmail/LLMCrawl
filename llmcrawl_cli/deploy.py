#!/usr/bin/env python3
"""
LLMCrawl Deploy CLI

Manages deployment of LLMCrawl services using Docker Compose.

Usage:
    llmcrawl deploy --init              # Initialize deployment folder
    llmcrawl deploy --upgrade           # Upgrade deployment after pip upgrade
    llmcrawl deploy --up                # Start all services
    llmcrawl deploy --down              # Stop all services
    llmcrawl deploy --stop gateway      # Stop specific service(s)
    llmcrawl deploy --restart gateway   # Restart specific service(s)
    llmcrawl deploy --restart gateway --build  # Restart with rebuild
    llmcrawl deploy --logs              # View service logs
    llmcrawl deploy --status            # Check service status

Services: gateway, crawler, indexer, azure-devops-mcp-server, memory-service
Monitoring: prometheus, grafana (use --profile monitoring)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


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


def get_package_docs_dir() -> Path:
    """Get the docs directory from the installed package."""
    package_root = get_package_root_dir()
    docs_dir = package_root / "docs"

    if docs_dir.exists():
        return docs_dir

    # Fallback: try to find it in common locations
    for candidate in [
        Path.cwd() / "docs",
        Path(__file__).parent.parent / "docs",
    ]:
        if candidate.exists():
            return candidate

    return docs_dir  # Return expected path even if not found


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
    for service_dir in ["gateway", "crawler", "indexer", "mcp_servers", "services"]:
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

    # Create memory directory for OpenClaw-style memory service
    memory_dir = target_dir / "memory" / "daily"
    memory_dir.mkdir(parents=True, exist_ok=True)
    print("   ✓ Created memory/daily/")

    # Copy documentation files from deploy folder (included in wheel)
    # Copy README.md to root of deployment
    readme_src = source_dir / "README.md"
    if readme_src.exists():
        shutil.copy2(readme_src, target_dir / "README.md")
        print("   ✓ Copied README.md")

    # Copy docs folder from main docs package (single source of truth)
    package_docs_dir = get_package_docs_dir()
    deploy_docs_dir = target_dir / "docs"
    deploy_docs_dir.mkdir(exist_ok=True)
    docs_to_copy = [
        "INSTALL.md",
        "DIAGNOSTICS.md",
        "MONITORING.md",
        "CONFIGURATION.md",
        "AUTHENTICATION.md",
    ]
    for doc_name in docs_to_copy:
        doc_src = package_docs_dir / doc_name
        if doc_src.exists():
            shutil.copy2(doc_src, deploy_docs_dir / doc_name)
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


# --- Local Service Management ---


def get_pid_file(deploy_dir: Path) -> Path:
    """Get path to PID file for local services."""
    return deploy_dir / "local-services.pid"


def read_pids(deploy_dir: Path) -> Dict[str, int]:
    """Read PIDs from the PID file."""
    pid_file = get_pid_file(deploy_dir)
    if not pid_file.exists():
        return {}
    try:
        with open(pid_file, "r") as f:
            data: Dict[str, int] = json.load(f)
            return data
    except (json.JSONDecodeError, IOError):
        return {}


def save_pids(deploy_dir: Path, pids: Dict[str, int]) -> None:
    """Save PIDs to the PID file."""
    pid_file = get_pid_file(deploy_dir)
    with open(pid_file, "w") as f:
        json.dump(pids, f, indent=2)


def is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return str(pid) in result.stdout
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def stop_process(pid: int) -> bool:
    """Stop a process by PID."""
    if not is_process_running(pid):
        return True
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
            )
        else:
            os.kill(pid, 15)  # SIGTERM
        return True
    except Exception:
        return False


def get_python_executable(deploy_dir: Path) -> str:
    """Get Python executable, preferring venv."""
    # Check for venv in project root (parent of deploy_dir)
    project_root = deploy_dir.parent
    venv_python = project_root / "venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)

    # Also check in deploy_dir itself (for wheel deployments)
    venv_python = deploy_dir / "venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)

    # Fallback to system Python
    return sys.executable


def resolve_memory_data_path(deploy_dir: Path, env_vars: Dict[str, str]) -> Path:
    """Resolve MEMORY_DATA_PATH from env vars, handling relative paths."""
    memory_path = env_vars.get("MEMORY_DATA_PATH", "./memory")

    # Handle relative paths (relative to deploy_dir)
    if not os.path.isabs(memory_path):
        # Remove leading ./ if present
        if memory_path.startswith("./"):
            memory_path = memory_path[2:]
        memory_path = str((deploy_dir / memory_path).resolve())

    return Path(memory_path)


def start_local_services(
    deploy_dir: Path,
    services: Optional[List[str]] = None,
) -> Tuple[bool, Dict[str, int]]:
    """Start local services (gateway, memory-service).

    Args:
        deploy_dir: Deployment directory
        services: Optional list of services to start. Defaults to all.

    Returns:
        Tuple of (success, pids dict)
    """
    if services is None:
        services = ["gateway", "memory"]

    # Load environment from .env
    env_file = deploy_dir / ".env"
    env_vars = parse_env_file(env_file)

    # Resolve memory data path
    memory_data_path = resolve_memory_data_path(deploy_dir, env_vars)

    # Ensure memory directory exists
    memory_data_path.mkdir(parents=True, exist_ok=True)
    (memory_data_path / "daily").mkdir(parents=True, exist_ok=True)

    # Create logs directory
    logs_dir = deploy_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Get Python executable
    python_exe = get_python_executable(deploy_dir)

    # Read existing PIDs
    pids = read_pids(deploy_dir)

    # Stop existing services first
    for svc in services:
        if svc in pids and is_process_running(pids[svc]):
            print(f"   Stopping existing {svc} (PID: {pids[svc]})...")
            stop_process(pids[svc])

    # Determine working directory (project root or deploy_dir for wheel)
    project_root = deploy_dir.parent
    if (project_root / "gateway").exists():
        work_dir = project_root
    else:
        work_dir = deploy_dir

    # Build environment for child processes
    child_env = os.environ.copy()
    child_env.update(env_vars)
    child_env["MEMORY_DATA_PATH"] = str(memory_data_path)
    child_env["EMBEDDING_PROVIDER"] = "local"
    child_env["MILVUS_URI"] = env_vars.get("MILVUS_URI", "http://localhost:19530")

    print(f"   Memory data path: {memory_data_path}")

    success = True

    # Start Memory Service
    if "memory" in services:
        print("   Starting Memory Service (port 8007)...")
        memory_log = logs_dir / "memory-service.log"

        try:
            with open(memory_log, "a") as log_file:
                proc = subprocess.Popen(
                    [
                        python_exe,
                        "-m",
                        "uvicorn",
                        "services.memory_service.main:app",
                        "--host",
                        "0.0.0.0",
                        "--port",
                        "8007",
                    ],
                    cwd=work_dir,
                    env=child_env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    ),
                )
                pids["memory"] = proc.pid
                print(f"     PID: {proc.pid}")
        except Exception as e:
            print(f"     Failed to start: {e}")
            success = False

    # Start Gateway
    if "gateway" in services:
        print("   Starting Gateway (port 8000)...")
        gateway_log = logs_dir / "gateway.log"

        # Set gateway-specific environment
        child_env["GATEWAY_HOST"] = "0.0.0.0"
        child_env["GATEWAY_PORT"] = "8000"
        child_env["CRAWLER_URL"] = env_vars.get("CRAWLER_URL", "http://localhost:8001")
        child_env["INDEXER_URL"] = env_vars.get("INDEXER_URL", "http://localhost:8002")
        child_env["AZURE_DEVOPS_MCP_URL"] = env_vars.get(
            "AZURE_DEVOPS_MCP_URL", "http://localhost:8004"
        )
        child_env["MEMORY_SERVICE_URL"] = env_vars.get(
            "MEMORY_SERVICE_URL", "http://localhost:8007"
        )
        child_env["MEMORY_AUTO_LOG"] = env_vars.get("MEMORY_AUTO_LOG", "true")
        child_env["MEMORY_AUTO_FLUSH"] = env_vars.get("MEMORY_AUTO_FLUSH", "true")
        child_env["ENVIRONMENT"] = "development"
        child_env["LOG_LEVEL"] = env_vars.get("LOG_LEVEL", "INFO")
        # Override bridge URLs for local gateway
        child_env["CLAUDE_BRIDGE_URL"] = env_vars.get(
            "CLAUDE_BRIDGE_URL", "http://localhost:8006"
        ).replace("host.docker.internal", "localhost")
        child_env["WIN_COMP_BRIDGE_URL"] = env_vars.get(
            "WIN_COMP_BRIDGE_URL", "http://localhost:8005"
        ).replace("host.docker.internal", "localhost")

        try:
            with open(gateway_log, "a") as log_file:
                proc = subprocess.Popen(
                    [
                        python_exe,
                        "-m",
                        "uvicorn",
                        "gateway.main:app",
                        "--host",
                        "0.0.0.0",
                        "--port",
                        "8000",
                    ],
                    cwd=work_dir,
                    env=child_env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    ),
                )
                pids["gateway"] = proc.pid
                print(f"     PID: {proc.pid}")
        except Exception as e:
            print(f"     Failed to start: {e}")
            success = False

    # Save PIDs
    save_pids(deploy_dir, pids)

    return success, pids


def stop_local_services(
    deploy_dir: Path,
    services: Optional[List[str]] = None,
) -> bool:
    """Stop local services.

    Args:
        deploy_dir: Deployment directory
        services: Optional list of services to stop. If None, stops all.

    Returns:
        True if all services stopped successfully
    """
    pids = read_pids(deploy_dir)

    if services is None:
        services = list(pids.keys())

    success = True
    for svc in services:
        if svc in pids:
            pid = pids[svc]
            if is_process_running(pid):
                print(f"   Stopping {svc} (PID: {pid})...")
                if stop_process(pid):
                    print("     Stopped")
                else:
                    print("     Failed to stop")
                    success = False
            del pids[svc]

    save_pids(deploy_dir, pids)
    return success


def get_local_service_status(deploy_dir: Path) -> Dict[str, str]:
    """Get status of local services.

    Returns:
        Dict mapping service name to status string
    """
    pids = read_pids(deploy_dir)
    status = {}

    for svc in ["gateway", "memory"]:
        if svc in pids:
            pid = pids[svc]
            if is_process_running(pid):
                status[svc] = f"running (PID: {pid})"
            else:
                status[svc] = f"stopped (stale PID: {pid})"
        else:
            status[svc] = "not started"

    return status


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
    for service_dir in ["gateway", "crawler", "indexer", "mcp_servers", "services"]:
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

    # Copy docs folder from main docs package (single source of truth)
    package_docs_dir = get_package_docs_dir()
    deploy_docs_dir = target_dir / "docs"
    deploy_docs_dir.mkdir(exist_ok=True)
    docs_to_copy = [
        "INSTALL.md",
        "DIAGNOSTICS.md",
        "MONITORING.md",
        "CONFIGURATION.md",
        "AUTHENTICATION.md",
    ]
    for doc_name in docs_to_copy:
        doc_src = package_docs_dir / doc_name
        if doc_src.exists():
            shutil.copy2(doc_src, deploy_docs_dir / doc_name)
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


def run_compose(args: list, deploy_dir: Path, use_dev: bool = False) -> int:
    """Run docker compose with the given arguments."""
    if not deploy_dir.exists():
        print(f"❌ Error: Deployment directory not found: {deploy_dir}")
        print("   Run 'llmcrawl deploy --init' first.")
        return 1

    compose_filename = "docker-compose.dev.yml" if use_dev else "docker-compose.yml"
    compose_file = deploy_dir / compose_filename
    if not compose_file.exists():
        print(f"❌ Error: {compose_filename} not found in {deploy_dir}")
        return 1

    compose_cmd = get_compose_command()
    # Use just the filename since we're running in deploy_dir
    cmd = compose_cmd + ["-f", compose_filename] + args

    print(f"🐳 Running: {' '.join(cmd)}")
    print()

    # Run with inherited stdout/stderr for interactive output
    result = subprocess.run(cmd, cwd=deploy_dir)
    return result.returncode


def cmd_up(
    deploy_dir: Path,
    detach: bool = True,
    profile: Optional[str] = None,
    use_dev: bool = False,
    docker_only: bool = False,
) -> int:
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

    result = run_compose(args, deploy_dir, use_dev=use_dev)

    # Start local services (gateway, memory) unless docker_only
    local_success = True
    if result == 0 and detach and not docker_only:
        print()
        print("🖥️  Starting local services...")
        local_success, _ = start_local_services(deploy_dir)
        if local_success:
            print("   Local services started.")
        else:
            print("   ⚠️  Some local services failed to start.")

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
        print("  • Memory Service:   http://localhost:8007")
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

    return result if local_success else 1


def cmd_down(
    deploy_dir: Path,
    services: Optional[list] = None,
    use_dev: bool = False,
    docker_only: bool = False,
) -> int:
    """Stop all services or specific services."""
    local_services = ["gateway", "memory"]
    docker_services = []
    local_to_stop = []

    if services:
        # Separate local and Docker services
        for svc in services:
            if svc in local_services:
                local_to_stop.append(svc)
            else:
                docker_services.append(svc)
    else:
        # Stop all
        local_to_stop = local_services
        docker_services = []  # Empty means all Docker services

    result = 0

    # Stop local services first (unless docker_only)
    if local_to_stop and not docker_only:
        print(f"🖥️  Stopping local services: {', '.join(local_to_stop)}...")
        stop_local_services(deploy_dir, local_to_stop)

    # Stop Docker services
    if services and docker_services:
        print(f"🛑 Stopping Docker services: {', '.join(docker_services)}...")
        result = run_compose(["stop"] + docker_services, deploy_dir, use_dev=use_dev)
        if result == 0:
            result = run_compose(
                ["rm", "-f"] + docker_services, deploy_dir, use_dev=use_dev
            )
    elif not services:
        print("🛑 Stopping all Docker services...")
        # Also stop local services if not already done
        if not docker_only and not local_to_stop:
            stop_local_services(deploy_dir)
        result = run_compose(["down"], deploy_dir, use_dev=use_dev)

    return result


def cmd_stop(
    deploy_dir: Path,
    services: Optional[list] = None,
    profile: Optional[str] = None,
    use_dev: bool = False,
) -> int:
    """Stop services without removing containers."""
    args = []
    if profile:
        args.extend(["--profile", profile])
    args.append("stop")

    if services:
        args.extend(services)
        print(f"🛑 Stopping services: {', '.join(services)}...")
    else:
        print("🛑 Stopping all services (containers preserved)...")

    return run_compose(args, deploy_dir, use_dev=use_dev)


def cmd_logs(
    deploy_dir: Path,
    follow: bool = True,
    service: Optional[str] = None,
    use_dev: bool = False,
) -> int:
    """View service logs."""
    args = ["logs"]
    if follow:
        args.append("-f")
    if service:
        args.append(service)
    try:
        return run_compose(args, deploy_dir, use_dev=use_dev)
    except KeyboardInterrupt:
        print("\n👋 Stopped following logs")
        return 0


def cmd_status(deploy_dir: Path, use_dev: bool = False) -> int:
    """Check service status."""
    print("📊 LLMCrawl Service Status")
    print("=" * 60)

    # Show local service status
    print()
    print("Local Services:")
    print("-" * 40)
    local_status = get_local_service_status(deploy_dir)
    for svc, status in local_status.items():
        icon = "✅" if "running" in status else "⚪"
        print(f"  {icon} {svc}: {status}")

    print()
    print("Docker Services:")
    print("-" * 40)
    return run_compose(["ps"], deploy_dir, use_dev=use_dev)


def cmd_restart(
    deploy_dir: Path,
    services: Optional[list] = None,
    build: bool = False,
    profile: Optional[str] = None,
    use_dev: bool = False,
    docker_only: bool = False,
) -> int:
    """Restart services with optional rebuild."""
    local_services_list = ["gateway", "memory"]
    docker_services = []
    local_to_restart = []

    if services:
        # Separate local and Docker services
        for svc in services:
            if svc in local_services_list:
                local_to_restart.append(svc)
            else:
                docker_services.append(svc)
    else:
        # Restart all
        local_to_restart = local_services_list
        docker_services = []  # Empty means all Docker services

    service_names = services if services else ["all services"]
    print(f"🔄 Restarting: {', '.join(service_names)}...")

    result = 0

    # Restart Docker services if any
    if not services or docker_services:
        if not check_docker():
            print("❌ Error: Docker is not running or not installed.")
            return 1

        if build:
            args = []
            if profile:
                args.extend(["--profile", profile])
            args.extend(["up", "-d", "--build", "--force-recreate"])
            if docker_services:
                args.extend(docker_services)
            print("   Mode: Rebuild images and recreate containers")
        else:
            args = []
            if profile:
                args.extend(["--profile", profile])
            args.append("restart")
            if docker_services:
                args.extend(docker_services)
            print("   Mode: Restart containers (no rebuild)")

        result = run_compose(args, deploy_dir, use_dev=use_dev)

    # Restart local services (unless docker_only)
    if local_to_restart and not docker_only:
        print()
        print(f"🖥️  Restarting local services: {', '.join(local_to_restart)}...")
        success, _ = start_local_services(deploy_dir, local_to_restart)
        if not success:
            result = 1

    if result == 0:
        print()
        print(f"✅ Successfully restarted: {', '.join(service_names)}")

    return result


def cmd_pull(deploy_dir: Path, use_dev: bool = False) -> int:
    """Pull latest images."""
    print("📥 Pulling latest images...")
    return run_compose(["pull"], deploy_dir, use_dev=use_dev)


def cmd_health() -> int:
    """Check health of all LLMCrawl services via their /health endpoints."""
    import json
    import urllib.error
    import urllib.request

    print()
    print("=" * 60)
    print("          LLMCrawl Service Health Check")
    print("=" * 60)

    services = [
        ("Gateway", "http://localhost:8000/health", 8000),
        ("Crawler", "http://localhost:8001/health", 8001),
        ("Indexer", "http://localhost:8002/health", 8002),
        ("Azure DevOps MCP", "http://localhost:8004/health", 8004),
        ("Memory Service", "http://localhost:8007/health", 8007),
        ("Qdrant", "http://localhost:6333/healthz", 6333),
        ("Playwright", "http://localhost:3003/health", 3003),
    ]

    healthy = 0
    total = len(services)

    for name, url, port in services:
        print()
        print(f"🔍 {name} (port {port})")
        print("-" * 40)

        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read().decode("utf-8")
                try:
                    result = json.loads(data)
                    status = result.get("status", "unknown")

                    if status == "healthy":
                        print("   Status: ✅ HEALTHY")
                        healthy += 1
                    else:
                        print(f"   Status: ⚠️ {status}")
                        healthy += 1  # Still reachable

                    # Show service name if available
                    if result.get("service"):
                        print(f"   Service: {result['service']}")

                    # Show components if available (crawler has nested components)
                    if result.get("components"):
                        print("   Components:")
                        for comp_name, comp_info in result["components"].items():
                            comp_status = comp_info.get("status", "unknown")
                            icon = "✅" if comp_status == "healthy" else "⚠"
                            print(f"     - {comp_name}: {icon} {comp_status}")

                    # Show vector store info (indexer)
                    if result.get("vector_store"):
                        vs = result["vector_store"]
                        vs_status = vs.get("status", "unknown")
                        icon = "✅" if vs_status == "healthy" else "⚠️"
                        print(f"   Vector Store: {icon} {vs_status}")
                        if vs.get("collections"):
                            print(f"     Collections: {vs['collections']}")

                    # Show embedding model (indexer)
                    if result.get("embedding_model"):
                        em = result["embedding_model"]
                        em_healthy = em.get("healthy", False)
                        icon = "✅" if em_healthy else "❌"
                        print(f"   Embedding: {icon} {em.get('model', 'unknown')}")

                except json.JSONDecodeError:
                    # Non-JSON response (like Playwright's /json/version)
                    print("   Status: ✅ HEALTHY (reachable)")
                    healthy += 1

        except urllib.error.URLError as e:
            print("   Status: ❌ UNREACHABLE")
            print(f"   Error: {e.reason}")
        except TimeoutError:
            print("   Status: ❌ TIMEOUT")
        except Exception as e:
            print("   Status: ❌ ERROR")
            print(f"   Error: {e}")

    # Summary
    print()
    print("=" * 60)
    if healthy == total:
        print(f"   Summary: ✅ {healthy}/{total} services healthy")
    elif healthy > 0:
        print(f"   Summary: ⚠️  {healthy}/{total} services healthy")
    else:
        print(f"   Summary: ❌ {healthy}/{total} services healthy")
    print("=" * 60)
    print()

    return 0 if healthy == total else 1


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
  llmcrawl deploy --down              Stop all services and remove containers
  llmcrawl deploy --down gateway      Stop and remove specific service
  llmcrawl deploy --stop              Stop all services (preserve containers)
  llmcrawl deploy --stop gateway      Stop specific service
  llmcrawl deploy --restart           Restart all services
  llmcrawl deploy --restart gateway   Restart specific service
  llmcrawl deploy --restart gateway --build  Restart with image rebuild
  llmcrawl deploy --restart --profile monitoring  Restart monitoring stack
  llmcrawl deploy --logs              View logs (Ctrl+C to exit)
  llmcrawl deploy --logs gateway      View logs for specific service
  llmcrawl deploy --status            Check service status
  llmcrawl deploy --health            Check health of all services

Local Development (use --dev to use docker-compose.dev.yml):
  llmcrawl deploy --restart gateway --build --dev --dir ./deploy
  llmcrawl deploy --stop gateway --dev --dir ./deploy
  llmcrawl deploy --status --dev --dir ./deploy

Services: gateway, crawler, indexer, azure-devops-mcp-server,
          memory-service, redis, postgres, qdrant, playwright, firecrawl
Monitoring: prometheus, grafana (use --profile monitoring)
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
    action_group.add_argument(
        "--down",
        action="store_true",
        help="Stop services and remove containers",
    )
    action_group.add_argument(
        "--stop",
        action="store_true",
        help="Stop services (preserve containers for quick restart)",
    )
    action_group.add_argument("--logs", action="store_true", help="View service logs")
    action_group.add_argument(
        "--status", action="store_true", help="Check service status"
    )
    action_group.add_argument(
        "--restart",
        action="store_true",
        help="Restart services (use --build to rebuild images)",
    )
    action_group.add_argument(
        "--pull", action="store_true", help="Pull latest Docker images"
    )
    action_group.add_argument(
        "--health",
        action="store_true",
        help="Check health of all services via HTTP endpoints",
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
        "--build",
        action="store_true",
        help="Rebuild images before restarting (for --restart)",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Use docker-compose.dev.yml for local development (uses ../ paths)",
    )
    parser.add_argument(
        "--docker-only",
        action="store_true",
        help="Only manage Docker services, skip local services (gateway, memory)",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Docker Compose profile (e.g., 'monitoring' for Prometheus/Grafana)",
    )
    parser.add_argument(
        "service",
        nargs="*",
        default=None,
        help="Service name(s) (for --logs, --restart, --stop, --down)",
    )

    args = parser.parse_args()

    # Determine deployment directory
    if args.dir:
        deploy_dir = Path(args.dir)
    else:
        deploy_dir = get_local_deploy_dir()

    # Parse services - handle both space-separated and comma-separated
    services: Optional[List[str]] = None
    if args.service:
        parsed: List[str] = []
        for s in args.service:
            # Split by comma in case of "gateway,memory" format
            parsed.extend([x.strip() for x in s.split(",") if x.strip()])
        if parsed:
            services = parsed
    use_dev = args.dev
    docker_only = args.docker_only

    # Execute action
    exit_code = 0

    if args.init:
        success = init_deployment(deploy_dir, force=args.force)
        exit_code = 0 if success else 1
    elif args.upgrade:
        success = upgrade_deployment(deploy_dir, restart=not args.no_restart)
        exit_code = 0 if success else 1
    elif args.up:
        exit_code = cmd_up(
            deploy_dir,
            detach=not args.no_detach,
            profile=args.profile,
            use_dev=use_dev,
            docker_only=docker_only,
        )
    elif args.down:
        exit_code = cmd_down(
            deploy_dir,
            services=services,
            use_dev=use_dev,
            docker_only=docker_only,
        )
    elif args.stop:
        exit_code = cmd_stop(
            deploy_dir, services=services, profile=args.profile, use_dev=use_dev
        )
    elif args.logs:
        # For logs, only use first service if multiple specified
        service = services[0] if services else None
        exit_code = cmd_logs(
            deploy_dir, follow=not args.no_follow, service=service, use_dev=use_dev
        )
    elif args.status:
        exit_code = cmd_status(deploy_dir, use_dev=use_dev)
    elif args.restart:
        exit_code = cmd_restart(
            deploy_dir,
            services=services,
            build=args.build,
            profile=args.profile,
            use_dev=use_dev,
            docker_only=docker_only,
        )
    elif args.pull:
        exit_code = cmd_pull(deploy_dir, use_dev=use_dev)
    elif args.health:
        exit_code = cmd_health()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

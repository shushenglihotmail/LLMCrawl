"""
Container management for the crawler service.

Provides commands to start, stop, restart crawler containers using Docker Compose.

The crawler stack includes:
- crawler: LLMCrawl crawler FastAPI service (port 8001)
- firecrawl: Web crawling engine (port 3002)
- playwright: Browser rendering for JS-heavy pages (port 3000)
- redis: Caching and rate limiting for firecrawl (port 6379)
- postgres: Database for firecrawl (port 5432)
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Default compose file bundled with the package
BUNDLED_COMPOSE_FILE = "docker-compose.crawler.yml"
# Fallback compose file in LLMCrawl workspace
WORKSPACE_COMPOSE_FILE = "docker-compose.dev.yml"


def get_compose_config() -> Tuple[Optional[Path], str]:
    """
    Find the compose directory and file to use.

    Returns:
        Tuple of (directory, compose_filename)
    """
    # 1. Check LLMCRAWL_DEPLOY_DIR environment variable
    env_dir = os.environ.get("LLMCRAWL_DEPLOY_DIR")
    if env_dir:
        env_path = Path(env_dir)
        if env_path.exists():
            # Prefer bundled compose file if it exists
            if (env_path / BUNDLED_COMPOSE_FILE).exists():
                return env_path, BUNDLED_COMPOSE_FILE
            if (env_path / WORKSPACE_COMPOSE_FILE).exists():
                return env_path, WORKSPACE_COMPOSE_FILE

    # 2. Check for bundled compose file in package directory (same dir as this module)
    package_dir = Path(__file__).parent
    if (package_dir / BUNDLED_COMPOSE_FILE).exists():
        return package_dir, BUNDLED_COMPOSE_FILE

    # 3. Check common workspace locations
    candidates = [
        Path.cwd() / "deploy",
        Path.cwd() / "llmcrawl-deploy",
        Path(__file__).parent.parent.parent.parent / "deploy",
        Path(__file__).parent.parent.parent.parent.parent / "deploy",
    ]

    # Also check parent directories
    cwd = Path.cwd()
    for _ in range(5):
        if (cwd / "deploy" / WORKSPACE_COMPOSE_FILE).exists():
            candidates.insert(0, cwd / "deploy")
            break
        cwd = cwd.parent

    for candidate in candidates:
        if candidate.exists():
            if (candidate / BUNDLED_COMPOSE_FILE).exists():
                return candidate, BUNDLED_COMPOSE_FILE
            if (candidate / WORKSPACE_COMPOSE_FILE).exists():
                return candidate, WORKSPACE_COMPOSE_FILE

    return None, BUNDLED_COMPOSE_FILE


def get_deploy_dir() -> Optional[Path]:
    """Find the deploy directory containing docker-compose files."""
    deploy_dir, _ = get_compose_config()
    return deploy_dir


def check_docker() -> bool:
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "--version"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_docker_compose() -> bool:
    """Check if Docker Compose is available."""
    # Try docker compose (v2)
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass

    # Try docker-compose (v1)
    try:
        result = subprocess.run(
            ["docker-compose", "--version"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_compose_command() -> list:
    """Get the Docker Compose command to use."""
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return ["docker", "compose"]
    except FileNotFoundError:
        pass

    return ["docker-compose"]


def run_compose_command(
    args: list,
    deploy_dir: Optional[Path] = None,
    compose_file: Optional[str] = None,
    capture_output: bool = False,
) -> Tuple[int, str, str]:
    """
    Run a docker-compose command.

    Args:
        args: Command arguments (e.g., ["up", "-d"])
        deploy_dir: Deploy directory (auto-detected if None)
        compose_file: Compose file to use (auto-detected if None)
        capture_output: If True, capture and return output

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    if deploy_dir is None or compose_file is None:
        detected_dir, detected_file = get_compose_config()
        if deploy_dir is None:
            deploy_dir = detected_dir
        if compose_file is None:
            compose_file = detected_file

    if deploy_dir is None:
        logger.error("Could not find deploy directory with docker-compose file.")
        logger.error(
            "Set LLMCRAWL_DEPLOY_DIR environment variable or run from workspace root."
        )
        return (1, "", "Deploy directory not found")

    compose_cmd = get_compose_command()
    full_cmd = compose_cmd + ["-f", compose_file] + args

    logger.debug(f"Running: {' '.join(full_cmd)} in {deploy_dir}")

    try:
        result = subprocess.run(
            full_cmd,
            cwd=deploy_dir,
            capture_output=capture_output,
            text=True,
        )
        return (result.returncode, result.stdout or "", result.stderr or "")
    except FileNotFoundError as e:
        return (1, "", str(e))


def start_services(
    services: Optional[list] = None,
    deploy_dir: Optional[Path] = None,
    build: bool = False,
    detach: bool = True,
) -> bool:
    """
    Start crawler services.

    Args:
        services: List of services to start (None = all)
        deploy_dir: Deploy directory
        build: Rebuild images before starting
        detach: Run in background

    Returns:
        True if successful
    """
    args = ["up"]
    if detach:
        args.append("-d")
    if build:
        args.append("--build")
    if services:
        args.extend(services)

    returncode, _, _ = run_compose_command(args, deploy_dir)

    if returncode == 0:
        print("Services started successfully!")
        print("  Gateway: http://localhost:8000")
        print("  Crawler: http://localhost:8001")
        print("  Indexer: http://localhost:8002")
        print("  Qdrant:  http://localhost:6333/dashboard")
        return True
    else:
        print("Failed to start services")
        return False


def stop_services(
    services: Optional[list] = None,
    deploy_dir: Optional[Path] = None,
    remove_volumes: bool = False,
) -> bool:
    """
    Stop crawler services.

    Args:
        services: List of services to stop (None = all)
        deploy_dir: Deploy directory
        remove_volumes: Also remove volumes

    Returns:
        True if successful
    """
    args = ["down"]
    if remove_volumes:
        args.append("-v")
    if services:
        # For specific services, use stop instead of down
        args = ["stop"] + services

    returncode, _, _ = run_compose_command(args, deploy_dir)

    if returncode == 0:
        print("Services stopped successfully!")
        return True
    else:
        print("Failed to stop services")
        return False


def restart_services(
    services: Optional[list] = None,
    deploy_dir: Optional[Path] = None,
    build: bool = False,
) -> bool:
    """
    Restart crawler services.

    Args:
        services: List of services to restart (None = all)
        deploy_dir: Deploy directory
        build: Rebuild images before restarting

    Returns:
        True if successful
    """
    if services:
        args = ["restart"] + services
        if build:
            # Need to rebuild first, then restart
            run_compose_command(["build"] + services, deploy_dir)
        returncode, _, _ = run_compose_command(args, deploy_dir)
    else:
        # Full restart - down then up
        stop_services(deploy_dir=deploy_dir)
        return start_services(deploy_dir=deploy_dir, build=build)

    if returncode == 0:
        print("Services restarted successfully!")
        return True
    else:
        print("Failed to restart services")
        return False


def get_service_status(deploy_dir: Optional[Path] = None) -> dict:
    """
    Get status of all services.

    Returns:
        Dict mapping service names to their status
    """
    returncode, stdout, _ = run_compose_command(
        ["ps", "--format", "json"],
        deploy_dir,
        capture_output=True,
    )

    if returncode != 0:
        # Fallback to non-json format
        returncode, stdout, _ = run_compose_command(
            ["ps"],
            deploy_dir,
            capture_output=True,
        )
        print(stdout)
        return {}

    import json

    try:
        services = json.loads(stdout)
        if isinstance(services, list):
            return {
                s.get("Name", s.get("Service")): s.get("State", "unknown")
                for s in services
            }
    except json.JSONDecodeError:
        pass

    return {}


def show_logs(
    services: Optional[list] = None,
    deploy_dir: Optional[Path] = None,
    follow: bool = True,
    tail: int = 100,
) -> None:
    """Show logs for services."""
    args = ["logs"]
    if follow:
        args.append("-f")
    if tail:
        args.extend(["--tail", str(tail)])
    if services:
        args.extend(services)

    run_compose_command(args, deploy_dir)


def health_check(
    deploy_dir: Optional[Path] = None,
    crawler_url: str = "http://localhost:8001",
) -> dict:
    """
    Check health of the crawler service.

    Args:
        deploy_dir: Deploy directory (unused, kept for API compatibility)
        crawler_url: Base URL of the crawler service

    Returns:
        Dict with crawler health status
    """
    import httpx

    health = {}

    try:
        response = httpx.get(f"{crawler_url}/health", timeout=5.0)
        health["crawler"] = (
            "healthy"
            if response.status_code == 200
            else f"unhealthy ({response.status_code})"
        )
    except httpx.RequestError:
        health["crawler"] = "unavailable"

    return health

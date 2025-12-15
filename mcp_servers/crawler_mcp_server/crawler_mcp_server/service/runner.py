"""
Runner for the embedded crawler service.

This allows running the crawler natively (without Docker) when the full
dependencies are installed.
"""

import logging
import sys

logger = logging.getLogger(__name__)


def run_crawler_service(
    host: str = "0.0.0.0",
    port: int = 8001,
    reload: bool = False,
    log_level: str = "info",
    workers: int = 1,
) -> None:
    """
    Run the crawler FastAPI service directly using uvicorn.

    This requires the full crawler dependencies to be installed:
        pip install crawler-mcp-server[service]

    Args:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 8001)
        reload: Enable auto-reload for development
        log_level: Logging level (default: info)
        workers: Number of uvicorn workers (default: 1)
    """
    try:
        import uvicorn
    except ImportError:
        logger.error("uvicorn is required to run the crawler service.")
        logger.error("Install with: pip install crawler-mcp-server[service]")
        sys.exit(1)

    # Try to import the crawler module
    try:
        from crawler.main import app  # noqa: F401
    except ImportError as e:
        logger.error(f"Could not import crawler module: {e}")
        logger.error("Make sure crawler dependencies are installed:")
        logger.error("  pip install crawler-mcp-server[service]")
        logger.error("")
        logger.error("Or if running from source, install crawler requirements:")
        logger.error("  pip install -r requirements/crawler.txt")
        sys.exit(1)

    # Check Playwright installation
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        logger.warning(
            "Playwright not installed. JavaScript rendering will be limited."
        )
        logger.warning(
            "Install with: pip install playwright && playwright install chromium"
        )

    logger.info(f"Starting crawler service on {host}:{port}")

    uvicorn.run(
        "crawler.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
        workers=workers,
    )


def check_playwright_browsers() -> bool:
    """Check if Playwright browsers are installed."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            # Just check if we can access browser types
            _ = p.chromium.executable_path
            return True
    except Exception:
        return False


def install_playwright_browsers(browser: str = "chromium") -> bool:
    """Install Playwright browsers."""
    import subprocess

    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", browser],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Failed to install Playwright browsers: {e}")
        return False

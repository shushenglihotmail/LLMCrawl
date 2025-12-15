"""
Authentication module for internal sites.

Provides cookie-based authentication for crawling internal sites like osgwiki.com.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def get_auth_dir() -> Path:
    """Get the .auth directory for storing credentials."""
    # Check environment variable first
    auth_dir_env = os.environ.get("LLMCRAWL_AUTH_DIR")
    if auth_dir_env:
        return Path(auth_dir_env)

    # Default to .auth in current directory or home
    for candidate in [Path.cwd() / ".auth", Path.home() / ".llmcrawl" / "auth"]:
        if candidate.exists():
            return candidate

    # Create in current directory
    auth_dir = Path.cwd() / ".auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    return auth_dir


def get_deploy_env_file() -> Optional[Path]:
    """Find the deploy .env file."""
    candidates = [
        Path.cwd() / "deploy" / ".env",
        Path.cwd() / "llmcrawl-deploy" / ".env",
    ]

    env_dir = os.environ.get("LLMCRAWL_DEPLOY_DIR")
    if env_dir:
        candidates.insert(0, Path(env_dir) / ".env")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def authenticate(
    url: str,
    name: Optional[str] = None,
    target_cookie: str = "AppServiceAuthSession",
    debug_port: int = 9222,
    auto_apply: bool = True,
    auto_restart: bool = True,
    auto_test: bool = True,
    deploy_dir: Optional[Path] = None,
    env_file: Optional[Path] = None,
) -> dict:
    """
    Authenticate to an internal site and save cookies.

    This launches Edge with remote debugging, waits for the user to sign in,
    then extracts the authentication cookies.

    Args:
        url: URL to authenticate to
        name: Profile name for saved credentials (default: derived from domain)
        target_cookie: Cookie name to look for (default: AppServiceAuthSession)
        debug_port: Remote debugging port
        auto_apply: Apply credentials to .env file
        auto_restart: Restart crawler container after applying
        auto_test: Test authentication after setup

    Returns:
        Dict with success status and details
    """
    import subprocess

    # Derive name from URL if not provided
    if not name:
        parsed = urlparse(url)
        name = parsed.netloc.replace(".", "_").replace(":", "_")

    auth_dir = get_auth_dir()
    cookie_file = auth_dir / f"{name}_cookies.json"

    print(f"\n=== Authentication for {url} ===\n")

    # Check for Edge browser
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "microsoft-edge",
    ]

    edge_path = None
    for path in edge_paths:
        if Path(path).exists() or _command_exists(path):
            edge_path = path
            break

    if not edge_path:
        return {"success": False, "error": "Microsoft Edge not found"}

    print(f"1. Launching Edge with remote debugging on port {debug_port}...")
    print("2. Please sign in to the site when prompted.")
    print("3. Wait for the authentication to complete.\n")

    # Create a temporary user data directory
    import tempfile

    user_data_dir = tempfile.mkdtemp(prefix="edge_auth_")

    # Launch Edge
    edge_cmd = [
        edge_path,
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]

    edge_process = subprocess.Popen(
        edge_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    try:
        # Wait for user to sign in
        cookies = _wait_for_cookie(debug_port, target_cookie, timeout=300)

        if not cookies:
            edge_process.terminate()
            return {"success": False, "error": f"Cookie '{target_cookie}' not found"}

        # Save cookies
        cookie_file.write_text(json.dumps(cookies, indent=2))
        print(f"\nCookies saved to: {cookie_file}")

        # Apply to .env if requested
        if auto_apply:
            if env_file is None:
                env_file = get_deploy_env_file()

            if env_file and env_file.exists():
                _apply_to_env(env_file, name, cookies, target_cookie)
                print(f"Applied to: {env_file}")

                # Restart crawler if requested
                if auto_restart:
                    from .containers import restart_services

                    print("\nRestarting crawler container...")
                    restart_services(services=["crawler"], deploy_dir=deploy_dir)

        # Test authentication if requested
        if auto_test:
            print("\nTesting authentication...")
            success = _test_auth(url, cookies, target_cookie)
            if success:
                print("Authentication successful!")
            else:
                print("Warning: Authentication test failed")

        return {"success": True, "cookie_file": str(cookie_file), "cookies": cookies}

    finally:
        edge_process.terminate()
        # Cleanup temp directory
        import shutil

        try:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass


def _command_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    import shutil

    return shutil.which(cmd) is not None


def _wait_for_cookie(
    debug_port: int, target_cookie: str, timeout: int = 300
) -> Optional[list]:
    """Wait for the target cookie to appear."""
    import httpx

    start_time = time.time()
    check_interval = 2

    while time.time() - start_time < timeout:
        try:
            # Get list of pages from Chrome DevTools Protocol
            response = httpx.get(f"http://127.0.0.1:{debug_port}/json", timeout=2.0)
            pages = response.json()

            if pages:
                # Get cookies from first page
                ws_url = pages[0].get("webSocketDebuggerUrl")
                if ws_url:
                    cookies = _get_cookies_via_cdp(ws_url)
                    for cookie in cookies:
                        if cookie.get("name") == target_cookie:
                            return cookies

        except Exception as e:
            logger.debug(f"Waiting for browser: {e}")

        time.sleep(check_interval)

    return None


def _get_cookies_via_cdp(ws_url: str) -> list:
    """Get cookies via Chrome DevTools Protocol WebSocket."""
    try:
        import websocket

        ws = websocket.create_connection(ws_url, timeout=5)

        # Send command to get cookies
        ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))

        # Get response
        response = json.loads(ws.recv())
        ws.close()

        if "result" in response:
            cookies: List[Any] = response["result"].get("cookies", [])
            return cookies
    except ImportError:
        logger.warning("websocket-client not installed, using fallback method")
    except Exception as e:
        logger.debug(f"CDP error: {e}")

    return []


def _apply_to_env(env_file: Path, name: str, cookies: list, target_cookie: str) -> None:
    """Apply cookies to .env file."""
    # Find the target cookie
    cookie_value = None
    for cookie in cookies:
        if cookie.get("name") == target_cookie:
            cookie_value = cookie.get("value")
            break

    if not cookie_value:
        return

    # Read existing .env
    content = env_file.read_text() if env_file.exists() else ""
    lines = content.splitlines()

    # Find and update or add the cookie variable
    var_name = f"AUTH_COOKIE_{name.upper()}"
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{var_name}=") or line.startswith(f"# {var_name}="):
            lines[i] = f'{var_name}="{target_cookie}={cookie_value}"'
            found = True
            break

    if not found:
        lines.append(f'{var_name}="{target_cookie}={cookie_value}"')

    # Also set CRAWLER_AUTH_COOKIE if this is the primary auth
    if not any(line.startswith("CRAWLER_AUTH_COOKIE=") for line in lines):
        lines.append(f'CRAWLER_AUTH_COOKIE="{target_cookie}={cookie_value}"')

    env_file.write_text("\n".join(lines) + "\n")


def _test_auth(url: str, cookies: list, target_cookie: str) -> bool:
    """Test if authentication works."""
    import httpx

    # Build cookie header
    cookie_header = "; ".join(
        f"{c['name']}={c['value']}" for c in cookies if c.get("name") == target_cookie
    )

    try:
        response = httpx.get(
            url,
            headers={"Cookie": cookie_header},
            follow_redirects=True,
            timeout=10.0,
        )
        # If we get 200 and not a login page, consider it successful
        return response.status_code == 200 and "login" not in response.url.path.lower()
    except Exception as e:
        logger.error(f"Auth test failed: {e}")
        return False


def list_saved_credentials() -> list:
    """List all saved authentication credentials."""
    auth_dir = get_auth_dir()
    credentials = []

    for cookie_file in auth_dir.glob("*_cookies.json"):
        name = cookie_file.stem.replace("_cookies", "")
        try:
            data = json.loads(cookie_file.read_text())
            credentials.append(
                {
                    "name": name,
                    "file": str(cookie_file),
                    "cookies": len(data) if isinstance(data, list) else 0,
                }
            )
        except Exception:
            pass

    return credentials


def clear_credentials(name: Optional[str] = None) -> bool:
    """Clear saved credentials."""
    auth_dir = get_auth_dir()

    if name:
        cookie_file = auth_dir / f"{name}_cookies.json"
        if cookie_file.exists():
            cookie_file.unlink()
            return True
        return False
    else:
        # Clear all
        for cookie_file in auth_dir.glob("*_cookies.json"):
            cookie_file.unlink()
        return True

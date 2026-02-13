#!/usr/bin/env python3
"""
HiChat Web Client - Python Version

A lightweight web client for interacting with LLMCrawl gateway service.
This client provides a web UI that proxies requests to the gateway.

Usage:
    python main.py [--port PORT] [--gateway URL] [--no-browser]

Example:
    python main.py --port 8080 --gateway http://localhost:8000
"""

import argparse
import asyncio
import json
import logging
import os
import webbrowser
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Handle both direct execution and module import
try:
    from .msal_auth import MSALAuthClient, create_auth_client_from_env
except ImportError:
    from msal_auth import MSALAuthClient, create_auth_client_from_env

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("hichat")

# Configuration
DEFAULT_PORT = 8080
DEFAULT_GATEWAY_URL = "http://localhost:8000"

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent.absolute()
STATIC_DIR = SCRIPT_DIR / "static"

# FastAPI app
app = FastAPI(
    title="HiChat Web Client",
    description="AI Chat Client for LLMCrawl Gateway",
    version="1.0.0",
)

# Global configuration
config = {
    "gateway_url": DEFAULT_GATEWAY_URL,
    "mode": "service",  # Always service mode in Python version
    "auth_enabled": False,
    "auth_client": None,
    "access_token": None,
}


@app.get("/", response_class=HTMLResponse)
async def serve_index() -> FileResponse:
    """Serve the main HTML page."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Index page not found")
    return FileResponse(index_path, media_type="text/html")


@app.get("/api/config")
async def get_config() -> dict:
    """Return current configuration."""
    return {
        "mode": "service",
        "preferredModel": None,
        "hasServiceConfig": True,
        "hasAzureConfig": False,
        "serviceUrl": config["gateway_url"],
        "authEnabled": config["auth_enabled"],
        "isAuthenticated": config["access_token"] is not None,
    }


@app.get("/api/models")
async def get_models() -> dict:
    """Fetch available models from gateway."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{config['gateway_url']}/api/models/available")
            response.raise_for_status()
            models = response.json()
            return {"models": models}
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch models: {e}")
        raise HTTPException(
            status_code=502, detail=f"Failed to fetch models from gateway: {str(e)}"
        )


@app.post("/api/agent/execute")
async def execute_agent(request: Request) -> JSONResponse:
    """Proxy agent execution requests to the gateway."""
    try:
        body = await request.json()

        logger.info(
            f"Proxying request to gateway: {json.dumps(body, indent=2)[:500]}..."
        )

        # Refresh token if auth is enabled
        if config.get("auth_enabled"):
            auth_client = config.get("auth_client")
            if auth_client:
                # Try silent acquisition to refresh token
                result = auth_client.acquire_token_silent()
                if result:
                    config["access_token"] = result["access_token"]
                else:
                    # If silent refresh fails, clear the stale token
                    config["access_token"] = None

        # Check if we need to acquire a token (initial login or re-login after expiry)
        if not config.get("access_token") and config.get("auth_enabled"):
            auth_client = config.get("auth_client")
            if auth_client:
                logger.info("No token available, triggering sign-in...")
                try:
                    # Try to get token (will prompt for interactive login, no device code fallback)
                    token = auth_client.get_token(
                        force_interactive=False, allow_device_code=False
                    )
                    config["access_token"] = token
                    account = auth_client.get_account_info()
                    logger.info(
                        f"User signed in: {account.get('username') if account else 'unknown'}"
                    )
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Authentication failed: {error_msg}")

                    # Return error immediately so frontend can display it
                    return JSONResponse(
                        status_code=401,
                        content={
                            "error": error_msg,
                            "response": f"❌ **Authentication Failed**\n\n{error_msg}\n\nPlease try again or contact your administrator.",
                        },
                    )

        # Prepare headers with bearer token if authenticated
        headers = {}
        if config.get("access_token"):
            headers["Authorization"] = f"Bearer {config['access_token']}"
            logger.info("Including bearer token in gateway request")

        async with httpx.AsyncClient(
            timeout=1800.0
        ) as client:  # 30 min timeout for slow models like Claude Opus
            response = await client.post(
                f"{config['gateway_url']}/agent/chat", json=body, headers=headers
            )

            # Return response as-is
            return JSONResponse(
                status_code=response.status_code,
                content=(
                    response.json()
                    if response.status_code == 200
                    else {"detail": response.text}
                ),
            )

    except httpx.TimeoutException:
        logger.error("Gateway request timed out")
        raise HTTPException(status_code=504, detail="Gateway request timed out")
    except httpx.HTTPError as e:
        logger.error(f"Gateway request failed: {e}")
        raise HTTPException(status_code=502, detail=f"Gateway request failed: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON in request body")


@app.get("/api/auth/status")
async def get_auth_status() -> JSONResponse:
    """Get authentication status."""
    if not config["auth_enabled"]:
        return JSONResponse({"enabled": False, "authenticated": False})

    auth_client = config.get("auth_client")
    account = auth_client.get_account_info() if auth_client else None

    return JSONResponse(
        {
            "enabled": True,
            "authenticated": config.get("access_token") is not None,
            "account": (
                {
                    "username": account.get("username") if account else None,
                    "name": account.get("name") if account else None,
                }
                if account
                else None
            ),
        }
    )


@app.post("/api/auth/login")
async def login() -> JSONResponse:
    """Trigger interactive login flow."""
    if not config["auth_enabled"]:
        raise HTTPException(status_code=400, detail="Authentication not enabled")

    try:
        auth_client = config.get("auth_client")
        if not auth_client:
            raise HTTPException(status_code=500, detail="Auth client not initialized")

        # Get token (will prompt for interactive login)
        token = auth_client.get_token(force_interactive=False)
        config["access_token"] = token

        account = auth_client.get_account_info()
        logger.info(
            f"User signed in: {account.get('username') if account else 'unknown'}"
        )

        return JSONResponse(
            {
                "success": True,
                "account": (
                    {
                        "username": account.get("username") if account else None,
                        "name": account.get("name") if account else None,
                    }
                    if account
                    else None
                ),
            }
        )

    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


@app.post("/api/auth/logout")
async def logout() -> JSONResponse:
    """Sign out the current user."""
    if not config["auth_enabled"]:
        raise HTTPException(status_code=400, detail="Authentication not enabled")

    try:
        auth_client = config.get("auth_client")
        if auth_client:
            auth_client.sign_out()

        config["access_token"] = None
        logger.info("User signed out")

        return JSONResponse({"success": True})

    except Exception as e:
        logger.error(f"Logout failed: {e}")
        raise HTTPException(status_code=500, detail=f"Logout failed: {str(e)}")


@app.post("/api/auth/refresh")
async def refresh_token() -> JSONResponse:
    """Refresh access token silently."""
    if not config["auth_enabled"]:
        raise HTTPException(status_code=400, detail="Authentication not enabled")

    try:
        auth_client = config.get("auth_client")
        if not auth_client:
            raise HTTPException(status_code=500, detail="Auth client not initialized")

        # Try silent token acquisition
        result = auth_client.acquire_token_silent()
        if result:
            config["access_token"] = result["access_token"]
            return JSONResponse({"success": True, "refreshed": True})
        else:
            # Token expired, need interactive login
            return JSONResponse({"success": False, "requiresLogin": True})

    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/api/agent/cancel/{conversation_id}")
async def cancel_agent_request(conversation_id: str) -> JSONResponse:
    """Cancel an active agent request."""
    try:
        logger.info(f"Sending cancel request for conversation: {conversation_id}")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{config['gateway_url']}/agent/cancel/{conversation_id}"
            )
            return JSONResponse(
                status_code=response.status_code, content=response.json()
            )
    except httpx.HTTPError as e:
        logger.error(f"Cancel request failed: {e}")
        raise HTTPException(status_code=502, detail=f"Cancel request failed: {str(e)}")


@app.get("/api/agent/status/{conversation_id}")
async def get_agent_status(conversation_id: str) -> JSONResponse:
    """Get the status of an agent request."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{config['gateway_url']}/agent/status/{conversation_id}"
            )
            return JSONResponse(
                status_code=response.status_code, content=response.json()
            )
    except httpx.HTTPError as e:
        logger.error(f"Status request failed: {e}")
        raise HTTPException(status_code=502, detail=f"Status request failed: {str(e)}")


# Mount static files (CSS, JS)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def load_environment_file(deploy_dir: Optional[str] = None) -> None:
    """Load environment variables from .env file.

    Args:
        deploy_dir: Optional path to deploy directory containing .env file

    Searches for .env file in the following order:
    1. Custom deploy directory (if provided via --deploy-dir)
    2. Current working directory (.env)
    3. deploy folder (./deploy/.env) - for source development
    4. llmcrawl-deploy folder (./llmcrawl-deploy/.env) - for wheel package deployment
    5. User's home directory (~/.llmcrawl/.env)
    """
    env_locations = []

    # Add custom deploy directory if provided
    if deploy_dir:
        custom_path = Path(deploy_dir) / ".env"
        env_locations.append(custom_path)
        logger.info(f"Custom deploy directory specified: {custom_path}")

    # Standard search locations
    env_locations.extend(
        [
            Path.cwd() / ".env",
            Path.cwd() / "deploy" / ".env",
            Path.cwd() / "llmcrawl-deploy" / ".env",
            Path.home() / ".llmcrawl" / ".env",
        ]
    )

    for env_path in env_locations:
        if env_path.exists():
            logger.info(f"Loading environment from {env_path}")
            load_dotenv(env_path, override=False)  # Don't override existing env vars
            return

    logger.info("No .env file found, using existing environment variables")


def open_browser(url: str, delay: float = 1.0) -> None:
    """Open the default browser after a short delay."""

    async def _open() -> None:
        await asyncio.sleep(delay)
        try:
            webbrowser.open(url)
            logger.info(f"Opened browser to {url}")
        except Exception as e:
            logger.warning(f"Could not open browser: {e}")
            print(f"\nPlease open your browser and navigate to: {url}")

    asyncio.create_task(_open())


def main() -> None:
    """Main entry point."""
    # Parse args first to get deploy_dir if specified
    parser = argparse.ArgumentParser(
        description="HiChat Web Client - AI Chat Interface for LLMCrawl"
    )
    parser.add_argument(
        "--deploy-dir",
        type=str,
        help="Path to deploy directory containing .env file (e.g., ../../deploy)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=int(os.environ.get("HICHAT_PORT", DEFAULT_PORT)),
        help=f"Port to run the web server on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--gateway",
        "-g",
        type=str,
        default=os.environ.get("LLMCRAWL_GATEWAY_URL", DEFAULT_GATEWAY_URL),
        help=f"LLMCrawl gateway URL (default: {DEFAULT_GATEWAY_URL})",
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Don't open browser automatically"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )

    args = parser.parse_args()

    # Load environment variables from .env file if available
    load_environment_file(deploy_dir=args.deploy_dir)

    # Update global config
    config["gateway_url"] = args.gateway.rstrip("/")

    # Always initialize MSAL authentication (required for Azure Foundry)
    try:
        logger.info("Initializing MSAL authentication...")
        auth_client = create_auth_client_from_env()
        config["auth_enabled"] = True
        config["auth_client"] = auth_client

        # Try to get token silently (from cache)
        result = auth_client.acquire_token_silent()
        if result:
            config["access_token"] = result["access_token"]
            account = auth_client.get_account_info()
            logger.info(
                f"Signed in from cache: {account.get('username') if account else 'unknown'}"
            )
        else:
            # No cached token - user will need to sign in on first request
            logger.info("No cached token found.")
            logger.info(
                "You will be prompted to sign in when you send your first message."
            )

    except Exception as e:
        logger.error(f"Authentication initialization failed: {e}")
        logger.error("Entra ID authentication is required to use Azure Foundry.")
        logger.error(
            "Please ensure ENTRA_CLIENT_ID, ENTRA_TENANT_ID, and AZURE_FOUNDRY_SCOPE are set."
        )
        raise SystemExit(1)

    url = f"http://{args.host}:{args.port}"

    print("\n" + "=" * 60)
    print("🤖 HiChat Web Client")
    print("=" * 60)
    print(f"  Gateway URL:  {config['gateway_url']}")
    print(f"  Web UI:       {url}")
    if config["auth_enabled"]:
        print(f"  Auth:         Enabled (Entra ID)")
    print("=" * 60)
    print("\nPress Ctrl+C to stop\n")

    # Schedule browser open if not disabled
    if not args.no_browser:

        @app.on_event("startup")
        async def startup_event() -> None:
            open_browser(url)

    # Run the server
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

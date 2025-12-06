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

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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

        async with httpx.AsyncClient(
            timeout=600.0
        ) as client:  # 10 min timeout for long requests
            response = await client.post(
                f"{config['gateway_url']}/agent/chat", json=body
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
    parser = argparse.ArgumentParser(
        description="HiChat Web Client - AI Chat Interface for LLMCrawl"
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

    # Update global config
    config["gateway_url"] = args.gateway.rstrip("/")

    url = f"http://{args.host}:{args.port}"

    print("\n" + "=" * 60)
    print("🤖 HiChat Web Client")
    print("=" * 60)
    print(f"  Gateway URL:  {config['gateway_url']}")
    print(f"  Web UI:       {url}")
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

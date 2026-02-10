#!/usr/bin/env python3
"""
Simulate Claude Code Console
Test tool to authenticate with Claude (or use env token) and retrieve available models.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Configure Logging to see auth details
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # Reduce noise

# Add clients/hichat to path to reuse auth logic
PROJECT_ROOT = Path(__file__).parent.parent
HICHAT_DIR = PROJECT_ROOT / "clients" / "hichat"
sys.path.insert(0, str(HICHAT_DIR))

try:
    from claude_auth import ClaudeAuthClient, create_claude_auth_client_from_env
except ImportError:
    print(
        "Error: Could not import claude_auth. Make sure clients/hichat is in python path."
    )
    sys.exit(1)

# Load Hichat Env
env_path = HICHAT_DIR / ".env"
if env_path.exists():
    print(f"Loading env from {env_path}")
    load_dotenv(env_path)
else:
    print(f"Warning: {env_path} not found.")

GATEWAY_URL = os.getenv("LLMCRAWL_GATEWAY_URL", "http://localhost:8000")


async def get_models(token=None):
    """Fetch models from Gateway with Claude Auth headers."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Provider-Auth"] = "claude"
        print(f"Using Bearer Token: {token[:10]}...")

    print(f"Fetching models from {GATEWAY_URL}/api/models/available...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{GATEWAY_URL}/api/models/available", headers=headers
            )
            response.raise_for_status()
            models = response.json()
            return models
    except Exception as e:
        print(f"Error fetching models: {e}")
        if hasattr(e, "response"):
            print(f"Response: {e.response.text}")
        return []


async def main():
    print("=== Claude Code Console Simulator ===")

    # Check for Manual Token Override
    manual_token = os.getenv("CLAUDE_ACCESS_TOKEN")
    token = None

    if manual_token and len(manual_token) > 20:
        print("Using CLAUDE_ACCESS_TOKEN from environment.")
        token = manual_token
    else:
        print("No CLAUDE_ACCESS_TOKEN found. Attempting OAuth flow...")
        client = create_claude_auth_client_from_env()

        # Check cache first
        token = client.get_cached_token()
        if token:
            print("Found cached OAuth token.")
        else:
            print("No cached token. Starting interactive login (if you want)...")
            choice = input("Start Browser Login? (y/n): ")
            if choice.lower() == "y":
                try:
                    # Run getting token
                    token = await asyncio.to_thread(
                        client.get_token, force_interactive=True
                    )
                    print("Login successful!")
                except Exception as e:
                    print(f"Login failed: {e}")
                    return
            else:
                print("Skipping login.")

    # Get Models
    print("\n--- Retrieving Models ---")
    models = await get_models(token)

    claude_models = [m for m in models if m.get("provider_type") == "claude"]
    other_models = [m for m in models if m.get("provider_type") != "claude"]

    print(f"\nFound {len(models)} total models.")

    if claude_models:
        print(f"\n--- Claude Models ({len(claude_models)}) ---")
        for m in claude_models:
            print(f" - {m['name']} (Provider: {m['provider']})")
    else:
        print("\nNo Claude models found (or Auth failed/missing).")

    if other_models:
        print(f"\n--- Other Models ({len(other_models)}) ---")
        for m in other_models[:5]:  # Show first 5
            print(f" - {m['name']} ({m['provider_type']})")
        if len(other_models) > 5:
            print("   ...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExited.")

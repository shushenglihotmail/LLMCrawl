#!/usr/bin/env python3
"""
Automatic Session Refresh for www.osgwiki.com

Monitors the authentication session and automatically refreshes it when expired.
Can be run manually or scheduled as a cron job/Windows Task.

Usage:
    python tools/refresh_auth.py --name www_osgwiki_com
    python tools/refresh_auth.py --name www_osgwiki_com --check-only
    python tools/refresh_auth.py --name www_osgwiki_com --force
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import requests


class AuthSessionMonitor:
    """Monitor and refresh authentication sessions."""

    def __init__(self, auth_dir: str = ".auth"):
        self.auth_dir = Path(auth_dir)
        self.auth_dir.mkdir(exist_ok=True)

    def load_auth_file(self, name: str) -> Optional[Dict]:
        """Load authentication file."""
        auth_file = self.auth_dir / f"{name}.json"
        if not auth_file.exists():
            print(f"❌ Auth file not found: {auth_file}")
            return None

        with open(auth_file) as f:
            return json.load(f)

    def test_auth(self, url: str, cookies: Dict) -> bool:
        """Test if current authentication is still valid."""
        print(f"Testing authentication for: {url}")

        try:
            response = requests.get(
                url,
                cookies=cookies,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                timeout=10,
                allow_redirects=True,
            )

            if response.status_code == 200:
                # Check if we're actually logged in
                content = response.text.lower()
                if "sign in" in content or "login" in content:
                    print("❌ Session expired (login page detected)")
                    return False
                else:
                    print("✅ Authentication valid")
                    return True
            elif response.status_code == 401:
                print("❌ Session expired (401 Unauthorized)")
                return False
            else:
                print(f"⚠ Unexpected status: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Error testing authentication: {e}")
            return False

    def get_cookies_from_auth(self, auth_data: Dict) -> Dict:
        """Extract cookies from auth data."""
        cookies = {}
        for cookie in auth_data.get("storage_state", {}).get("cookies", []):
            if cookie["domain"] in [auth_data["domain"], f".{auth_data['domain']}"]:
                cookies[cookie["name"]] = cookie["value"]
        return cookies

    async def refresh_session(self, url: str, name: str) -> bool:
        """Refresh the authentication session using interactive auth."""
        print(f"\n🔄 Refreshing authentication session for {name}...")
        print("=" * 60)

        # Import here to avoid circular dependency
        from tools.interactive_auth import InteractiveAuth

        auth_tool = InteractiveAuth(auth_dir=str(self.auth_dir))

        try:
            # Run interactive authentication
            await auth_tool.authenticate(url=url, name=name, timeout=300)
            print("\n✅ Session refreshed successfully!")
            return True

        except Exception as e:
            print(f"\n❌ Failed to refresh session: {e}")
            return False

    def apply_to_env(self, name: str) -> bool:
        """Apply the authentication to .env file."""
        print(f"\n📝 Applying authentication to .env...")

        import subprocess

        try:
            result = subprocess.run(
                ["pwsh", "-File", "tools/apply_auth.ps1", "-AuthName", name],
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
            )

            if result.returncode == 0:
                print("✅ Applied to .env successfully")
                return True
            else:
                print(f"❌ Failed to apply to .env: {result.stderr}")
                return False

        except Exception as e:
            print(f"❌ Error applying to .env: {e}")
            return False


async def main():
    parser = argparse.ArgumentParser(
        description="Monitor and refresh authentication sessions"
    )
    parser.add_argument("--name", required=True, help="Name of the auth configuration")
    parser.add_argument(
        "--url",
        help="URL to test (default: from auth file)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check if auth is valid, don't refresh",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force refresh even if current session is valid",
    )
    parser.add_argument(
        "--apply-env",
        action="store_true",
        default=True,
        help="Apply to .env after refresh (default: True)",
    )

    args = parser.parse_args()

    monitor = AuthSessionMonitor()

    # Load existing auth
    auth_data = monitor.load_auth_file(args.name)
    if not auth_data:
        return 1

    url = args.url or auth_data.get("url")
    if not url:
        print("❌ No URL specified and none found in auth file")
        return 1

    # Get cookies and test
    cookies = monitor.get_cookies_from_auth(auth_data)
    is_valid = monitor.test_auth(url, cookies)

    if args.check_only:
        return 0 if is_valid else 1

    # Decide whether to refresh
    needs_refresh = not is_valid or args.force

    if needs_refresh:
        print("\n⚠ Session needs refresh" if not is_valid else "\n🔄 Forcing refresh")

        success = await monitor.refresh_session(url, args.name)

        if success and args.apply_env:
            monitor.apply_to_env(args.name)

        return 0 if success else 1
    else:
        print("\n✓ Session is valid, no refresh needed")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

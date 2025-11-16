"""
Interactive Browser Authentication Tool for FireCrawl

This tool launches Microsoft Edge browser, lets you authenticate to a site
interactively, then captures and saves the authentication credentials
(cookies, tokens) for FireCrawl to reuse.

Usage:
    python tools/interactive_auth.py https://internal-site.com
    python tools/interactive_auth.py --name sharepoint https://company.sharepoint.com
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright


class InteractiveAuth:
    """Interactive browser authentication tool."""

    def __init__(self, auth_dir: str = ".auth"):
        """
        Initialize the interactive auth tool.

        Args:
            auth_dir: Directory to store auth credentials
        """
        self.auth_dir = Path(auth_dir)
        self.auth_dir.mkdir(exist_ok=True)

    async def authenticate(
        self,
        url: str,
        name: Optional[str] = None,
        timeout: int = 120,
        headless: bool = False,
    ) -> Dict:
        """
        Launch browser for interactive authentication.

        Args:
            url: The URL to authenticate to
            name: Profile name for these credentials (default: domain name)
            timeout: Seconds to wait for user to complete authentication
            headless: Run browser in headless mode

        Returns:
            Dict with authentication data
        """
        if not name:
            parsed = urlparse(url)
            name = parsed.netloc.replace(".", "_")

        print(f"\n🌐 Launching Microsoft Edge for {url}")
        print(f"📝 Profile name: {name}")
        print(f"⏱️  You have {timeout} seconds to complete authentication")
        print("\n" + "=" * 60)
        print("INSTRUCTIONS:")
        print("1. Microsoft Edge browser window will open")
        print("2. You will be redirected to Microsoft login")
        print("3. Sign in with your credentials + complete MFA")
        print("4. WAIT for redirect back to www.osgwiki.com")
        print("5. VERIFY you can see the protected wiki content")
        print("6. ⚠️  PRESS ENTER in this terminal (DON'T close browser yet!)")
        print("7. Script will then capture credentials and close browser")
        print()
        print("⚠️  IMPORTANT: Keep browser open until script captures!")
        print("=" * 60 + "\n")

        async with async_playwright() as p:
            # Launch Microsoft Edge browser with full UI
            # Note: We can't use launch_persistent_context if Edge is already running
            # Instead, use regular browser and capture storage state after auth
            browser = await p.chromium.launch(
                headless=headless,
                channel="msedge",  # Use Microsoft Edge
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )

            # Create context with realistic settings
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
                ),
                locale="en-US",
                timezone_id="America/New_York",
            )

            page = await context.new_page()

            # Set up request/response interception to capture Bearer tokens
            captured_tokens = []

            async def handle_response(response):
                """Intercept responses to extract Bearer tokens"""
                try:
                    # Check Authorization header in request
                    request = response.request
                    auth_header = request.headers.get("authorization", "")
                    if auth_header.startswith("Bearer "):
                        token = auth_header.replace("Bearer ", "")
                        if token and token not in captured_tokens:
                            captured_tokens.append(token)
                            print(f"   🎫 Captured Bearer token from request")

                    # Check for tokens in response headers
                    response_auth = response.headers.get("authorization", "")
                    if response_auth.startswith("Bearer "):
                        token = response_auth.replace("Bearer ", "")
                        if token and token not in captured_tokens:
                            captured_tokens.append(token)
                            print(f"   🎫 Captured Bearer token from response")

                    # Check for tokens in response body (JSON)
                    if "application/json" in response.headers.get("content-type", ""):
                        try:
                            body = await response.json()
                            # Common OAuth2 token fields
                            for field in [
                                "access_token",
                                "id_token",
                                "token",
                                "bearer_token",
                            ]:
                                if field in body and body[field]:
                                    token = body[field]
                                    if token not in captured_tokens:
                                        captured_tokens.append(token)
                                        print(
                                            f"   🎫 Captured {field} from response body"
                                        )
                        except:
                            pass
                except Exception as e:
                    pass  # Silently ignore errors in interception

            page.on("response", handle_response)

            # Navigate to the URL
            print(f"🔄 Loading {url}...")
            print("⏳ The page will redirect to Microsoft login - this is expected")
            print("   Monitoring network traffic for OAuth2 tokens...")
            print("   Browser should stay open throughout the entire process")
            print()

            try:
                # Navigate - don't use complex wait conditions that might trigger closure
                await page.goto(url, wait_until="commit", timeout=60000)
                print("   ✅ Initial navigation started")
            except Exception as e:
                print(f"   ⚠️  Navigation message: {e}")
                print("   Continuing anyway - browser should still be open")

            await asyncio.sleep(
                2
            )  # Give browser time to complete redirects and token requests

            print("✅ Browser is open - please complete authentication:")
            print("   1. Sign in with your Microsoft credentials")
            print("   2. Complete MFA/2FA if prompted")
            print("   3. ⚠️  WAIT for redirect back to www.osgwiki.com")
            print("   4. ⚠️  VERIFY you see the actual wiki page content")
            print()
            print("💡 The page will redirect multiple times - this is NORMAL!")
            print("💡 Keep the browser open - it should NOT auto-close")
            print()
            print("=" * 60)
            print("⏸️  When you can see the wiki content, press ENTER here")
            print("=" * 60)
            print()

            # Wait ONLY for user to press Enter - no automatic detection
            try:
                import sys

                # Simple blocking wait for Enter key
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, sys.stdin.readline)

                print("\n✅ Enter pressed. Capturing credentials...")

            except KeyboardInterrupt:
                print("\n✋ Ctrl+C pressed. Capturing credentials...")

            # Check current URL from the active page
            try:
                # Get the last active page (might have changed due to redirects)
                pages = context.pages
                if pages:
                    page = pages[-1]  # Use the most recent page
                    current_url = page.url
                    print(f"📍 Final page: {current_url}")

                    # If we're not on the target domain, warn user
                    target_domain = urlparse(url).netloc
                    current_domain = urlparse(current_url).netloc
                    if target_domain not in current_domain:
                        print(
                            f"⚠️  WARNING: You are on {current_domain}, not {target_domain}"
                        )
                        print(
                            f"⚠️  Make sure you completed login and viewed the protected content!"
                        )
                else:
                    print("⚠️  No pages found in context")
            except Exception:
                print("📍 Browser was closed, proceeding with capture...")

            # Capture entire storage state (includes cookies across all domains)
            print(
                "💾 Capturing storage state (cookies, localStorage, sessionStorage)..."
            )
            storage_state = await context.storage_state()
            cookies = storage_state.get("cookies", [])
            print(f"📦 Captured {len(cookies)} cookies")

            # Show distribution of cookies by domain
            from collections import Counter

            cookie_domains = Counter(c.get("domain", "unknown") for c in cookies)
            print(f"   Cookie distribution:")
            for domain, count in sorted(cookie_domains.items(), key=lambda x: -x[1]):
                print(f"   - {domain}: {count} cookies")

            # Capture local storage
            local_storage = {}
            try:
                local_storage = await page.evaluate(
                    """() => {
                    const storage = {};
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        storage[key] = localStorage.getItem(key);
                    }
                    return storage;
                }"""
                )
                print(f"💾 Captured {len(local_storage)} localStorage items")
            except Exception as e:
                print(f"⚠️  Could not capture localStorage: {e}")

            # Capture session storage
            session_storage = {}
            try:
                session_storage = await page.evaluate(
                    """() => {
                    const storage = {};
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        storage[key] = sessionStorage.getItem(key);
                    }
                    return storage;
                }"""
                )
                print(f"💾 Captured {len(session_storage)} sessionStorage items")
            except Exception as e:
                print(f"⚠️  Could not capture sessionStorage: {e}")

            # Combine captured tokens from interception and page analysis
            print("🔍 Analyzing for bearer tokens...")
            page_tokens = await self._extract_bearer_tokens(page)
            all_bearer_tokens = list(set(captured_tokens + page_tokens))  # Deduplicate

            if all_bearer_tokens:
                print(f"🎫 Found {len(all_bearer_tokens)} bearer token(s)")
                print(
                    f"   Token preview: {all_bearer_tokens[0][:50]}..."
                    if all_bearer_tokens[0] and len(all_bearer_tokens[0]) > 50
                    else ""
                )
            else:
                print(f"⚠️  No bearer tokens captured - site may use cookie-based auth")

            await browser.close()

        # Build auth data - include storage_state for Playwright
        auth_data = {
            "name": name,
            "url": url,
            "domain": urlparse(url).netloc,
            "captured_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(hours=24)).isoformat(),
            "storage_state": storage_state,  # Full Playwright storage state
            "cookies": [
                {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ""),
                    "path": c.get("path", "/"),
                    "expires": c.get("expires", -1),
                    "httpOnly": c.get("httpOnly", False),
                    "secure": c.get("secure", False),
                    "sameSite": c.get("sameSite", "Lax"),
                }
                for c in cookies
            ],
            "local_storage": local_storage,
            "session_storage": session_storage,
            "bearer_tokens": all_bearer_tokens,
        }

        # Save to file
        auth_file = self.auth_dir / f"{name}.json"
        with open(auth_file, "w") as f:
            json.dump(auth_data, f, indent=2)

        print(f"\n✅ Authentication saved to: {auth_file}")
        print(f"📊 Summary:")
        print(f"   - Cookies: {len(cookies)}")
        print(f"   - LocalStorage: {len(local_storage)}")
        print(f"   - SessionStorage: {len(session_storage)}")
        print(f"   - Bearer Tokens: {len(all_bearer_tokens)}")

        # Show expiration info
        expires = self._find_expiration(cookies)
        if expires:
            print(f"\n⏰ Credentials expire: {expires}")
        else:
            print(
                "\n⏰ No explicit expiration found - "
                "credentials may expire with browser session"
            )

        return auth_data

    async def _extract_bearer_tokens(self, page) -> List[str]:
        """Try to extract bearer tokens from page."""
        tokens = []

        # Check localStorage for tokens
        try:
            storage_tokens = await page.evaluate(
                """() => {
                const tokens = [];
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    const value = localStorage.getItem(key);
                    // Look for JWT-like patterns
                    if (value && value.match(/^eyJ[A-Za-z0-9-_=]+\\.eyJ[A-Za-z0-9-_=]+\\.[A-Za-z0-9-_.+/=]*$/)) {
                        tokens.push(value);
                    }
                }
                return tokens;
            }"""
            )
            tokens.extend(storage_tokens)
        except Exception:
            pass

        return tokens

    def _find_expiration(self, cookies: List[Dict]) -> Optional[str]:
        """Find earliest expiration from cookies."""
        expires_dates = []
        for cookie in cookies:
            if cookie.get("expires") and cookie["expires"] > 0:
                try:
                    expires = datetime.fromtimestamp(cookie["expires"])
                    expires_dates.append(expires)
                except Exception:
                    pass

        if expires_dates:
            earliest = min(expires_dates)
            return earliest.strftime("%Y-%m-%d %H:%M:%S")
        return None

    def apply_to_env(self, name: str, env_file: str = ".env") -> bool:
        """
        Apply saved auth credentials to .env file.

        Args:
            name: Profile name
            env_file: Path to .env file

        Returns:
            True if successful
        """
        auth_file = self.auth_dir / f"{name}.json"
        if not auth_file.exists():
            print(f"❌ Auth profile '{name}' not found")
            self.list_profiles()
            return False

        with open(auth_file, "r") as f:
            auth_data = json.load(f)

        # Check if expired
        if auth_data.get("expires_at"):
            expires = datetime.fromisoformat(auth_data["expires_at"])
            if datetime.now() > expires:
                print(
                    f"⚠️  Warning: Credentials expired at " f"{auth_data['expires_at']}"
                )
                print("   You may need to re-authenticate")

        print(f"\n📝 Applying auth profile '{name}' to {env_file}")

        # Store FULL cookie objects with all attributes (domain, httpOnly, secure, etc.)
        # This is needed for proper authentication in Playwright
        cookies_list = auth_data["cookies"]

        # Build headers dict (include bearer tokens if found)
        headers_dict = {}
        if auth_data.get("bearer_tokens"):
            headers_dict["Authorization"] = f"Bearer {auth_data['bearer_tokens'][0]}"

        # Read current .env
        env_path = Path(env_file)
        env_lines = []
        if env_path.exists():
            with open(env_path, "r") as f:
                env_lines = f.readlines()

        # Remove old auth settings
        new_lines = []
        skip_next = False
        for line in env_lines:
            if any(
                line.startswith(prefix)
                for prefix in [
                    "FIRECRAWL_AUTH_TYPE=",
                    "FIRECRAWL_AUTH_COOKIES=",
                    "FIRECRAWL_AUTH_HEADERS=",
                    "FIRECRAWL_AUTH_STORAGE_STATE=",
                ]
            ):
                continue
            new_lines.append(line)

        # Add new auth settings
        new_lines.append(
            f"\n# Auth settings for {name} (captured at "
            f"{auth_data['captured_at']})\n"
        )
        new_lines.append("FIRECRAWL_AUTH_TYPE=cookies\n")
        # Store full cookie objects (not just name/value) to preserve domain, httpOnly, secure, etc.
        new_lines.append(f"FIRECRAWL_AUTH_COOKIES={json.dumps(cookies_list)}\n")
        # Also store the full storage_state for Playwright to restore entire session
        if auth_data.get("storage_state"):
            new_lines.append(
                f"FIRECRAWL_AUTH_STORAGE_STATE={json.dumps(auth_data['storage_state'])}\n"
            )
        if headers_dict:
            new_lines.append(f"FIRECRAWL_AUTH_HEADERS={json.dumps(headers_dict)}\n")

        # Add domain to allowed domains if not present
        domain = auth_data["domain"]
        allowed_domains_found = False
        for i, line in enumerate(new_lines):
            if line.startswith("ALLOWED_DOMAINS="):
                allowed_domains_found = True
                domains = line.split("=", 1)[1].strip()
                if domain not in domains:
                    new_lines[i] = f"ALLOWED_DOMAINS={domains},{domain}\n"
                    print(f"   ✓ Added {domain} to ALLOWED_DOMAINS")
                break

        if not allowed_domains_found:
            new_lines.append(f"ALLOWED_DOMAINS={domain}\n")
            print(f"   ✓ Added ALLOWED_DOMAINS={domain}")

        # Write back
        with open(env_path, "w") as f:
            f.writelines(new_lines)

        print(f"✅ Updated {env_file}")
        print(f"\n📋 Next steps:")
        print(f"   1. Restart crawler: docker-compose restart crawler")
        print(f"   2. Test: .\\scripts\\test-internal-auth.ps1 {auth_data['url']}")

        return True

    def list_profiles(self):
        """List all saved auth profiles."""
        profiles = list(self.auth_dir.glob("*.json"))

        if not profiles:
            print("\n📭 No auth profiles saved yet")
            print("   Use: python tools/interactive_auth.py <url>")
            return

        print(f"\n📚 Saved auth profiles ({len(profiles)}):")
        print("=" * 60)

        for profile_file in sorted(profiles):
            try:
                with open(profile_file, "r") as f:
                    data = json.load(f)

                name = data["name"]
                url = data["url"]
                captured = data["captured_at"]
                expires = data.get("expires_at", "Unknown")

                print(f"\n🔐 {name}")
                print(f"   URL: {url}")
                print(f"   Captured: {captured}")
                print(f"   Expires: {expires}")

                # Check if expired
                if expires != "Unknown":
                    expires_dt = datetime.fromisoformat(expires)
                    if datetime.now() > expires_dt:
                        print(f"   ⚠️  STATUS: EXPIRED")
                    else:
                        remaining = expires_dt - datetime.now()
                        hours = remaining.total_seconds() / 3600
                        print(f"   ✅ STATUS: Valid ({hours:.1f} hours remaining)")

            except Exception as e:
                print(f"   ⚠️  Error reading {profile_file.name}: {e}")

        print("\n" + "=" * 60)
        print("\nTo apply: python tools/interactive_auth.py " "--apply <profile_name>")

    def delete_profile(self, name: str) -> bool:
        """Delete a saved auth profile."""
        auth_file = self.auth_dir / f"{name}.json"
        if not auth_file.exists():
            print(f"❌ Profile '{name}' not found")
            return False

        auth_file.unlink()
        print(f"✅ Deleted profile '{name}'")
        return True


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Interactive Browser Authentication for FireCrawl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Authenticate to a site
  python tools/interactive_auth.py https://internal-site.com

  # Authenticate with custom profile name
  python tools/interactive_auth.py --name sharepoint https://company.sharepoint.com

  # Apply saved credentials to .env
  python tools/interactive_auth.py --apply sharepoint

  # List saved profiles
  python tools/interactive_auth.py --list

  # Delete a profile
  python tools/interactive_auth.py --delete sharepoint
        """,
    )

    parser.add_argument("url", nargs="?", help="URL to authenticate to")
    parser.add_argument("--name", "-n", help="Profile name for these credentials")
    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=120,
        help="Authentication timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run browser in headless mode"
    )
    parser.add_argument(
        "--apply", "-a", metavar="PROFILE", help="Apply saved profile to .env file"
    )
    parser.add_argument(
        "--list", "-l", action="store_true", help="List saved auth profiles"
    )
    parser.add_argument(
        "--delete", "-d", metavar="PROFILE", help="Delete a saved profile"
    )
    parser.add_argument(
        "--auth-dir",
        default=".auth",
        help="Directory to store auth data (default: .auth)",
    )

    args = parser.parse_args()

    auth_tool = InteractiveAuth(auth_dir=args.auth_dir)

    # List profiles
    if args.list:
        auth_tool.list_profiles()
        return

    # Delete profile
    if args.delete:
        auth_tool.delete_profile(args.delete)
        return

    # Apply profile
    if args.apply:
        success = auth_tool.apply_to_env(args.apply)
        sys.exit(0 if success else 1)

    # Authenticate
    if not args.url:
        parser.print_help()
        print("\n❌ Error: URL required for authentication")
        print("   Use --list to see saved profiles")
        print("   Use --apply to apply a saved profile")
        sys.exit(1)

    try:
        await auth_tool.authenticate(
            url=args.url,
            name=args.name,
            timeout=args.timeout,
            headless=args.headless,
        )

        print("\n" + "=" * 60)
        print("🎉 Authentication captured successfully!")
        print("=" * 60)
        print("\n📋 Next steps:")
        print(f"   1. Apply to .env:")
        print(
            f"      python tools/interactive_auth.py "
            f"--apply {args.name or urlparse(args.url).netloc.replace('.', '_')}"
        )
        print(f"   2. Restart crawler:")
        print(f"      docker-compose restart crawler")
        print(f"   3. Test crawling:")
        print(f"      .\\scripts\\test-internal-auth.ps1 {args.url}")

    except KeyboardInterrupt:
        print("\n\n✋ Authentication cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

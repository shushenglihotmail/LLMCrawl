#!/usr/bin/env python3
"""
Authentication Tool for Internal Sites (Edge Remote Debugging)

This is the primary tool for authenticating to internal Microsoft sites
(e.g., www.osgwiki.com) that use Azure App Service Easy Auth or similar
cookie-based authentication.

The tool:
1. Launches Microsoft Edge with remote debugging enabled
2. Lets you authenticate manually in the browser
3. Extracts authentication cookies via Chrome DevTools Protocol (CDP)
4. Saves credentials to .auth/ directory
5. Applies credentials to .env file
6. Recreates crawler container to load new credentials
7. Tests authentication by crawling the target URL

Usage:
    # Full automated workflow (recommended)
    python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page

    # Skip auto-apply to .env (just save cookies)
    python tools/msauth/authenticate.py https://www.osgwiki.com --no-apply

    # Skip container restart
    python tools/msauth/authenticate.py https://www.osgwiki.com --no-restart

    # Skip authentication test
    python tools/msauth/authenticate.py https://www.osgwiki.com --no-test

Why this approach works:
    - Bypasses cookie encryption issues (Edge decrypts cookies for CDP access)
    - Uses a temporary profile to avoid "profile switching" conflicts
    - Captures ALL cookies including HttpOnly cookies like AppServiceAuthSession
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse


def find_project_root() -> Path:
    """Find the project root directory (where .env is located)."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "deploy" / ".env").exists():
            return parent
        if (parent / ".env").exists():
            return parent
    return Path.cwd()


PROJECT_ROOT = find_project_root()
AUTH_DIR = PROJECT_ROOT / ".auth"
ENV_FILE = PROJECT_ROOT / "deploy" / ".env"
DEPLOY_DIR = PROJECT_ROOT / "deploy"


def launch_edge_with_debugging(
    debug_port: int = 9222,
    user_data_dir: Optional[str] = None,
    initial_url: Optional[str] = None,
) -> subprocess.Popen:
    """
    Launch Microsoft Edge with remote debugging enabled.

    Args:
        debug_port: Port for remote debugging (default: 9222)
        user_data_dir: Temp profile directory to avoid profile conflicts
        initial_url: Optional URL to open on launch

    Returns:
        subprocess.Popen object for the Edge process
    """
    if user_data_dir is None:
        user_data_dir = "C:\\Temp\\EdgeDebugProfile"

    # Find Edge executable
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]

    edge_path = None
    for path in edge_paths:
        if Path(path).exists():
            edge_path = path
            break

    if not edge_path:
        raise FileNotFoundError(
            "Microsoft Edge not found. Please install Edge or update the path."
        )

    # Build command
    cmd = [
        edge_path,
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={user_data_dir}",
        "--disable-background-networking",
        "--disable-client-side-phishing-detection",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-hang-monitor",
        "--disable-popup-blocking",
        "--disable-prompt-on-repost",
        "--disable-sync",
        "--disable-translate",
        "--metrics-recording-only",
        "--no-first-run",
        "--safebrowsing-disable-auto-update",
    ]

    if initial_url:
        cmd.append(initial_url)

    print(f"🚀 Launching Edge with remote debugging on port {debug_port}...")
    print(f"   Profile directory: {user_data_dir}")

    process = subprocess.Popen(cmd)
    time.sleep(3)  # Give Edge time to start

    return process


def get_cookies_from_debug_browser(
    debug_port: int = 9222,
    target_cookie: str = "AppServiceAuthSession",
    target_domain: Optional[str] = None,
) -> Dict:
    """
    Connect to Edge via CDP and extract cookies.

    Args:
        debug_port: Port where Edge is listening for debug connections
        target_cookie: Specific cookie name to look for
        target_domain: Optional domain filter for cookies

    Returns:
        Dict with cookies and metadata
    """
    from playwright.sync_api import sync_playwright

    print(f"\n🔌 Connecting to Edge on localhost:{debug_port}...")

    result = {
        "success": False,
        "target_cookie": None,
        "all_cookies": [],
        "domain_cookies": [],
        "error": None,
    }

    try:
        with sync_playwright() as p:
            # Connect to the existing browser on the debug port
            browser = p.chromium.connect_over_cdp(f"http://localhost:{debug_port}")

            if not browser.contexts:
                result["error"] = "No browser contexts found. Is a page open in Edge?"
                return result

            # Get the existing context (your open tab)
            context = browser.contexts[0]

            # Get all cookies from the browser's memory
            all_cookies = context.cookies()
            result["all_cookies"] = all_cookies

            print(f"📦 Retrieved {len(all_cookies)} total cookies")

            # Filter by domain if specified
            if target_domain:
                domain_cookies = [
                    c for c in all_cookies if target_domain in c.get("domain", "")
                ]
                result["domain_cookies"] = domain_cookies
                print(
                    f"🔍 Found {len(domain_cookies)} cookies "
                    f"for domain '{target_domain}'"
                )

                # Show domain cookies
                for c in domain_cookies:
                    masked_value = (
                        c["value"][:20] + "..." if len(c["value"]) > 20 else c["value"]
                    )
                    http_only = c.get("httpOnly", False)
                    print(f"   - {c['name']}: {masked_value} (httpOnly={http_only})")

            # Find the specific Auth cookie
            found_cookie = next(
                (c for c in all_cookies if target_cookie in c.get("name", "")), None
            )

            if found_cookie:
                result["success"] = True
                result["target_cookie"] = found_cookie
                print(f"\n✅ SUCCESS! Found cookie '{target_cookie}'")
                print(f"   Domain: {found_cookie.get('domain')}")
                print(f"   Path: {found_cookie.get('path')}")
                print(f"   HttpOnly: {found_cookie.get('httpOnly')}")
                print(f"   Secure: {found_cookie.get('secure')}")
                print(f"   Value length: {len(found_cookie['value'])} chars")
            else:
                print(f"\n⚠️  Cookie '{target_cookie}' not found.")
                print("   Make sure you are fully logged in inside the Edge window.")
                result["error"] = f"Cookie '{target_cookie}' not found"

            # Disconnect (don't close browser)
            browser.close()

    except Exception as e:
        error_msg = str(e)
        result["error"] = error_msg
        print(f"\n❌ Error connecting: {error_msg}")
        if "connection refused" in error_msg.lower():
            print("\n💡 Troubleshooting tips:")
            print("   1. Make sure Edge is running with --remote-debugging-port=9222")
            print("   2. Close all other Edge instances first")
            print("   3. Try restarting Edge with the debug command")

    return result


def save_auth_credentials(
    cookies: List[Dict],
    name: str,
    auth_dir: Path = AUTH_DIR,
    target_domain: Optional[str] = None,
) -> Path:
    """
    Save authentication credentials in the format expected by FireCrawl.

    Args:
        cookies: List of cookie dictionaries
        name: Profile name for these credentials
        auth_dir: Directory to store auth credentials
        target_domain: Optional domain to filter cookies

    Returns:
        Path to the saved credentials file
    """
    auth_dir.mkdir(exist_ok=True)

    # Filter cookies by domain if specified
    if target_domain:
        cookies = [c for c in cookies if target_domain in c.get("domain", "")]

    # Convert to FireCrawl format
    firecrawl_cookies = []
    for c in cookies:
        firecrawl_cookie = {
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain"),
            "path": c.get("path", "/"),
            "secure": c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
        }

        # Handle expiry
        if "expires" in c and c["expires"] > 0:
            firecrawl_cookie["expires"] = c["expires"]

        firecrawl_cookies.append(firecrawl_cookie)

    # Create storage_state structure
    storage_state = {
        "cookies": firecrawl_cookies,
        "origins": [],
    }

    # Create auth data structure
    auth_data = {
        "profile_name": name,
        "created_at": datetime.now().isoformat(),
        "cookies": firecrawl_cookies,
        "storage_state": storage_state,
    }

    # Save to file
    auth_file = auth_dir / f"{name}.json"
    with open(auth_file, "w", encoding="utf-8") as f:
        json.dump(auth_data, f, indent=2)

    print(f"\n💾 Saved {len(firecrawl_cookies)} cookies to {auth_file}")

    return auth_file, storage_state


# Domains to exclude from cookie storage (not needed for crawling)
EXCLUDED_DOMAINS = [
    "eng.ms",
    ".eng.ms",
]


def get_existing_storage_state(env_file: Path = ENV_FILE) -> Dict:
    """
    Get existing storage state from .env file.

    Args:
        env_file: Path to .env file

    Returns:
        Existing storage state dict or empty structure
    """
    if not env_file.exists():
        return {"cookies": [], "origins": []}

    with open(env_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Look for existing FIRECRAWL_AUTH_STORAGE_STATE (not commented)
    match = re.search(r"^FIRECRAWL_AUTH_STORAGE_STATE=(.+)$", content, re.MULTILINE)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return {"cookies": [], "origins": []}


def merge_storage_states(existing: Dict, new: Dict, new_domain: str) -> Dict:
    """
    Merge new cookies into existing storage state.

    - Keeps existing cookies from other domains
    - Replaces/adds cookies for the new domain
    - Filters out excluded domains

    Args:
        existing: Existing storage state
        new: New storage state with cookies to add
        new_domain: The domain being authenticated
            (used to replace old cookies for this domain)

    Returns:
        Merged storage state
    """
    existing_cookies = existing.get("cookies", [])
    new_cookies = new.get("cookies", [])

    # Filter out excluded domains from existing cookies
    filtered_existing = [
        c
        for c in existing_cookies
        if not any(excluded in c.get("domain", "") for excluded in EXCLUDED_DOMAINS)
    ]

    # Filter out cookies from the new domain (will be replaced with new ones)
    # Also filter out excluded domains
    kept_cookies = [
        c for c in filtered_existing if new_domain not in c.get("domain", "")
    ]

    # Filter new cookies to exclude unwanted domains
    filtered_new = [
        c
        for c in new_cookies
        if not any(excluded in c.get("domain", "") for excluded in EXCLUDED_DOMAINS)
    ]

    # Merge: existing (minus new domain) + new cookies
    merged_cookies = kept_cookies + filtered_new

    print("\n📊 Cookie merge summary:")
    print(f"   Existing cookies (other domains): {len(kept_cookies)}")
    print(f"   New cookies for {new_domain}: {len(filtered_new)}")
    print(f"   Total after merge: {len(merged_cookies)}")

    # Show domains
    domains = set(c.get("domain", "unknown") for c in merged_cookies)
    print(f"   Domains: {', '.join(sorted(domains))}")

    return {
        "cookies": merged_cookies,
        "origins": existing.get("origins", []) + new.get("origins", []),
    }


def apply_to_env(
    storage_state: Dict,
    env_file: Path = ENV_FILE,
    target_domain: Optional[str] = None,
) -> bool:
    """
    Apply storage_state to .env file, merging with existing cookies.

    Args:
        storage_state: The storage state dict with cookies
        env_file: Path to .env file
        target_domain: The domain being authenticated (for merge logic)

    Returns:
        True if successful
    """
    print(f"\n📝 Applying credentials to {env_file}...")

    if not env_file.exists():
        print(f"❌ .env file not found: {env_file}")
        return False

    # Get existing storage state and merge
    if target_domain:
        existing_state = get_existing_storage_state(env_file)
        merged_state = merge_storage_states(
            existing_state, storage_state, target_domain
        )
    else:
        merged_state = storage_state

    # Read current .env content
    with open(env_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Create compact JSON for storage state
    storage_state_json = json.dumps(merged_state, separators=(",", ":"))

    # Check if FIRECRAWL_AUTH_STORAGE_STATE exists (including commented)
    if re.search(r"^#?\s*FIRECRAWL_AUTH_STORAGE_STATE=", content, re.MULTILINE):
        # Replace existing line (commented or not)
        pattern = r"^#?\s*FIRECRAWL_AUTH_STORAGE_STATE=.*$"
        replacement = f"FIRECRAWL_AUTH_STORAGE_STATE={storage_state_json}"
        content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    else:
        # Add new lines
        auth_section = f"""
# Auth settings (captured at {datetime.now().isoformat()})
FIRECRAWL_AUTH_TYPE=cookies
FIRECRAWL_AUTH_STORAGE_STATE={storage_state_json}
"""
        content = content.rstrip() + "\n" + auth_section

    # Ensure FIRECRAWL_AUTH_TYPE=cookies is set
    if (
        "FIRECRAWL_AUTH_TYPE=" not in content
        or "FIRECRAWL_AUTH_TYPE=cookies" not in content
    ):
        # Update or add auth type
        if "FIRECRAWL_AUTH_TYPE=" in content:
            content = re.sub(
                r"^FIRECRAWL_AUTH_TYPE=.*$",
                "FIRECRAWL_AUTH_TYPE=cookies",
                content,
                flags=re.MULTILINE,
            )

    # Write back
    with open(env_file, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ Updated {env_file} with new credentials")
    return True


def recreate_crawler(deploy_dir: Path = DEPLOY_DIR) -> bool:
    """
    Force recreate the crawler container to reload .env.

    Args:
        deploy_dir: Path to deploy directory

    Returns:
        True if successful
    """
    print("\n🔄 Recreating crawler container to load new credentials...")

    if not deploy_dir.exists():
        print(f"❌ Deploy directory not found: {deploy_dir}")
        return False

    try:
        # Run docker-compose to recreate crawler
        result = subprocess.run(
            [
                "docker-compose",
                "-f",
                "docker-compose.yml",
                "up",
                "-d",
                "--force-recreate",
                "crawler",
            ],
            cwd=str(deploy_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            print("✅ Crawler container recreated successfully")
            # Wait for crawler to start
            print("⏳ Waiting for crawler to initialize...")
            time.sleep(5)
            return True
        else:
            print(f"❌ Failed to recreate crawler: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("❌ Timeout waiting for container recreation")
        return False
    except FileNotFoundError:
        print("❌ docker-compose not found. Please install Docker.")
        return False
    except Exception as e:
        print(f"❌ Error recreating crawler: {e}")
        return False


def test_authentication(url: str) -> bool:
    """
    Test if authentication works by crawling a page.

    Args:
        url: URL to test

    Returns:
        True if authentication works
    """
    print(f"\n🧪 Testing authentication with: {url}")

    try:
        import requests
    except ImportError:
        print("⚠️  Skipping authentication test - 'requests' module not installed")
        print("   Install with: pip install requests")
        return False

    try:
        # Call the crawler API
        response = requests.post(
            "http://localhost:8001/crawl",
            json={
                "query": "test",
                "seed_urls": [url],
                "max_results": 1,
            },
            timeout=60,
        )

        if response.status_code == 200:
            data = response.json()
            docs = data.get("docs", [])

            if docs:
                doc = docs[0]
                title = doc.get("title", "No title")
                content_length = len(doc.get("markdown", ""))
                source = doc.get("source", "unknown")

                print("\n✅ Authentication working!")
                print(f"   Title: {title}")
                print(f"   Content length: {content_length} chars")
                print(f"   Source: {source}")
                return True
            else:
                print("⚠️  Request succeeded but no content returned")
                return False
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False

    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to crawler. Is it running?")
        print("   Try: cd deploy && docker-compose up -d crawler")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def authenticate(
    url: str,
    name: Optional[str] = None,
    target_cookie: str = "AppServiceAuthSession",
    debug_port: int = 9222,
    user_data_dir: Optional[str] = None,
    auto_apply: bool = True,
    auto_restart: bool = True,
    auto_test: bool = True,
    deploy_dir: Optional[Path] = None,
    env_file: Optional[Path] = None,
) -> Dict:
    """
    Complete authentication workflow.

    Args:
        url: URL to authenticate to
        name: Profile name (default: derived from URL domain)
        target_cookie: Name of the authentication cookie to find
        debug_port: Port for Edge remote debugging
        user_data_dir: Directory for Edge temp profile
        auto_apply: Automatically apply to .env
        auto_restart: Automatically restart crawler
        auto_test: Automatically test authentication
        deploy_dir: Path to deployment directory (default: ./deploy)
        env_file: Path to .env file (default: deploy/.env)

    Returns:
        Dict with authentication result
    """
    # Use defaults if not provided
    if deploy_dir is None:
        deploy_dir = DEPLOY_DIR
    if env_file is None:
        env_file = ENV_FILE

    if not name:
        parsed = urlparse(url)
        name = parsed.netloc.replace(".", "_")

    target_domain = urlparse(url).netloc

    print("\n" + "=" * 70)
    print("🔐 AUTHENTICATION TOOL FOR INTERNAL SITES")
    print("=" * 70)
    print(f"\n📍 Target URL: {url}")
    print(f"📝 Profile name: {name}")
    print(f"🎯 Looking for cookie: {target_cookie}")

    # Step 1: Launch Edge
    print("\n" + "-" * 70)
    print("STEP 1/5: Launch Edge with debugging")
    print("-" * 70)

    try:
        launch_edge_with_debugging(  # noqa: F841 - process runs in background
            debug_port=debug_port,
            user_data_dir=user_data_dir,
            initial_url=url,
        )
        print("✅ Edge launched successfully")
    except Exception as e:
        print(f"❌ Failed to launch Edge: {e}")
        return {"success": False, "error": str(e)}

    # Step 2: Wait for user authentication
    print("\n" + "-" * 70)
    print("STEP 2/5: Complete authentication in browser")
    print("-" * 70)
    print("\n📋 INSTRUCTIONS:")
    print("   1. An Edge window should now be open")
    print("   2. If prompted, sign in with your Microsoft credentials")
    print("   3. Complete MFA/2FA if prompted")
    print("   4. WAIT until you see the authenticated page content")
    print("   5. Verify you can see the actual wiki/site content (not a login page)")
    print()
    print("⏸️  Press ENTER when you can see the authenticated content...")

    try:
        input()
    except KeyboardInterrupt:
        print("\n✋ Cancelled by user")
        return {"success": False, "error": "Cancelled by user"}

    # Step 3: Extract cookies
    print("\n" + "-" * 70)
    print("STEP 3/5: Extract cookies from browser")
    print("-" * 70)

    result = get_cookies_from_debug_browser(
        debug_port=debug_port,
        target_cookie=target_cookie,
        target_domain=target_domain,
    )

    if not result["success"]:
        print("\n" + "=" * 70)
        print("❌ AUTHENTICATION FAILED")
        print("=" * 70)
        print(f"\nError: {result.get('error', 'Unknown error')}")
        print("\n💡 Troubleshooting:")
        print("   - Make sure you completed the full login process")
        print("   - Check that you can see the protected content in Edge")
        print("   - Try running the script again")
        return result

    # Save credentials
    cookies_to_save = (
        result["domain_cookies"] if result["domain_cookies"] else result["all_cookies"]
    )
    auth_file, storage_state = save_auth_credentials(
        cookies=cookies_to_save,
        name=name,
        auth_dir=AUTH_DIR,
        target_domain=target_domain,
    )
    result["auth_file"] = str(auth_file)
    result["storage_state"] = storage_state

    # Step 4: Apply to .env
    if auto_apply:
        print("\n" + "-" * 70)
        print("STEP 4/5: Apply credentials to .env")
        print("-" * 70)
        apply_to_env(storage_state, env_file, target_domain=target_domain)
    else:
        print("\n" + "-" * 70)
        print("STEP 4/5: Skip applying to .env (--no-apply)")
        print("-" * 70)

    # Step 5: Restart crawler
    if auto_restart:
        print("\n" + "-" * 70)
        print("STEP 5/5: Restart crawler to load new credentials")
        print("-" * 70)
        recreate_crawler(deploy_dir)
    else:
        print("\n" + "-" * 70)
        print("STEP 5/5: Skip restarting crawler (--no-restart)")
        print("-" * 70)

    # Test authentication
    if auto_test and auto_restart:
        print("\n" + "-" * 70)
        print("BONUS: Test authentication")
        print("-" * 70)
        test_authentication(url)

    print("\n" + "=" * 70)
    print("✅ AUTHENTICATION COMPLETE!")
    print("=" * 70)
    print(f"\n📁 Credentials saved to: {auth_file}")
    print(f"📝 Applied to: {env_file}")
    print("\n💡 You can now close the Edge window manually.")
    print("\n🔄 To re-authenticate later, run:")
    print(f"   python tools/msauth/authenticate.py {url}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Authenticate to internal sites using Edge remote debugging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full automated workflow (recommended)
  python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page

  # Custom profile name
  python tools/msauth/authenticate.py https://www.osgwiki.com --name my_wiki

  # Skip auto-apply to .env
  python tools/msauth/authenticate.py https://www.osgwiki.com --no-apply

  # Skip container restart
  python tools/msauth/authenticate.py https://www.osgwiki.com --no-restart

  # Skip authentication test
  python tools/msauth/authenticate.py https://www.osgwiki.com --no-test

The tool will:
  1. Launch Edge with remote debugging enabled
  2. Wait for you to sign in
  3. Extract authentication cookies
  4. Save to .auth/ directory
  5. Apply to deploy/.env file
  6. Recreate crawler container
  7. Test authentication
        """,
    )

    parser.add_argument(
        "url",
        help="URL to authenticate to",
    )
    parser.add_argument(
        "--name",
        "-n",
        help="Profile name for saved credentials (default: derived from domain)",
    )
    parser.add_argument(
        "--cookie",
        "-c",
        default="AppServiceAuthSession",
        help="Target cookie name to find (default: AppServiceAuthSession)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=9222,
        help="Remote debugging port (default: 9222)",
    )
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="User data directory for Edge profile",
    )
    parser.add_argument(
        "--no-apply",
        action="store_true",
        help="Don't apply credentials to .env file",
    )
    parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Don't restart crawler container",
    )
    parser.add_argument(
        "--no-test",
        action="store_true",
        help="Don't test authentication after setup",
    )
    parser.add_argument(
        "--dir",
        "-d",
        default=None,
        help="Deployment directory containing .env",
    )

    args = parser.parse_args()

    # Determine deploy directory
    deploy_dir = None
    env_file = None
    if args.dir:
        deploy_dir = Path(args.dir)
        env_file = deploy_dir / ".env"
    else:
        # Try common locations
        for candidate in [
            Path.cwd() / "deploy",
            Path.cwd() / "llmcrawl-deploy",
            PROJECT_ROOT / "deploy",
        ]:
            if (candidate / ".env").exists():
                deploy_dir = candidate
                env_file = candidate / ".env"
                break
        if deploy_dir is None:
            deploy_dir = DEPLOY_DIR
            env_file = ENV_FILE

    result = authenticate(
        url=args.url,
        name=args.name,
        target_cookie=args.cookie,
        debug_port=args.port,
        user_data_dir=args.user_data_dir,
        auto_apply=not args.no_apply,
        auto_restart=not args.no_restart,
        auto_test=not args.no_test,
        deploy_dir=deploy_dir,
        env_file=env_file,
    )

    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()

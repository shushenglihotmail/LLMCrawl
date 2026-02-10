#!/usr/bin/env python3
"""
Claude Code Authentication Diagnostics

This script tests Claude Code OAuth configuration and helps diagnose issues.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import logging

from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_status(success, message):
    """Print a status message."""
    icon = "✓" if success else "✗"
    status = "SUCCESS" if success else "FAILED"
    print(f"{icon} [{status:7}] {message}")


def test_1_environment_variables():
    """Test 1: Check Claude OAuth environment variables."""
    print_header("TEST 1: Claude OAuth Configuration")

    # Load .env file
    script_dir = Path(__file__).parent
    env_file = script_dir / ".env"

    if env_file.exists():
        print(f"ℹ️  Loading {env_file}")
        load_dotenv(env_file)
    else:
        print(f"⚠️  No .env file found at {env_file}")

    # Check Claude-specific variables
    claude_vars = {
        "CLAUDE_CLIENT_ID": "Claude OAuth Client ID",
        "CLAUDE_REDIRECT_PORT": "Redirect port for OAuth",
        "CLAUDE_SCOPES": "OAuth scopes",
    }

    results = {}
    all_configured = True

    for var, description in claude_vars.items():
        value = os.getenv(var)
        if value:
            if var == "CLAUDE_CLIENT_ID":
                masked = value[:8] + "..." if len(value) > 8 else value
                print_status(True, f"{var}: {masked}")
            else:
                print_status(True, f"{var}: {value}")
            print(f"           {description}")
            results[var] = value
        else:
            # Use defaults
            if var == "CLAUDE_CLIENT_ID":
                default = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
                print_status(True, f"{var}: {default[:8]}... (default)")
                print(f"           Using official Claude CLI client ID")
                results[var] = default
            elif var == "CLAUDE_REDIRECT_PORT":
                default = "54545"
                print_status(True, f"{var}: {default} (default)")
                results[var] = default
            elif var == "CLAUDE_SCOPES":
                default = "org:create_api_key user:profile user:inference"
                print_status(True, f"{var}: {default} (default)")
                results[var] = default

    return True, results


def test_2_oauth_configuration(env_vars):
    """Test 2: Analyze OAuth configuration."""
    print_header("TEST 2: OAuth Configuration Analysis")

    client_id = env_vars.get("CLAUDE_CLIENT_ID")
    redirect_port = env_vars.get("CLAUDE_REDIRECT_PORT", "54545")

    print("📋 Current Configuration:")
    print(f"   Client ID: {client_id[:8]}...")
    print(f"   Redirect URI: http://localhost:{redirect_port}/callback")
    print(f"   Auth Endpoint: https://console.anthropic.com/oauth/authorize")
    print(f"   Token Endpoint: https://console.anthropic.com/oauth/token")
    print()

    # Check if using official CLI client ID
    official_cli_id = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
    if client_id == official_cli_id:
        print("✓ Using official Claude CLI client ID")
        print("  This should work for standard Claude Code access")
    else:
        print("⚠️  Using custom client ID")
        print("  Make sure this is registered with Anthropic")

    print()
    return True


def test_3_company_sso_check():
    """Test 3: Check for company SSO requirements."""
    print_header("TEST 3: Company SSO Configuration")

    print("⚠️  Important: Company SSO Requirements")
    print()
    print("Your organization uses Claude Code with company SSO/Entra ID.")
    print("This may require:")
    print()
    print("1. Your company may have registered a custom OAuth app with Anthropic")
    print("   - If so, you need the correct CLAUDE_CLIENT_ID")
    print("   - Contact your IT/security team for the Client ID")
    print()
    print("2. The official Claude CLI client ID may not work with your company SSO")
    print("   - Company SSO often requires organization-specific configuration")
    print()
    print("3. Your company may need to approve the OAuth redirect URI")
    print("   - Redirect URI: http://localhost:54545/callback")
    print()

    return True


def test_4_claude_auth_client():
    """Test 4: Try to create Claude auth client."""
    print_header("TEST 4: Claude Auth Client Creation")

    try:
        from claude_auth import ClaudeAuthClient, create_claude_auth_client_from_env

        print("ℹ️  Creating Claude auth client...")
        client = create_claude_auth_client_from_env()

        print_status(True, "Claude auth client created successfully")
        return True, client

    except Exception as e:
        print_status(False, f"Failed to create Claude auth client")
        print(f"\n⚠️  ERROR: {e}")
        return False, None


def test_5_cached_token(client):
    """Test 5: Check for cached Claude token."""
    print_header("TEST 5: Cached Claude Token")

    if not client:
        print_status(False, "Skipped (no client)")
        return False

    try:
        token = client.get_cached_token()

        if token:
            print_status(True, f"Found cached token (length: {len(token)})")
            return True
        else:
            print_status(False, "No cached token found")
            print("   ℹ️  This is normal on first run - you need to sign in")
            return False

    except Exception as e:
        print_status(False, f"Error checking cache")
        print(f"   ⚠️  {e}")
        return False


def test_6_interactive_auth(client, force=False):
    """Test 6: Try interactive Claude authentication."""
    print_header("TEST 6: Claude Interactive Authentication")

    if not client:
        print_status(False, "Skipped (no client)")
        return False

    if not force:
        print("ℹ️  This test will open a browser to console.anthropic.com")
        print("   You'll sign in with your company SSO")
        print()
        print("   Press Enter to continue, or Ctrl+C to skip...")
        try:
            input()
        except KeyboardInterrupt:
            print("\n⚠️  Skipped by user")
            return False

    try:
        print("\n🌐 Opening browser for Claude Code authentication...")
        print("   - Complete sign-in in the browser window")
        print("   - Look for 'Invalid OAuth Request' or 'Missing state parameter'")
        print("   - Press Ctrl+C here to cancel if needed")
        print()

        token = client.get_token(force_interactive=True)

        if token:
            print_status(True, "Claude authentication successful!")
            print(f"   Token length: {len(token)}")
            return True
        else:
            print_status(False, "Authentication failed (no token)")
            return False

    except KeyboardInterrupt:
        print("\n⚠️  Authentication cancelled by user")
        return False
    except Exception as e:
        print_status(False, "Claude authentication failed")
        print(f"\n⚠️  ERROR: {e}")
        print()

        error_str = str(e).lower()

        # Diagnose the error
        if "state" in error_str or "invalid" in error_str:
            print("💡 DIAGNOSIS: OAuth Configuration Issue")
            print()
            print("   The 'Missing state parameter' error for Claude Code means:")
            print()
            print("   ❌ Option 1: Using wrong Client ID")
            print(
                "      - The official Claude CLI client ID may not work with your company"
            )
            print("      - Your company may have registered a custom OAuth app")
            print("      - Ask your IT team for the correct CLAUDE_CLIENT_ID")
            print()
            print("   ❌ Option 2: Company hasn't configured OAuth redirect")
            print(
                "      - Your company's Claude OAuth app may not allow localhost redirects"
            )
            print("      - Ask IT to add: http://localhost:54545/callback")
            print()
            print("   ❌ Option 3: Wrong OAuth endpoints")
            print(
                "      - Your company may use custom OAuth endpoints (not console.anthropic.com)"
            )
            print("      - Ask IT for the correct authorization and token URLs")
            print()
        elif "redirect" in error_str or "callback" in error_str:
            print("💡 DIAGNOSIS: Redirect URI Issue")
            print()
            print("   The redirect URI is not approved for this OAuth app.")
            print("   Ask your IT team to add: http://localhost:54545/callback")
            print()
        else:
            print("💡 Next Steps:")
            print()
            print("   1. Contact your IT/Security team")
            print("   2. Ask for Claude Code OAuth configuration details:")
            print("      - OAuth Client ID for Claude Code")
            print("      - Approved redirect URIs")
            print("      - Authorization endpoint (if custom)")
            print("      - Token endpoint (if custom)")
            print()

        return False


def main():
    """Run all diagnostic tests."""
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 12 + "Claude Code Authentication Diagnostics" + " " * 17 + "║")
    print("╚" + "═" * 68 + "╝")

    # Test 1: Environment Variables
    success1, env_vars = test_1_environment_variables()

    # Test 2: OAuth Config
    test_2_oauth_configuration(env_vars)

    # Test 3: Company SSO
    test_3_company_sso_check()

    # Test 4: Auth Client
    success4, client = test_4_claude_auth_client()
    if not success4:
        print("\n❌ Cannot proceed without auth client")
        return 1

    # Test 5: Cached Token
    success5 = test_5_cached_token(client)

    # Summary
    print_header("SUMMARY")

    if success5:
        print("✓ Claude authentication is working!")
        print("  You can use Claude models in HiChat.")
    else:
        print("⚠️  Claude authentication not configured yet.")
        print()
        print("   Next steps:")
        print("   1. Run this script with --auth to test authentication")
        print("   2. If you see 'Missing state parameter' error:")
        print("      - Contact your IT team for company-specific Claude OAuth settings")
        print("      - Ask for the correct CLAUDE_CLIENT_ID for your organization")
        print()
        print("   Command: python test_claude_auth.py --auth")

    print()

    # Optional: Interactive auth
    if "--auth" in sys.argv or "--login" in sys.argv or "-a" in sys.argv:
        test_6_interactive_auth(client, force=True)

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

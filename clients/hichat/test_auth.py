#!/usr/bin/env python3
"""
HiChat Authentication Diagnostics

This script tests Azure AD authentication configuration and helps diagnose issues.
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
    """Test 1: Check if environment variables are set."""
    print_header("TEST 1: Environment Variables")

    # Load .env file
    script_dir = Path(__file__).parent
    env_file = script_dir / ".env"

    if env_file.exists():
        print(f"ℹ️  Loading {env_file}")
        load_dotenv(env_file)
    else:
        print(f"⚠️  No .env file found at {env_file}")
        print(f"ℹ️  Checking system environment variables...")

    # Check required variables
    required_vars = {
        "ENTRA_CLIENT_ID": "Azure AD Application (Client) ID",
        "ENTRA_TENANT_ID": "Azure AD Tenant ID",
        "AZURE_FOUNDRY_SCOPE": "Azure Foundry API Scope",
    }

    all_found = True
    results = {}

    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            # Mask the value for security (show first 8 chars only)
            masked = value[:8] + "..." if len(value) > 8 else value
            print_status(True, f"{var}: {masked}")
            print(f"           {description}")
            results[var] = value
        else:
            print_status(False, f"{var}: NOT SET")
            print(f"           {description}")
            all_found = False

    if not all_found:
        print("\n⚠️  CONFIGURATION ERROR")
        print("   Please create clients/hichat/.env with required variables:")
        print()
        print("   ENTRA_CLIENT_ID=<your-app-client-id>")
        print("   ENTRA_TENANT_ID=<your-tenant-id>")
        print("   AZURE_FOUNDRY_SCOPE=https://cognitiveservices.azure.com/.default")
        print()
        return False, results

    return True, results


def test_2_msal_import():
    """Test 2: Check if MSAL library is installed."""
    print_header("TEST 2: MSAL Library")

    try:
        import msal

        print_status(True, f"MSAL version: {msal.__version__}")
        return True
    except ImportError as e:
        print_status(False, "MSAL not installed")
        print(f"\n⚠️  DEPENDENCY ERROR")
        print(f"   {e}")
        print(f"   Install with: pip install msal")
        return False


def test_3_auth_client_creation(env_vars):
    """Test 3: Try to create MSAL auth client."""
    print_header("TEST 3: Auth Client Creation")

    try:
        from msal_auth import MSALAuthClient

        client_id = env_vars.get("ENTRA_CLIENT_ID")
        tenant_id = env_vars.get("ENTRA_TENANT_ID", "common")
        scope = env_vars.get("AZURE_FOUNDRY_SCOPE")

        authority = f"https://login.microsoftonline.com/{tenant_id}"
        scopes = [scope]

        print(f"ℹ️  Creating client with:")
        print(f"   Client ID: {client_id[:8]}...")
        print(f"   Authority: {authority}")
        print(f"   Scopes: {scopes}")

        client = MSALAuthClient(
            client_id=client_id,
            authority=authority,
            scopes=scopes,
        )

        print_status(True, "Auth client created successfully")
        return True, client

    except Exception as e:
        print_status(False, f"Failed to create auth client")
        print(f"\n⚠️  ERROR: {e}")
        return False, None


def test_4_cached_token(client):
    """Test 4: Check for cached authentication token."""
    print_header("TEST 4: Cached Token")

    if not client:
        print_status(False, "Skipped (no client)")
        return False

    try:
        result = client.acquire_token_silent()

        if result and "access_token" in result:
            token = result["access_token"]
            print_status(True, f"Found cached token (length: {len(token)})")

            # Try to get account info
            account = client.get_account_info()
            if account:
                print(f"   Username: {account.get('username', 'N/A')}")
                print(f"   Name: {account.get('name', 'N/A')}")

            return True
        else:
            print_status(False, "No cached token found")
            print("   ℹ️  This is normal on first run - you need to sign in")
            return False

    except Exception as e:
        print_status(False, f"Error checking cache")
        print(f"   ⚠️  {e}")
        return False


def test_5_azure_ad_config(env_vars):
    """Test 5: Check Azure AD configuration (informational)."""
    print_header("TEST 5: Azure AD Configuration Check")

    client_id = env_vars.get("ENTRA_CLIENT_ID")
    tenant_id = env_vars.get("ENTRA_TENANT_ID", "common")

    print("ℹ️  Azure Portal Configuration Checklist:")
    print()
    print(f"   1. Go to: https://portal.azure.com")
    print(f"   2. Navigate to: Azure Active Directory > App registrations")
    print(f"   3. Find app with Client ID: {client_id[:8]}...")
    print()
    print("   4. In 'Authentication' section, verify:")
    print("      ☐ Platform: Mobile and desktop applications")
    print("      ☐ Redirect URI: http://localhost:8765")
    print("      ☐ Allow public client flows: Yes")
    print()
    print("   5. In 'API permissions' section, verify:")
    print("      ☐ Azure Foundry scope is added")
    print("      ☐ Admin consent granted (if required)")
    print()
    print("⚠️  If any of the above are not configured, authentication will fail!")
    print()


def test_6_interactive_auth(client, force=False):
    """Test 6: Try interactive authentication (optional)."""
    print_header("TEST 6: Interactive Authentication")

    if not client:
        print_status(False, "Skipped (no client)")
        return False

    if not force:
        print("ℹ️  This test will open a browser for sign-in.")
        print("   Press Enter to continue, or Ctrl+C to skip...")
        try:
            input()
        except KeyboardInterrupt:
            print("\n⚠️  Skipped by user")
            return False

    try:
        print("\n🌐 Opening browser for authentication...")
        print("   - Complete sign-in in the browser window")
        print("   - You may see 'Missing state parameter' if config is wrong")
        print("   - Press Ctrl+C here to cancel if it hangs")
        print()

        token = client.get_token(force_interactive=True, allow_device_code=False)

        if token:
            print_status(True, "Authentication successful!")
            print(f"   Token length: {len(token)}")

            # Get account info
            account = client.get_account_info()
            if account:
                print(f"   Signed in as: {account.get('username', 'N/A')}")

            return True
        else:
            print_status(False, "Authentication failed (no token)")
            return False

    except KeyboardInterrupt:
        print("\n⚠️  Authentication cancelled by user")
        return False
    except Exception as e:
        print_status(False, "Authentication failed")
        print(f"\n⚠️  ERROR: {e}")
        print()

        error_str = str(e).lower()

        # Provide specific guidance based on error
        if "state" in error_str or "invalid" in error_str:
            print("💡 DIAGNOSIS: Azure AD App Configuration Issue")
            print()
            print("   Your Azure AD app registration needs proper configuration.")
            print("   The 'Missing state parameter' error means:")
            print()
            print("   ✗ App is not configured as 'Public client'")
            print("   ✗ Redirect URI 'http://localhost:8765' is missing")
            print("   ✗ 'Allow public client flows' is disabled")
            print()
            print("   See TEST 5 output above for configuration steps.")
            print()
        elif "consent" in error_str or "aadsts65001" in error_str:
            print("💡 DIAGNOSIS: Admin Consent Required")
            print()
            print("   The application needs admin consent to access Azure resources.")
            print("   Ask your Azure administrator to grant consent.")
            print()
        elif "timeout" in error_str or "connection" in error_str:
            print("💡 DIAGNOSIS: Network or Firewall Issue")
            print()
            print("   Cannot connect to Azure AD authentication service.")
            print("   Check your network connection and firewall settings.")
            print()
        else:
            print("💡 See docs/TROUBLESHOOTING_AUTH.md for more help")
            print()

        return False


def main():
    """Run all diagnostic tests."""
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "HiChat Authentication Diagnostics" + " " * 20 + "║")
    print("╚" + "═" * 68 + "╝")

    # Test 1: Environment Variables
    success1, env_vars = test_1_environment_variables()
    if not success1:
        print("\n❌ Cannot proceed without required environment variables")
        print("   Please configure .env file and try again.")
        return 1

    # Test 2: MSAL Import
    success2 = test_2_msal_import()
    if not success2:
        print("\n❌ Cannot proceed without MSAL library")
        print("   Install with: pip install msal")
        return 1

    # Test 3: Auth Client Creation
    success3, client = test_3_auth_client_creation(env_vars)
    if not success3:
        print("\n❌ Failed to create authentication client")
        return 1

    # Test 4: Cached Token
    success4 = test_4_cached_token(client)

    # Test 5: Azure AD Config (informational)
    test_5_azure_ad_config(env_vars)

    # Summary
    print_header("SUMMARY")

    if success4:
        print("✓ Authentication is configured and working!")
        print("  You can now run HiChat without issues.")
        print()
        print("  Start HiChat with: python main.py")
    else:
        print("⚠️  No cached token found. You need to sign in.")
        print()
        print("   You can:")
        print("   1. Run this script with --auth flag to sign in now")
        print("   2. Or start HiChat and sign in when prompted")
        print()
        print("   Command: python test_auth.py --auth")

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

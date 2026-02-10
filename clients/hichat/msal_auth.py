"""
MSAL Authentication Module for HiChat Client

Handles Entra ID authentication using MSAL (Microsoft Authentication Library).
Supports:
- Interactive browser-based sign-in
- Silent token acquisition (token refresh)
- Device code flow (fallback)
- Token caching for persistent sessions
"""

import json
import logging
import os
import webbrowser
from pathlib import Path
from typing import Optional

import msal

logger = logging.getLogger("hichat.auth")

# Default MSAL configuration
DEFAULT_AUTHORITY = "https://login.microsoftonline.com/common"
DEFAULT_SCOPES = []  # Will be configured based on Azure Foundry resource


class MSALAuthClient:
    """MSAL authentication client for Entra ID."""

    def __init__(
        self,
        client_id: str,
        authority: Optional[str] = None,
        scopes: Optional[list[str]] = None,
        cache_file: Optional[Path] = None,
    ):
        """
        Initialize MSAL authentication client.

        Args:
            client_id: Application (client) ID from Azure AD app registration
            authority: Authority URL (defaults to common tenant)
            scopes: List of scopes to request (e.g., ['<resource>/.default'])
            cache_file: Path to token cache file (defaults to ~/.llmcrawl/token_cache.bin)
        """
        self.client_id = client_id
        self.authority = authority or DEFAULT_AUTHORITY
        self.scopes = scopes or DEFAULT_SCOPES

        # Set up token cache
        if cache_file is None:
            cache_dir = Path.home() / ".llmcrawl"
            cache_dir.mkdir(exist_ok=True)
            cache_file = cache_dir / "token_cache.bin"

        self.cache_file = cache_file
        self.cache = self._load_cache()

        # Create MSAL public client application with explicit redirect URI
        self.app = msal.PublicClientApplication(
            client_id=self.client_id,
            authority=self.authority,
            token_cache=self.cache,
        )

        logger.info(f"Initialized MSAL auth client (client_id: {client_id})")

    def _load_cache(self) -> msal.SerializableTokenCache:
        """Load token cache from file."""
        cache = msal.SerializableTokenCache()

        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r") as f:
                    cache.deserialize(f.read())
                logger.info(f"Loaded token cache from {self.cache_file}")
            except Exception as e:
                logger.warning(f"Failed to load token cache: {e}")

        return cache

    def _save_cache(self):
        """Save token cache to file."""
        if self.cache.has_state_changed:
            try:
                with open(self.cache_file, "w") as f:
                    f.write(self.cache.serialize())
                logger.info(f"Saved token cache to {self.cache_file}")
            except Exception as e:
                logger.error(f"Failed to save token cache: {e}")

    def acquire_token_silent(self) -> Optional[dict]:
        """
        Attempt to acquire token silently from cache.

        Returns:
            Token result dict if successful, None otherwise
        """
        accounts = self.app.get_accounts()
        if not accounts:
            logger.info("No cached accounts found")
            return None

        # Try to acquire token silently for the first account
        account = accounts[0]
        logger.info(
            f"Attempting silent token acquisition for: {account.get('username')}"
        )

        try:
            result = self.app.acquire_token_silent(
                scopes=self.scopes,
                account=account,
            )

            if result and "access_token" in result:
                logger.info("Successfully acquired token silently")
                self._save_cache()
                return result
            elif result and "error" in result:
                logger.warning(
                    f"Silent token acquisition failed: {result.get('error_description')}"
                )
                return None
            else:
                logger.warning("Silent token acquisition returned unexpected result")
                return None

        except Exception as e:
            logger.error(f"Error during silent token acquisition: {e}")
            return None

    def acquire_token_interactive(self) -> dict:
        """
        Acquire token interactively using system browser.

        This will:
        1. Open the default system browser
        2. Navigate to Microsoft login page
        3. Handle MFA, Conditional Access, etc.
        4. Return token to application

        Returns:
            Token result dict with 'access_token' and other metadata

        Raises:
            Exception: If authentication fails
        """
        logger.info("Starting interactive authentication flow")
        logger.info(
            "A browser window will open for sign-in. Please complete authentication there."
        )

        try:
            # Use interactive flow with browser and explicit port
            result = self.app.acquire_token_interactive(
                scopes=self.scopes,
                prompt="select_account",  # Allow account selection
                port=8765,  # Use fixed port for redirect URI
                # login_hint can be used to pre-fill username if known
            )

            if result and "access_token" in result:
                logger.info(
                    f"Successfully authenticated: {result.get('id_token_claims', {}).get('preferred_username')}"
                )
                self._save_cache()
                return result
            elif result and "error" in result:
                error_msg = f"{result.get('error')}: {result.get('error_description')}"
                logger.error(f"Authentication failed: {error_msg}")
                raise Exception(error_msg)
            else:
                raise Exception("Authentication returned unexpected result")

        except Exception as e:
            logger.error(f"Interactive authentication error: {e}")
            raise

    def acquire_token_device_code(self) -> dict:
        """
        Acquire token using device code flow (fallback).

        This is useful when:
        - Browser pop-ups are blocked
        - Running in CLI/terminal environment
        - Interactive flow fails

        User will see a code and URL to sign in at https://microsoft.com/devicelogin

        Returns:
            Token result dict with 'access_token' and other metadata

        Raises:
            Exception: If authentication fails
        """
        logger.info("Starting device code authentication flow")

        try:
            flow = self.app.initiate_device_flow(scopes=self.scopes)

            if "user_code" not in flow:
                raise Exception(
                    f"Failed to initiate device flow: {flow.get('error_description')}"
                )

            # Display instructions to user
            print("\n" + "=" * 60)
            print("DEVICE CODE AUTHENTICATION")
            print("=" * 60)
            print(flow["message"])
            print("=" * 60 + "\n")

            # Wait for user to complete authentication
            result = self.app.acquire_token_by_device_flow(flow)

            if result and "access_token" in result:
                logger.info(f"Successfully authenticated via device code")
                self._save_cache()
                return result
            elif result and "error" in result:
                error_msg = f"{result.get('error')}: {result.get('error_description')}"
                logger.error(f"Device code authentication failed: {error_msg}")
                raise Exception(error_msg)
            else:
                raise Exception("Device code authentication returned unexpected result")

        except Exception as e:
            logger.error(f"Device code authentication error: {e}")
            raise

    def get_token(
        self, force_interactive: bool = False, allow_device_code: bool = False
    ) -> str:
        """
        Get access token, using silent acquisition if possible.

        This is the main method to use for getting tokens.
        It will:
        1. Try silent token acquisition from cache
        2. If that fails, prompt for interactive login
        3. Optionally fall back to device code flow if interactive fails

        Args:
            force_interactive: If True, skip silent acquisition and go straight to interactive
            allow_device_code: If True, fall back to device code flow if interactive fails

        Returns:
            Access token string

        Raises:
            Exception: If all authentication methods fail
        """
        # Try silent acquisition first (unless forced)
        if not force_interactive:
            result = self.acquire_token_silent()
            if result:
                return result["access_token"]

        # Try interactive flow
        try:
            result = self.acquire_token_interactive()
            return result["access_token"]
        except Exception as e:
            error_str = str(e).lower()

            # Check for admin consent errors
            if (
                "access_denied" in error_str
                or "consent" in error_str
                or "aadsts65001" in error_str
            ):
                logger.error("Authentication failed: Admin consent required")
                raise Exception(
                    "Admin consent required. The application needs administrator approval to access Azure Foundry resources. "
                    "Please contact your Azure administrator to grant consent for this application."
                )

            # Check if device code fallback is allowed
            if not allow_device_code:
                logger.error(f"Interactive authentication failed: {e}")
                raise Exception(f"Authentication failed: {e}")

            logger.warning(f"Interactive flow failed: {e}, trying device code flow")

        # Fallback to device code flow (only if allowed)
        if allow_device_code:
            try:
                result = self.acquire_token_device_code()
                return result["access_token"]
            except Exception as e:
                logger.error(f"All authentication methods failed: {e}")
                raise Exception(f"Authentication failed: {e}")

        raise Exception("Authentication failed")

    def get_account_info(self) -> Optional[dict]:
        """
        Get information about the currently signed-in account.

        Returns:
            Account info dict or None if not signed in
        """
        accounts = self.app.get_accounts()
        return accounts[0] if accounts else None

    def sign_out(self):
        """Sign out the current user and clear token cache."""
        accounts = self.app.get_accounts()

        for account in accounts:
            self.app.remove_account(account)
            logger.info(f"Signed out account: {account.get('username')}")

        # Clear cache file
        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
                logger.info(f"Removed token cache file: {self.cache_file}")
            except Exception as e:
                logger.error(f"Failed to remove cache file: {e}")


def create_auth_client_from_env() -> MSALAuthClient:
    """
    Create MSAL auth client from environment variables.

    Required environment variables:
        ENTRA_CLIENT_ID: Application (client) ID
        ENTRA_TENANT_ID: Directory (tenant) ID (optional, defaults to 'common')
        AZURE_FOUNDRY_SCOPE: Scope for Azure Foundry resource (e.g., 'https://ai.azure.com/.default')

    Returns:
        Configured MSALAuthClient instance

    Raises:
        ValueError: If required environment variables are missing
    """
    client_id = os.getenv("ENTRA_CLIENT_ID")
    if not client_id:
        raise ValueError("ENTRA_CLIENT_ID environment variable is required")

    tenant_id = os.getenv("ENTRA_TENANT_ID", "common")
    authority = f"https://login.microsoftonline.com/{tenant_id}"

    # Get scope for Azure Foundry
    scope = os.getenv("AZURE_FOUNDRY_SCOPE")
    if not scope:
        raise ValueError("AZURE_FOUNDRY_SCOPE environment variable is required")

    scopes = [scope]

    return MSALAuthClient(
        client_id=client_id,
        authority=authority,
        scopes=scopes,
    )


if __name__ == "__main__":
    """Test authentication flow."""
    logging.basicConfig(level=logging.INFO)

    try:
        # Create client from environment
        auth_client = create_auth_client_from_env()

        # Get token
        token = auth_client.get_token()
        print(f"\nSuccessfully obtained token (length: {len(token)})")
        print(f"Token preview: {token[:50]}...")

        # Show account info
        account = auth_client.get_account_info()
        if account:
            print(f"\nSigned in as: {account.get('username')}")

    except Exception as e:
        print(f"\nAuthentication failed: {e}")
        exit(1)

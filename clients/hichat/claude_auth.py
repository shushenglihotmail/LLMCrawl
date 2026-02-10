"""
Claude OAuth 2.0 PKCE Authentication Module

Handles OAuth 2.0 PKCE flow for Claude Code authentication with Entra ID SSO.
Based on the official Claude CLI client implementation.

Supports:
- Browser-based SSO sign-in via console.anthropic.com
- PKCE (Proof Key for Code Exchange) flow
- Token refresh for persistent sessions
- Token caching for reuse across sessions
"""

import base64
import hashlib
import json
import logging
import os
import secrets
import socket
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests


def find_available_port(start=50000, end=60000):
    """Find an available port in the given range."""
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No available port found in range {start}-{end}")


logger = logging.getLogger("hichat.claude_auth")

# Claude OAuth configuration (official Claude CLI parameters)
DEFAULT_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
# Port 49861 is whitelisted for the official Claude CLI client ID
DEFAULT_REDIRECT_PORT = 49861
# Scopes from official Claude Code CLI v2.1.2
DEFAULT_SCOPES = (
    "org:create_api_key user:profile user:inference user:sessions:claude_code"
)
# Claude OAuth endpoints (from official Claude Code CLI v2.1.2)
# Enterprise SSO uses platform.claude.com for authorization
AUTH_URL = "https://platform.claude.com/oauth/authorize"
# Token exchange endpoint (v1 path on console.anthropic.com)
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Temporary HTTP server to catch the OAuth redirect code."""

    def log_message(self, format, *args):
        """Suppress default HTTP server logging."""
        pass

    def do_GET(self):
        """Handle GET request from OAuth redirect."""
        logger.info(f"Callback received request: {self.path}")

        # Ignore requests that are not for the callback path (e.g. /favicon.ico)
        if not self.path.startswith("/callback"):
            logger.info("Ignoring non-callback request")
            self.send_response(404)
            self.end_headers()
            return

        query = urlparse(self.path).query
        params = parse_qs(query)

        if "code" in params:
            self.server.auth_code = params["code"][0]
            self.server.auth_state = params.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html = """
            <html>
            <head>
                <title>Claude Authentication - Success</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                        text-align: center;
                        max-width: 400px;
                    }
                    h1 {
                        color: #2d3748;
                        margin-bottom: 20px;
                    }
                    p {
                        color: #4a5568;
                        line-height: 1.6;
                    }
                    .checkmark {
                        font-size: 60px;
                        margin-bottom: 20px;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="checkmark">✅</div>
                    <h1>Login Successful!</h1>
                    <p>You have successfully authenticated with Claude Code.</p>
                    <p>You can now close this tab and return to HiChat.</p>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        else:
            error = params.get("error", ["Unknown error"])[0]
            error_desc = params.get("error_description", [""])[0]
            self.server.auth_error = f"{error}: {error_desc}" if error_desc else error
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html = f"""
            <html>
            <head>
                <title>Claude Authentication - Error</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                    }}
                    .container {{
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                        text-align: center;
                        max-width: 400px;
                    }}
                    h1 {{
                        color: #e53e3e;
                        margin-bottom: 20px;
                    }}
                    p {{
                        color: #4a5568;
                        line-height: 1.6;
                    }}
                    .error {{
                        font-size: 60px;
                        margin-bottom: 20px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="error">❌</div>
                    <h1>Authentication Failed</h1>
                    <p>{error}: {error_desc}</p>
                    <p>Please try again or contact your administrator.</p>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))


class ClaudeAuthClient:
    """OAuth 2.0 PKCE authentication client for Claude Code."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        redirect_port: Optional[int] = None,
        scopes: Optional[str] = None,
        cache_file: Optional[Path] = None,
    ):
        """
        Initialize Claude OAuth client.

        Args:
            client_id: OAuth client ID (defaults to official Claude CLI client ID)
            redirect_port: Local port for OAuth redirect (default: 54545)
            scopes: OAuth scopes (default: org:create_api_key user:profile user:inference)
            cache_file: Path to token cache file (defaults to ~/.llmcrawl/claude_tokens.json)
        """
        self.client_id = client_id or DEFAULT_CLIENT_ID
        self.redirect_port = redirect_port or DEFAULT_REDIRECT_PORT
        # Use localhost callback (must match what's whitelisted for this client_id)
        self.redirect_uri = f"http://localhost:{self.redirect_port}/callback"
        self.scopes = scopes or DEFAULT_SCOPES

        # Set up token cache
        if cache_file is None:
            cache_dir = Path.home() / ".llmcrawl"
            cache_dir.mkdir(exist_ok=True)
            cache_file = cache_dir / "claude_tokens.json"

        self.cache_file = cache_file
        self._cached_tokens = self._load_tokens()

        logger.info(
            f"Initialized Claude OAuth client (client_id: {self.client_id[:8]}...)"
        )

    def _load_tokens(self) -> Optional[dict]:
        """Load tokens from cache file."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r") as f:
                    tokens = json.load(f)
                logger.info(f"Loaded Claude tokens from {self.cache_file}")
                return tokens
            except Exception as e:
                logger.warning(f"Failed to load Claude token cache: {e}")
        return None

    def _save_tokens(self, tokens: dict):
        """Save tokens to cache file."""
        try:
            with open(self.cache_file, "w") as f:
                json.dump(tokens, f, indent=2)
            logger.info(f"Saved Claude tokens to {self.cache_file}")
            self._cached_tokens = tokens
        except Exception as e:
            logger.error(f"Failed to save Claude token cache: {e}")

    def get_cached_token(self) -> Optional[str]:
        """
        Get cached access token if available.

        Returns:
            Access token string or None if not cached/expired
        """
        if self._cached_tokens:
            return self._cached_tokens.get("access_token")
        return None

    def acquire_token_with_browser(self) -> dict:
        """
        Acquire tokens via browser-based OAuth flow (PKCE).

        Opens system browser for SSO sign-in at console.anthropic.com,
        then catches redirect on local server and exchanges auth code for tokens.

        Returns:
            Token dict with access_token, refresh_token, etc.

        Raises:
            Exception if authentication fails
        """
        logger.info("Starting Claude OAuth browser flow...")

        # Find an available port dynamically (like official Claude Code CLI)
        port = find_available_port()
        redirect_uri = f"http://localhost:{port}/callback"
        logger.info(f"Using dynamic port {port} for OAuth callback")

        # Generate PKCE challenge
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode("utf-8")).digest()
            )
            .decode("utf-8")
            .rstrip("=")
        )

        # Generate random state parameter (must match official CLI length ~43 chars)
        state = secrets.token_urlsafe(32)

        # Build authorization URL (matching official Claude Code CLI v2.1.2)
        params = {
            "code": "true",  # Required by Claude OAuth
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": self.scopes,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
        }

        auth_request_url = (
            requests.Request("GET", AUTH_URL, params=params).prepare().url
        )

        # Start local server to catch redirect
        server = HTTPServer(("localhost", port), OAuthCallbackHandler)
        server.auth_code = None
        server.auth_error = None
        server.auth_state = None

        logger.info(f"Local callback server listening on {redirect_uri}")
        logger.info(f"Opening browser for Claude SSO login: {auth_request_url}")
        webbrowser.open(auth_request_url)

        # Wait for redirect (timeout after 5 minutes)
        timeout_seconds = 300
        start_time = time.time()

        while server.auth_code is None and server.auth_error is None:
            elapsed = time.time() - start_time
            if elapsed >= timeout_seconds:
                break

            server.timeout = timeout_seconds - elapsed
            server.handle_request()

        if server.auth_error:
            error_msg = f"OAuth authentication failed: {server.auth_error}"
            logger.error(error_msg)
            raise Exception(error_msg)

        if not server.auth_code:
            error_msg = "OAuth redirect timed out or failed"
            logger.error(error_msg)
            raise Exception(error_msg)

        auth_code = server.auth_code
        auth_state = server.auth_state
        logger.info("Received OAuth authorization code")

        # Verify state
        if auth_state != state:
            error_msg = "OAuth state mismatch - possible CSRF attempt"
            logger.error(error_msg)
            raise Exception(error_msg)

        # Exchange code for tokens (include state in body as per opencode implementation)
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "code": auth_code,
            "state": auth_state,  # Required by Anthropic OAuth
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,  # Must match the redirect_uri used in authorization
        }

        # Debug: log the token URL and request data
        logger.info(f"Token exchange URL: {TOKEN_URL}")
        logger.info(f"Token exchange data: {data}")

        try:
            # Try JSON format with Claude CLI User-Agent
            logger.info(
                "Attempting token exchange with JSON data and Claude CLI User-Agent..."
            )
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "claude-cli/2.1.2",
                "Accept": "application/json",
            }
            response = requests.post(TOKEN_URL, json=data, headers=headers, timeout=30)
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response URL: {response.url}")
            logger.info(f"Response headers: {dict(response.headers)}")
            logger.info(
                f"Response body: {response.text[:1000] if response.text else '(empty)'}"
            )
            response.raise_for_status()
            tokens = response.json()

            # Save tokens to cache
            self._save_tokens(tokens)

            logger.info("Successfully acquired Claude tokens")
            return tokens

        except requests.RequestException as e:
            error_msg = f"Failed to exchange code for tokens: {e}"
            logger.error(error_msg)
            # Try to get more details from response
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg = f"{error_msg} - {error_detail}"
                except Exception:
                    error_msg = f"{error_msg} - {e.response.text}"
            raise Exception(error_msg)

    def refresh_access_token(self, refresh_token: Optional[str] = None) -> dict:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: Refresh token (uses cached if not provided)

        Returns:
            New token dict

        Raises:
            Exception if refresh fails
        """
        if refresh_token is None and self._cached_tokens:
            refresh_token = self._cached_tokens.get("refresh_token")

        if not refresh_token:
            raise Exception("No refresh token available")

        logger.info("Refreshing Claude access token...")

        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": refresh_token,
        }

        try:
            # Use JSON format (Claude API requires JSON)
            headers = {"Content-Type": "application/json"}
            response = requests.post(TOKEN_URL, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            tokens = response.json()

            # Save new tokens
            self._save_tokens(tokens)

            logger.info("Successfully refreshed Claude access token")
            return tokens

        except requests.RequestException as e:
            logger.error(f"Token refresh failed: {e}")
            raise Exception(f"Failed to refresh Claude token: {e}")

    def get_token(self, force_interactive: bool = False) -> str:
        """
        Get valid access token, refreshing or re-authenticating as needed.

        Args:
            force_interactive: Force browser-based authentication

        Returns:
            Valid access token string

        Raises:
            Exception if authentication fails
        """
        if force_interactive:
            tokens = self.acquire_token_with_browser()
            return tokens["access_token"]

        # Try cached token first
        if self._cached_tokens:
            # Try to refresh if we have a refresh token
            if "refresh_token" in self._cached_tokens:
                try:
                    tokens = self.refresh_access_token()
                    return tokens["access_token"]
                except Exception as e:
                    logger.warning(
                        f"Token refresh failed, falling back to browser auth: {e}"
                    )

        # Fall back to browser authentication
        tokens = self.acquire_token_with_browser()
        return tokens["access_token"]

    def sign_out(self):
        """Clear cached tokens (sign out)."""
        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
                self._cached_tokens = None
                logger.info("Cleared Claude token cache (signed out)")
            except Exception as e:
                logger.error(f"Failed to clear token cache: {e}")
                raise


def create_claude_auth_client_from_env() -> ClaudeAuthClient:
    """
    Create Claude auth client from environment variables.

    Environment variables:
        CLAUDE_CLIENT_ID: OAuth client ID (defaults to official Claude CLI)
        CLAUDE_REDIRECT_PORT: Local port for redirect (default: 54545)
        CLAUDE_SCOPES: OAuth scopes (default: org:create_api_key user:profile user:inference)

    Returns:
        Initialized ClaudeAuthClient
    """
    client_id = os.getenv("CLAUDE_CLIENT_ID", DEFAULT_CLIENT_ID)
    redirect_port = int(os.getenv("CLAUDE_REDIRECT_PORT", DEFAULT_REDIRECT_PORT))
    scopes = os.getenv("CLAUDE_SCOPES", DEFAULT_SCOPES)

    return ClaudeAuthClient(
        client_id=client_id,
        redirect_port=redirect_port,
        scopes=scopes,
    )

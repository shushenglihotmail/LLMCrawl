"""
Authentication middleware for FastAPI Gateway.

Handles bearer token validation and optional Entra ID JWT token validation.
"""

import logging
import os
from typing import Optional

try:
    import jwt

    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logging.warning(
        "PyJWT not installed. JWT validation will be disabled. Install with: pip install PyJWT cryptography"
    )

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# Optional: JWT validation for Entra ID tokens
# If enabled, validates token signature and claims
JWT_VALIDATION_ENABLED = (
    os.getenv("JWT_VALIDATION_ENABLED", "false").lower() == "true" and JWT_AVAILABLE
)
ENTRA_TENANT_ID = os.getenv("ENTRA_TENANT_ID", "common")
ENTRA_CLIENT_ID = os.getenv("ENTRA_CLIENT_ID")


class BearerTokenAuth(HTTPBearer):
    """
    FastAPI dependency for bearer token authentication.

    Can be used in two modes:
    1. Pass-through: Extract token and pass to LLM (no validation)
    2. Validation: Validate JWT token against Entra ID (optional)
    """

    def __init__(self, auto_error: bool = False):
        """
        Initialize bearer token auth.

        Args:
            auto_error: If False, returns None for missing tokens instead of raising 401
        """
        super().__init__(auto_error=auto_error)
        self.validation_enabled = JWT_VALIDATION_ENABLED

        if self.validation_enabled:
            logger.info("JWT validation enabled for Entra ID tokens")
        else:
            logger.info("JWT validation disabled - tokens will be passed through")

    async def __call__(self, request: Request) -> Optional[str]:
        """
        Extract and optionally validate bearer token.

        Returns:
            Access token string if present, None otherwise

        Raises:
            HTTPException: If validation is enabled and token is invalid
        """
        # Get authorization header
        credentials: Optional[HTTPAuthorizationCredentials] = await super().__call__(
            request
        )

        if not credentials:
            # No token provided
            return None

        token = credentials.credentials

        # If validation is disabled, just return the token
        if not self.validation_enabled:
            logger.debug("Extracted bearer token (no validation)")
            return token

        # Validate JWT token
        if not JWT_AVAILABLE:
            logger.error("JWT validation requested but PyJWT is not installed")
            raise HTTPException(status_code=500, detail="JWT validation not available")

        try:
            validated_token = self._validate_token(token)
            logger.info(
                f"Validated token for user: {validated_token.get('preferred_username', 'unknown')}"
            )
            return token

        except jwt.ExpiredSignatureError:
            logger.error("Token has expired")
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid token: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise HTTPException(status_code=401, detail="Token validation failed")

    def _validate_token(self, token: str) -> dict:
        """
        Validate Entra ID JWT token.

        This performs basic JWT validation:
        - Signature verification (requires fetching JWKS from Microsoft)
        - Expiration check
        - Audience check
        - Issuer check

        Args:
            token: JWT token string

        Returns:
            Decoded token claims

        Raises:
            jwt.InvalidTokenError: If token is invalid
        """
        # Decode without verification first to get key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        if not kid:
            raise jwt.InvalidTokenError("Token missing key ID")

        # Get signing keys from Microsoft
        signing_key = self._get_signing_key(kid)

        # Decode and validate token
        issuer = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/v2.0"
        audience = ENTRA_CLIENT_ID or "api://default"  # Azure Foundry resource ID

        decoded = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
            },
        )

        return decoded

    def _get_signing_key(self, kid: str) -> str:
        """
        Fetch JWKS signing key from Microsoft.

        Args:
            kid: Key ID from token header

        Returns:
            Public key for signature verification

        Note: In production, you should cache JWKS to avoid repeated requests.
        """
        import httpx

        # Fetch JWKS from Microsoft
        jwks_url = (
            f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}/discovery/v2.0/keys"
        )

        try:
            response = httpx.get(jwks_url, timeout=10.0)
            response.raise_for_status()
            jwks = response.json()

            # Find the key matching kid
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    # Convert JWK to PEM format
                    from jwt.algorithms import RSAAlgorithm

                    return RSAAlgorithm.from_jwk(key)

            raise jwt.InvalidTokenError(f"Signing key not found: {kid}")

        except Exception as e:
            logger.error(f"Failed to fetch JWKS: {e}")
            raise jwt.InvalidTokenError(f"Failed to fetch signing keys: {e}")


# Global instance for dependency injection
bearer_auth = BearerTokenAuth(auto_error=False)


def get_bearer_token(request: Request) -> Optional[str]:
    """
    FastAPI dependency to extract bearer token from request.

    Usage:
        @app.get("/api/endpoint")
        async def endpoint(token: Optional[str] = Depends(get_bearer_token)):
            if token:
                # Use token for LLM authentication
                pass

    Returns:
        Access token string if present, None otherwise
    """
    # Extract Authorization header manually to avoid raising errors
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    return auth_header[7:]  # Remove "Bearer " prefix

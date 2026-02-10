from contextvars import ContextVar
from typing import Optional

# Context variable to store the bearer token for the current request
bearer_token: ContextVar[Optional[str]] = ContextVar("bearer_token", default=None)

# Context variable to store the provider type for the token (azure, claude, etc.)
token_provider: ContextVar[Optional[str]] = ContextVar("token_provider", default=None)


def set_token(token: str, provider: str = "azure") -> None:
    """
    Set the bearer token and provider for the current context.

    Args:
        token: Bearer token string
        provider: Provider type ("azure" for Azure Foundry, "claude" for Claude, etc.)
    """
    bearer_token.set(token)
    token_provider.set(provider)


def get_token() -> Optional[str]:
    """Get the bearer token from the current context."""
    return bearer_token.get()


def get_token_provider() -> Optional[str]:
    """Get the token provider from the current context."""
    return token_provider.get()


# Legacy alias for backward compatibility
azure_ad_token = bearer_token

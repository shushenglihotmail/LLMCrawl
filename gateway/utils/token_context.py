from contextvars import ContextVar
from typing import Optional

# Context variable to store the Azure AD token for the current request
azure_ad_token: ContextVar[Optional[str]] = ContextVar("azure_ad_token", default=None)


def set_token(token: str) -> None:
    """Set the Azure AD token for the current context."""
    azure_ad_token.set(token)


def get_token() -> Optional[str]:
    """Get the Azure AD token from the current context."""
    return azure_ad_token.get()

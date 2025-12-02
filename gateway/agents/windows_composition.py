import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class WindowsCompositionClient:
    """
    Client for the Windows Composition Bridge service running on the host.
    """

    def __init__(self, bridge_url: str):
        self.bridge_url = bridge_url.rstrip("/")

    async def run_query(self, query: str) -> str:
        """
        Sends a query to the bridge service.
        """
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.bridge_url}/query",
                    json={"query": query},
                )

                if response.status_code == 200:
                    result = response.json()
                    return str(result.get("result", ""))
                else:
                    error_msg = (
                        f"Bridge returned error: {response.status_code} - "
                        f"{response.text}"
                    )
                    logger.error(error_msg)
                    return f"Error: {error_msg}"

        except Exception as e:
            logger.error(f"Failed to query Windows Composition Bridge: {e}")
            return f"Error connecting to bridge: {str(e)}"


# Global instance
_client: Optional[WindowsCompositionClient] = None


def get_composition_client() -> Optional[WindowsCompositionClient]:
    """Get or create the global Windows Composition client."""
    global _client

    # Check if bridge URL is configured
    bridge_url = os.getenv("WIN_COMP_BRIDGE_URL")

    # Fallback: If SHARE_CMD is set but BRIDGE_URL is not, we might be in a mode
    # where we expect the bridge to be at a default location
    # (e.g. host.docker.internal:8005)
    # But explicit config is better.

    if not bridge_url:
        return None

    if _client is None:
        _client = WindowsCompositionClient(bridge_url)

    return _client

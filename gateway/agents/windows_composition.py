import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class WindowsCompositionClient:
    """
    Client for the Windows Composition Bridge service.

    The bridge is started on demand by WcdBridgeManager and the URL is
    obtained from it — no manual WIN_COMP_BRIDGE_URL needed.
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
    """Get or create the global Windows Composition client.

    Uses WcdBridgeManager to get the bridge URL (on-demand startup).
    """
    global _client

    from gateway.utils.wcd_bridge_manager import get_wcd_bridge_manager

    mgr = get_wcd_bridge_manager()
    if not mgr.available or not mgr.bridge_url:
        return None

    if _client is None or _client.bridge_url != mgr.bridge_url.rstrip("/"):
        _client = WindowsCompositionClient(mgr.bridge_url)

    return _client

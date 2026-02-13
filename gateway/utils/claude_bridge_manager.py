"""
Claude Bridge Manager - handles startup discovery and model caching.

On gateway startup, probes the Claude Bridge (host-side) with retries.
If the bridge is available, discovers and caches Claude models.
If the bridge is unavailable, gateway starts normally without Claude models.

The cached model list is used by:
- models.py (GET /api/models/available) to include Claude models
- llm/client.py (get_model_config) to route Claude models to the bridge
"""

import logging
import os
from typing import Dict, List, Optional, Set

import httpx

logger = logging.getLogger(__name__)


class ClaudeBridgeManager:
    """Manages connection to the host-side Claude Bridge service."""

    def __init__(self):
        self.bridge_url: Optional[str] = os.getenv("CLAUDE_BRIDGE_URL")
        self.available: bool = False
        self._cached_models: List[Dict[str, str]] = []
        self._claude_model_names: Set[str] = set()

    @property
    def cached_models(self) -> List[Dict[str, str]]:
        """Return cached Claude models (name + display_name)."""
        return self._cached_models

    @property
    def claude_model_names(self) -> Set[str]:
        """Set of Claude model names discovered from the bridge."""
        return self._claude_model_names

    def is_claude_model(self, model_name: str) -> bool:
        """Check if a model was discovered from the Claude bridge."""
        return model_name in self._claude_model_names

    async def probe_and_discover(
        self,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> bool:
        """
        Probe the Claude Bridge and discover available models.

        Called once at gateway startup. Retries a few times to allow
        the bridge to finish starting.

        Returns:
            True if bridge is available and models were discovered.
        """
        if not self.bridge_url:
            logger.info("CLAUDE_BRIDGE_URL not set — Claude models disabled")
            return False

        import asyncio

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"Probing Claude Bridge at {self.bridge_url} "
                    f"(attempt {attempt}/{max_retries})..."
                )

                async with httpx.AsyncClient(timeout=10.0) as client:
                    # Health check first
                    health_resp = await client.get(
                        f"{self.bridge_url.rstrip('/')}/health"
                    )
                    health_resp.raise_for_status()
                    health = health_resp.json()

                    if health.get("status") != "healthy":
                        logger.warning(f"Claude Bridge unhealthy: {health}")
                        if attempt < max_retries:
                            await asyncio.sleep(retry_delay)
                            continue
                        return False

                    # Discover models
                    models_resp = await client.get(
                        f"{self.bridge_url.rstrip('/')}/models"
                    )
                    models_resp.raise_for_status()
                    models_data = models_resp.json()

                self._cached_models = []
                self._claude_model_names = set()

                for m in models_data:
                    name = m.get("name", "")
                    display_name = m.get("display_name", name)
                    self._cached_models.append(
                        {"name": name, "display_name": display_name}
                    )
                    self._claude_model_names.add(name)

                self.available = True
                logger.info(
                    f"Claude Bridge ready — {len(self._cached_models)} models: "
                    f"{', '.join(sorted(self._claude_model_names))}"
                )
                return True

            except Exception as e:
                logger.warning(f"Claude Bridge probe attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay)

        logger.warning(
            "Claude Bridge not available after all retries — "
            "gateway will start without Claude models"
        )
        self.available = False
        return False


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_manager: Optional[ClaudeBridgeManager] = None


def get_claude_bridge_manager() -> ClaudeBridgeManager:
    """Get or create the global ClaudeBridgeManager."""
    global _manager
    if _manager is None:
        _manager = ClaudeBridgeManager()
    return _manager

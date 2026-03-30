"""
Copilot Bridge Manager - handles startup discovery and model caching.

On gateway startup, checks for Copilot CLI availability (local or HTTP bridge).
If available, populates model list from known models.
If unavailable, gateway starts normally without Copilot models.

The cached model list is used by:
- models.py (GET /api/models/available) to include Copilot models
- llm/client.py (get_model_config) to route Copilot models
"""

import logging
import os
from typing import Dict, List, Optional, Set

import httpx

logger = logging.getLogger(__name__)


class CopilotBridgeManager:
    """Manages connection to Copilot CLI or host-side Copilot Bridge service."""

    def __init__(self):
        self.bridge_url: Optional[str] = os.getenv("COPILOT_BRIDGE_URL")
        self.available: bool = False
        self._cached_models: List[Dict[str, str]] = []
        self._copilot_model_names: Set[str] = set()

    @property
    def cached_models(self) -> List[Dict[str, str]]:
        """Return cached Copilot models (name + display_name)."""
        return self._cached_models

    @property
    def copilot_model_names(self) -> Set[str]:
        """Set of Copilot model names available."""
        return self._copilot_model_names

    def is_copilot_model(self, model_name: str) -> bool:
        """Check if a model is a known Copilot model."""
        return model_name in self._copilot_model_names

    async def probe_and_discover(
        self,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> bool:
        """
        Probe for Copilot availability and populate model list.

        Checks:
        1. HTTP bridge (if COPILOT_BRIDGE_URL set)
        2. Local CLI (copilot.exe on PATH or known locations)

        Returns:
            True if Copilot is available.
        """
        # Try HTTP bridge first
        if self.bridge_url:
            import asyncio

            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(
                        f"Probing Copilot Bridge at {self.bridge_url} "
                        f"(attempt {attempt}/{max_retries})..."
                    )
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        health_resp = await client.get(
                            f"{self.bridge_url.rstrip('/')}/health"
                        )
                        health_resp.raise_for_status()
                        health = health_resp.json()

                        if health.get("status") != "healthy":
                            if attempt < max_retries:
                                await asyncio.sleep(retry_delay)
                                continue
                            break

                        models_resp = await client.get(
                            f"{self.bridge_url.rstrip('/')}/models"
                        )
                        models_resp.raise_for_status()
                        models_data = models_resp.json()

                    self._cached_models = []
                    self._copilot_model_names = set()
                    for m in models_data:
                        name = m.get("name", "")
                        display_name = m.get("display_name", name)
                        self._cached_models.append(
                            {"name": name, "display_name": display_name}
                        )
                        self._copilot_model_names.add(name)

                    self.available = True
                    logger.info(
                        f"Copilot Bridge ready — {len(self._cached_models)} models"
                    )
                    return True

                except Exception as e:
                    logger.warning(
                        f"Copilot Bridge probe attempt {attempt} failed: {e}"
                    )
                    if attempt < max_retries:
                        import asyncio

                        await asyncio.sleep(retry_delay)

        # Try local CLI detection
        from gateway.llm.cli_providers import COPILOT_KNOWN_MODELS, CopilotCLIProvider

        cli = CopilotCLIProvider()
        if cli.available:
            self._cached_models = []
            self._copilot_model_names = set()
            for name, display_name in COPILOT_KNOWN_MODELS:
                self._cached_models.append({"name": name, "display_name": display_name})
                self._copilot_model_names.add(name)

            self.available = True
            logger.info(
                f"Copilot CLI available — {len(self._cached_models)} known models"
            )
            return True

        logger.info(
            "Copilot not available (no CLI found, no bridge configured) "
            "— gateway will start without Copilot models"
        )
        return False


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_manager: Optional[CopilotBridgeManager] = None


def get_copilot_bridge_manager() -> CopilotBridgeManager:
    """Get or create the global CopilotBridgeManager."""
    global _manager
    if _manager is None:
        _manager = CopilotBridgeManager()
    return _manager

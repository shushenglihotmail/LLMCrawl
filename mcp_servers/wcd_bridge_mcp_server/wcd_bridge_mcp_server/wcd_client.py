from __future__ import annotations

from typing import Any, Dict, Optional, cast

import httpx


class WcdBridgeClient:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 60.0,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._headers = headers or {}

    async def health(self) -> Dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self._timeout_s, headers=self._headers
        ) as c:
            resp = await c.get(f"{self.base_url}/health")
            resp.raise_for_status()
            return cast(Dict[str, Any], resp.json())

    async def query(self, query: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self._timeout_s, headers=self._headers
        ) as c:
            resp = await c.post(f"{self.base_url}/query", json={"query": query})
            resp.raise_for_status()
            return cast(Dict[str, Any], resp.json())

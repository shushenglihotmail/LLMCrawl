from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class CrawlerClient:
    def __init__(
        self,
        base_url: str,
        timeout_s: float = 120.0,
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
            result: Dict[str, Any] = resp.json()
            return result

    async def crawl(
        self,
        query: str,
        freshness_days: int = 7,
        depth: int = 1,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "query": query,
            "freshness_days": freshness_days,
            "depth": depth,
            "max_results": max_results,
        }
        async with httpx.AsyncClient(
            timeout=self._timeout_s, headers=self._headers
        ) as c:
            resp = await c.post(f"{self.base_url}/crawl", json=payload)
            resp.raise_for_status()
            result: Dict[str, Any] = resp.json()
            return result

    async def render(self, url: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self._timeout_s, headers=self._headers
        ) as c:
            resp = await c.post(f"{self.base_url}/render", json={"url": url})
            resp.raise_for_status()
            result: Dict[str, Any] = resp.json()
            return result

    async def extract(self, url: str, html: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self._timeout_s, headers=self._headers
        ) as c:
            resp = await c.post(
                f"{self.base_url}/extract",
                json={"url": url, "html": html},
            )
            resp.raise_for_status()
            result: Dict[str, Any] = resp.json()
            return result

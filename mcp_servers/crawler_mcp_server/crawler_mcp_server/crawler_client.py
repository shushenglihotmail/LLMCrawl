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
        """
        Crawl a URL and return extracted content.

        Simple crawling - just pass the URL to the crawler service.
        The crawler will render and extract content.

        Args:
            query: URL to crawl (should be a full URL)
            freshness_days: Not used (kept for compatibility)
            depth: Crawl depth (1=single page, >1=follow links)
            max_results: Maximum number of documents to return

        Returns:
            Dict with 'docs' list containing full content, markdown, HTML, etc.
        """
        # Simple: just pass the URL(s) to crawler
        urls = [query] if query.startswith(("http://", "https://")) else []

        if not urls:
            return {"docs": [], "total_found": 0, "processed": 0}

        payload: Dict[str, Any] = {
            "urls": urls,
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

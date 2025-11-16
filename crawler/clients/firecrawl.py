"""
Firecrawl client for web crawling and content extraction.
Handles search, crawling, and content processing via Firecrawl API.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)


class FirecrawlClient:
    """Client for interacting with Firecrawl API."""

    def __init__(self):
        self.base_url = os.getenv("FIRECRAWL_URL", "http://firecrawl:3002")
        self.api_key = os.getenv("FIRECRAWL_API_KEY", "")
        self.timeout = int(os.getenv("REQUEST_TIMEOUT_MS", "20000")) / 1000
        self.max_concurrency = int(os.getenv("MAX_CONCURRENCY", "4"))

        # Authentication configuration for internal sites
        self.auth_type = os.getenv("FIRECRAWL_AUTH_TYPE", "none")
        self.auth_headers = self._parse_json_env("FIRECRAWL_AUTH_HEADERS", {})
        self.auth_cookies = self._parse_json_env("FIRECRAWL_AUTH_COOKIES", {})
        self.auth_username = os.getenv("FIRECRAWL_AUTH_USERNAME", "")
        self.auth_password = os.getenv("FIRECRAWL_AUTH_PASSWORD", "")
        self.auth_token = os.getenv("FIRECRAWL_AUTH_TOKEN", "")

        # Setup HTTP client with authentication
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            headers=headers,
            limits=httpx.Limits(max_connections=self.max_concurrency),
        )

        logger.info(
            f"Initialized Firecrawl client: {self.base_url} "
            f"(auth_type: {self.auth_type})"
        )

    async def search_and_crawl(
        self,
        query: str,
        seed_urls: List[str] = None,
        freshness_days: int = 7,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search the web and crawl resulting pages.

        Args:
            query: Search query
            seed_urls: Optional seed URLs to prioritize
            freshness_days: How recent content should be
            max_results: Maximum number of results to return

        Returns:
            List of crawled documents with metadata
        """
        try:
            # First, search for relevant URLs
            search_results = await self._search(query, seed_urls, max_results)

            if not search_results:
                logger.warning(f"No search results for query: {query}")
                return []

            # Filter by freshness if needed
            if freshness_days > 0:
                cutoff_date = datetime.now() - timedelta(days=freshness_days)
                search_results = self._filter_by_freshness(search_results, cutoff_date)

            # Crawl the resulting URLs
            documents = []
            semaphore = asyncio.Semaphore(self.max_concurrency)

            async def crawl_url(url_data):
                async with semaphore:
                    return await self._crawl_single_url(url_data)

            tasks = [crawl_url(url_data) for url_data in search_results]

            # Add timeout to prevent indefinite hanging
            try:
                crawl_results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=25.0,  # 25 seconds total for all crawls
                )
            except asyncio.TimeoutError:
                logger.error(f"Crawling timed out after 25 seconds for query: {query}")
                crawl_results = []

            for result in crawl_results:
                if isinstance(result, Exception):
                    logger.error(f"Crawl failed: {result}")
                elif result:
                    documents.append(result)

            logger.info(
                f"Successfully crawled {len(documents)} documents for query: {query}"
            )
            return documents

        except Exception as e:
            logger.error(f"Search and crawl failed: {e}")
            return []

    async def crawl_url(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Crawl a single URL and extract content.

        Args:
            url: URL to crawl

        Returns:
            Document data or None if failed
        """
        return await self._crawl_single_url({"url": url})

    async def _search(
        self, query: str, seed_urls: List[str] = None, max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for URLs using Firecrawl search API."""
        try:
            search_params = {
                "query": query,
                "limit": max_results,
                "include_domains": (
                    self._extract_domains(seed_urls) if seed_urls else None
                ),
            }

            # Remove None values
            search_params = {k: v for k, v in search_params.items() if v is not None}

            response = await self.client.post(
                urljoin(self.base_url, "/v1/search"), json=search_params
            )
            response.raise_for_status()

            data = response.json()
            return data.get("data", [])

        except httpx.HTTPStatusError as e:
            logger.error(f"Firecrawl search HTTP error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Firecrawl search failed: {e}")
            return []

    async def _crawl_single_url(
        self, url_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Crawl a single URL using Firecrawl."""
        url = url_data.get("url")
        if not url:
            return None

        try:
            crawl_params = {
                "url": url,
                "formats": ["markdown", "html"],
                "onlyMainContent": True,
                "includeTags": ["title", "meta"],
                "excludeTags": ["script", "style", "nav", "footer"],
                "waitFor": 1000,  # Wait for JavaScript
            }

            # Add authentication based on configured type
            auth_config = self._get_auth_config()
            if auth_config.get("headers"):
                crawl_params["headers"] = auth_config["headers"]
            if auth_config.get("cookies"):
                crawl_params["cookies"] = auth_config["cookies"]

            response = await self.client.post(
                urljoin(self.base_url, "/v1/scrape"), json=crawl_params
            )
            response.raise_for_status()

            data = response.json()

            if not data.get("success"):
                logger.warning(f"Firecrawl crawl unsuccessful for {url}")
                return None

            content_data = data.get("data", {})

            # Extract and structure the document
            document = {
                "url": url,
                "title": content_data.get("metadata", {}).get("title", ""),
                "markdown": content_data.get("markdown", ""),
                "html": content_data.get("html", ""),
                "metadata": content_data.get("metadata", {}),
                "published_at": self._extract_published_date(content_data),
                "fetched_at": datetime.now().isoformat(),
                "source": urlparse(url).netloc,
                "content_hash": self._generate_content_hash(
                    content_data.get("markdown", "")
                ),
            }

            return document

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Firecrawl crawl HTTP error for {url}: {e.response.status_code}"
            )
            return None
        except Exception as e:
            logger.error(f"Firecrawl crawl failed for {url}: {e}")
            return None

    def _extract_domains(self, urls: List[str]) -> List[str]:
        """Extract domains from a list of URLs."""
        domains = []
        for url in urls:
            try:
                domain = urlparse(url).netloc
                if domain and domain not in domains:
                    domains.append(domain)
            except Exception:
                continue
        return domains

    def _filter_by_freshness(
        self, results: List[Dict[str, Any]], cutoff_date: datetime
    ) -> List[Dict[str, Any]]:
        """Filter search results by publication date."""
        filtered = []
        for result in results:
            pub_date = self._extract_published_date(result)
            if pub_date:
                try:
                    if (
                        datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                        >= cutoff_date
                    ):
                        filtered.append(result)
                except Exception:
                    # If date parsing fails, include the result anyway
                    filtered.append(result)
            else:
                # If no date available, include the result
                filtered.append(result)

        return filtered

    def _extract_published_date(self, data: Dict[str, Any]) -> Optional[str]:
        """Extract published date from content data."""
        # Try various metadata fields for publication date
        metadata = data.get("metadata", {})

        date_fields = [
            "publishedTime",
            "article:published_time",
            "datePublished",
            "pubdate",
            "date",
        ]

        for field in date_fields:
            if field in metadata and metadata[field]:
                return metadata[field]

        return None

    def _generate_content_hash(self, content: str) -> str:
        """Generate a hash for content deduplication."""
        import hashlib

        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def _parse_json_env(self, key: str, default: dict) -> dict:
        """Parse JSON from environment variable."""
        import json

        value = os.getenv(key, "")
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in environment variable {key}")
            return default

    def _get_auth_config(self) -> Dict[str, Any]:
        """
        Get authentication configuration based on auth type.

        Returns:
            Dict with 'headers' and/or 'cookies' for authentication
        """
        config = {"headers": {}, "cookies": {}}

        if self.auth_type == "headers":
            # Custom headers authentication
            if self.auth_headers:
                config["headers"].update(self.auth_headers)
                logger.debug("Using custom headers authentication")

        elif self.auth_type == "cookies":
            # Cookie-based authentication
            if self.auth_cookies:
                config["cookies"].update(self.auth_cookies)
                logger.debug("Using cookie-based authentication")

        elif self.auth_type == "basic":
            # Basic authentication
            if self.auth_username and self.auth_password:
                import base64

                credentials = f"{self.auth_username}:{self.auth_password}"
                encoded = base64.b64encode(credentials.encode()).decode()
                config["headers"]["Authorization"] = f"Basic {encoded}"
                logger.debug("Using basic authentication")

        elif self.auth_type == "bearer":
            # Bearer token authentication
            if self.auth_token:
                config["headers"]["Authorization"] = f"Bearer {self.auth_token}"
                logger.debug("Using bearer token authentication")

        return config

    async def health_check(self) -> Dict[str, Any]:
        """Check if Firecrawl service is healthy."""
        try:
            # FireCrawl doesn't have /health, use root endpoint instead
            response = await self.client.get(self.base_url)
            response.raise_for_status()

            return {"status": "healthy", "service": "firecrawl", "url": self.base_url}

        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "firecrawl",
                "url": self.base_url,
                "error": str(e),
            }

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

"""
Firecrawl client for web crawling and content extraction.
Handles search, crawling, and content processing via Firecrawl API.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
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

        # Cookie-based authentication for internal sites (e.g., www.osgwiki.com)
        self.auth_type = os.getenv("FIRECRAWL_AUTH_TYPE", "none")

        # Parse storage_state for cookie-based auth
        # First try from env var, then from file path
        self.auth_storage_state = self._load_storage_state()
        self.auth_cookies = self._build_cookie_map()

        # Setup HTTP client
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            headers=headers,
            limits=httpx.Limits(max_connections=self.max_concurrency),
        )

        # Log authentication status
        if self.auth_type == "cookies" and self.auth_cookies:
            domains = list(self.auth_cookies.keys())
            total_cookies = sum(len(c) for c in self.auth_cookies.values())
            logger.info(
                f"Initialized Firecrawl client: {self.base_url} "
                f"(auth_type: {self.auth_type}, {total_cookies} cookies for {domains})"
            )
        else:
            logger.info(
                f"Initialized Firecrawl client: {self.base_url} (auth_type: {self.auth_type})"
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

    async def crawl_urls(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Crawl multiple URLs directly (bypass search).

        Use this for seed URLs that should be scraped directly.

        Args:
            urls: List of URLs to crawl

        Returns:
            List of crawled documents
        """
        if not urls:
            return []

        documents = []
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def crawl_with_semaphore(url: str):
            async with semaphore:
                return await self._crawl_single_url({"url": url})

        tasks = [crawl_with_semaphore(url) for url in urls]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.error(f"Crawling seed URLs timed out after 30 seconds")
            results = []

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Crawl failed: {result}")
            elif result:
                # Filter out login/auth pages that indicate failed authentication
                title = result.get("title", "").lower()
                markdown = result.get("markdown", "").lower()
                if any(indicator in title for indicator in ["sign in", "login", "authenticate", "access denied"]):
                    logger.warning(f"Skipping login page: {result.get('url')}")
                    continue
                if "sign in to your account" in markdown[:500] or "please sign in" in markdown[:500]:
                    logger.warning(f"Skipping login page (content): {result.get('url')}")
                    continue
                result["source"] = "firecrawl"  # Mark as firecrawl source
                documents.append(result)

        logger.info(f"FireCrawl directly crawled {len(documents)}/{len(urls)} URLs")
        return documents

    async def _search(
        self, query: str, seed_urls: List[str] = None, max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for URLs using Firecrawl search API."""
        try:
            search_params = {
                "query": query,
                "limit": max_results,
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
                "onlyMainContent": False,  # Get full page for internal wikis
                "includeTags": ["title", "meta", "article", "main", "div", "p", "h1", "h2", "h3", "ul", "ol", "li", "table"],
                "excludeTags": ["script", "style"],
                "waitFor": 3000,  # Wait longer for JavaScript (3 seconds)
            }

            # Add authentication headers (cookies passed as Cookie header)
            auth_config = await self._get_auth_config(url)
            if auth_config.get("headers"):
                crawl_params["headers"] = auth_config["headers"]
                logger.info(f"Using cookie auth for {url}")

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

    def _load_storage_state(self) -> Optional[Dict[str, Any]]:
        """
        Load storage_state from env var or file path.

        Tries FIRECRAWL_AUTH_STORAGE_STATE env var first (JSON string),
        then falls back to STORAGE_STATE_PATH file.

        Returns:
            Parsed storage_state dict or None
        """
        # First try env var with JSON content
        env_json = os.getenv("FIRECRAWL_AUTH_STORAGE_STATE", "")
        if env_json:
            try:
                return json.loads(env_json)
            except json.JSONDecodeError:
                logger.error("Invalid JSON in FIRECRAWL_AUTH_STORAGE_STATE env var")

        # Then try file path
        file_path = os.getenv("STORAGE_STATE_PATH", "")
        if file_path:
            path = Path(file_path)
            if path.is_file():
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                        cookie_count = len(data.get("cookies", []))
                        logger.info(f"Loaded storage_state from {file_path} ({cookie_count} cookies)")
                        return data
                except (json.JSONDecodeError, IOError) as e:
                    logger.error(f"Failed to load storage_state from {file_path}: {e}")
            else:
                logger.warning(f"STORAGE_STATE_PATH set but file not found: {file_path}")

        return None

    def _build_cookie_map(self) -> Dict[str, Dict[str, str]]:
        """
        Build a map of domain -> {cookie_name: cookie_value} from storage_state.

        Returns:
            Dict mapping domains to their cookies
        """
        cookie_map = {}
        if not self.auth_storage_state:
            return cookie_map

        cookies = self.auth_storage_state.get("cookies", [])
        for cookie in cookies:
            domain = cookie.get("domain", "").lstrip(".")
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            if domain and name:
                if domain not in cookie_map:
                    cookie_map[domain] = {}
                cookie_map[domain][name] = value

        return cookie_map

    def _get_cookie_header_for_url(self, url: str) -> Optional[str]:
        """
        Get Cookie header string for a given URL based on stored cookies.

        Args:
            url: The URL to get cookies for

        Returns:
            Cookie header string or None if no matching cookies
        """
        if not self.auth_cookies:
            return None

        try:
            parsed = urlparse(url)
            host = parsed.netloc.lower()

            # Find matching cookies for this domain
            matching_cookies = {}
            for domain, cookies in self.auth_cookies.items():
                # Match exact domain or subdomain
                if host == domain or host.endswith("." + domain):
                    matching_cookies.update(cookies)

            if matching_cookies:
                # Build cookie header string: "name1=value1; name2=value2"
                cookie_str = "; ".join(
                    f"{name}={value}" for name, value in matching_cookies.items()
                )
                return cookie_str

        except Exception as e:
            logger.error(f"Error building cookie header for {url}: {e}")

        return None

    async def _get_auth_config(self, url: str = None) -> Dict[str, Any]:
        """
        Get authentication configuration for FireCrawl API.

        For cookie-based auth, builds a Cookie header from storage_state
        that FireCrawl will use when scraping the page.

        Args:
            url: The URL being crawled (used to match domain-specific cookies)

        Returns:
            Dict with 'headers' key containing auth headers for FireCrawl API
        """
        config = {}

        if self.auth_type == "cookies" and url:
            cookie_header = self._get_cookie_header_for_url(url)
            if cookie_header:
                config["headers"] = {
                    "Cookie": cookie_header,
                    # Match browser User-Agent to avoid being blocked
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                logger.debug(f"Added Cookie header for {url}")

        return config

    async def health_check(self) -> Dict[str, Any]:
        """Check if Firecrawl service is healthy."""
        try:
            # FireCrawl doesn't have /health, use root endpoint instead
            # Note: Firecrawl redirects root to docs (302), which is expected behavior
            response = await self.client.get(self.base_url, follow_redirects=False)
            # Accept 200 OK or 302 redirect (redirect to docs is expected)
            if response.status_code in (200, 302):
                return {
                    "status": "healthy",
                    "service": "firecrawl",
                    "url": self.base_url,
                }
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

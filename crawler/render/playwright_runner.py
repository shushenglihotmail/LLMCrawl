"""
Playwright-based web rendering for JavaScript-heavy pages.
Provides fallback rendering when Firecrawl fails or for SPA content.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

try:
    from playwright.async_api import Browser, Page, async_playwright
except ImportError:
    async_playwright = None
    Page = None
    Browser = None

logger = logging.getLogger(__name__)


class PlaywrightRenderer:
    """Playwright-based web page renderer for JavaScript content."""

    def __init__(self):
        self.headless = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
        self.timeout = int(os.getenv("REQUEST_TIMEOUT_MS", "20000"))
        self.user_agent = os.getenv("USER_AGENT", "WebRAG/1.0")
        self.max_concurrency = int(os.getenv("MAX_CONCURRENCY", "4"))

        # Cookie-based authentication configuration
        self.auth_type = os.getenv("FIRECRAWL_AUTH_TYPE", "none")
        self.auth_storage_state = self._load_storage_state()

        self._browser = None
        self._playwright = None
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        self._browser_lock = asyncio.Lock()  # Lock for browser initialization

        if not async_playwright:
            logger.warning(
                "Playwright not installed - JavaScript rendering unavailable"
            )

        if self.auth_type == "cookies" and self.auth_storage_state:
            storage_cookies = len(self.auth_storage_state.get("cookies", []))
            logger.info(
                f"Playwright renderer configured with storage_state authentication ({storage_cookies} cookies)"
            )

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

    async def search_google(self, query: str, max_results: int = 5) -> List[str]:
        """
        Search Google and extract URLs from search results.

        Args:
            query: Search query
            max_results: Maximum number of URLs to return

        Returns:
            List of URLs from search results
        """
        if not async_playwright:
            logger.error("Playwright not available for Google search")
            return []

        urls = []

        try:
            async with self._semaphore:
                await self._ensure_browser()

                # Try DuckDuckGo instead of Google since Google blocks automated browsers
                page = await self._browser.new_page()

                # Set more realistic headers to avoid detection
                await page.set_extra_http_headers(
                    {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                        "Accept-Encoding": "gzip, deflate, br",
                        "DNT": "1",
                        "Connection": "keep-alive",
                        "Upgrade-Insecure-Requests": "1",
                    }
                )

                # Use DuckDuckGo which is more bot-friendly
                # Try the search page directly with a different URL format
                search_url = f"https://duckduckgo.com/html/?q={query.replace(' ', '+')}"
                logger.info(f"Searching DuckDuckGo HTML: {search_url}")

                response = await page.goto(
                    search_url, wait_until="domcontentloaded", timeout=self.timeout
                )
                logger.info(f"DuckDuckGo response status: {response.status}")

                # Wait for search results to load
                await page.wait_for_timeout(2000)

                # Get page title and content to verify
                title = await page.title()
                logger.info(f"Page title: {title}")

                # DuckDuckGo HTML search result selectors
                result_selectors = [
                    ".result__a",  # Main result links in HTML version
                    "h2 a",  # Generic result title links
                    ".result__title a",  # Alternative title links
                    "a[href^='http']:not([href*='duckduckgo'])",  # All external links except DDG
                ]

                found_results = False
                for selector in result_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        if elements and len(elements) > 0:
                            found_results = True
                            logger.info(
                                f"Found {len(elements)} results using selector: {selector}"
                            )

                            for element in elements[:max_results]:
                                try:
                                    href = await element.get_attribute("href")
                                    if (
                                        href
                                        and href.startswith("http")
                                        and not any(
                                            skip in href.lower()
                                            for skip in [
                                                "duckduckgo.com",
                                                "google.com",
                                                "youtube.com",
                                                "facebook.com",
                                                "twitter.com",
                                            ]
                                        )
                                    ):
                                        urls.append(href)
                                        logger.info(f"Added URL: {href}")

                                        if len(urls) >= max_results:
                                            break
                                except Exception as e:
                                    logger.debug(f"Error extracting URL: {e}")
                                    continue
                            break
                    except Exception as e:
                        logger.debug(f"Selector {selector} failed: {e}")
                        continue

                if not found_results:
                    logger.warning("No search results found on DuckDuckGo HTML version")
                    # Try to debug what's on the page
                    page_content = await page.content()
                    if len(page_content) > 0:
                        # Look for any links as backup
                        all_links = await page.query_selector_all("a[href^='http']")
                        logger.info(f"Found {len(all_links)} total http links on page")
                        for link in all_links[:3]:  # Debug first few links
                            try:
                                href = await link.get_attribute("href")
                                text = await link.inner_text()
                                logger.debug(f"Sample link: {text[:50]} -> {href}")
                            except:
                                continue

                await page.close()
                logger.info(f"DuckDuckGo search for '{query}' found {len(urls)} URLs")

        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")

        return urls

    async def render_page(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Render a single page with Playwright.

        Args:
            url: URL to render

        Returns:
            Rendered page data with HTML and metadata
        """
        if not async_playwright:
            logger.error("Playwright not available for rendering")
            return None

        async with self._semaphore:
            context = None
            try:
                logger.info(f"Starting render for {url}")
                await self._ensure_browser()
                logger.info(f"Browser ensured for {url}")

                # Prepare context options
                context_options = {
                    "user_agent": self.user_agent,
                    "viewport": {"width": 1920, "height": 1080},
                }

                # If we have storage_state, use it to restore entire browser session
                # This includes cookies across all domains (for SSO scenarios)
                if self.auth_type == "cookies" and self.auth_storage_state:
                    context_options["storage_state"] = self.auth_storage_state
                    logger.info(
                        f"Creating context with storage_state ({len(self.auth_storage_state.get('cookies', []))} cookies)"
                    )

                context = await self._browser.new_context(**context_options)
                logger.info(f"Context created for {url}")

                page = await context.new_page()
                logger.info(f"Page created for {url}")

                # Set up page with reasonable defaults
                extra_headers = {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "keep-alive",
                }

                await page.set_extra_http_headers(extra_headers)

                # Navigate to page
                response = await page.goto(
                    url, wait_until="domcontentloaded", timeout=self.timeout
                )

                if not response or response.status >= 400:
                    # Log authentication issues with more details
                    status = response.status if response else "no response"
                    logger.error(f"Failed to load page {url}: status {status}")
                    if response and response.status == 401:
                        # Get www-authenticate header if present
                        auth_header = response.headers.get("www-authenticate", "")
                        if auth_header:
                            logger.error(f"WWW-Authenticate header: {auth_header}")
                        # Check if we got redirected
                        if response.url != url:
                            logger.error(f"Redirected from {url} to {response.url}")
                        # Get the HTML to see what the auth page looks like
                        try:
                            html = await page.content()
                            if "login" in html.lower() or "sign in" in html.lower():
                                logger.error(
                                    "Page contains login/sign-in elements - auth failed"
                                )
                            logger.debug(f"401 response HTML preview: {html[:500]}")
                        except Exception as e:
                            logger.error(f"Could not read 401 page content: {e}")
                    return None

                # Wait for JavaScript to execute and content to load
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    # Continue even if network doesn't go idle
                    pass

                # Additional wait for dynamic content
                await asyncio.sleep(2)

                # Extract page data
                html = await page.content()
                title = await page.title()

                # Get meta information
                metadata = await self._extract_metadata(page)

                return {
                    "url": url,
                    "html": html,
                    "title": title,
                    "metadata": metadata,
                    "status_code": response.status,
                    "rendered_at": datetime.now().isoformat(),
                    "user_agent": self.user_agent,
                }

            except Exception as e:
                logger.error(f"Playwright rendering failed for {url}: {e}")
                return None

            finally:
                # Always clean up context
                if context:
                    try:
                        await context.close()
                    except Exception as e:
                        logger.warning(f"Error closing context: {e}")

    async def render_multiple(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Render multiple URLs sequentially to avoid browser conflicts.

        Args:
            urls: List of URLs to render

        Returns:
            List of rendered page data
        """
        if not async_playwright:
            logger.error("Playwright not available for rendering")
            return []

        documents = []
        for url in urls:
            try:
                logger.info(f"Rendering URL {url}")
                result = await self.render_page(url)
                if result:
                    documents.append(result)
                    logger.info(f"Successfully rendered {url}")
                else:
                    logger.warning(f"No result for {url}")
            except Exception as e:
                logger.error(f"Rendering failed for {url}: {e}")

        return documents

    async def _ensure_browser(self):
        """Ensure browser is launched and ready."""
        async with self._browser_lock:  # Protect browser initialization
            try:
                # Check if browser is still connected
                if self._browser:
                    try:
                        is_connected = self._browser.is_connected()
                        logger.info(f"Browser connection status: {is_connected}")
                        if not is_connected:
                            logger.warning("Browser was disconnected, relaunching...")
                            # Clean up old browser
                            try:
                                await self._browser.close()
                            except:
                                pass
                            self._browser = None
                    except Exception as e:
                        logger.warning(f"Error checking browser connection: {e}")
                        # Clean up old browser
                        try:
                            await self._browser.close()
                        except:
                            pass
                        self._browser = None

                if not self._browser:
                    if not self._playwright:
                        logger.info("Starting new Playwright instance...")
                        self._playwright = await async_playwright().start()

                    logger.info("Launching new Chromium browser...")
                    self._browser = await self._playwright.chromium.launch(
                        headless=self.headless,
                        args=[
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--disable-web-security",
                            "--disable-features=VizDisplayCompositor",
                        ],
                    )

                    # Give browser a moment to initialize
                    await asyncio.sleep(0.1)

                    # Verify connection
                    if not self._browser.is_connected():
                        logger.error("Browser failed to connect after launch")
                        raise Exception("Browser not connected after launch")

                    logger.info(
                        f"Playwright browser launched successfully. Connected: {self._browser.is_connected()}"
                    )
            except Exception as e:
                logger.error(f"Failed to ensure browser: {e}")
                # Reset everything and try again
                self._browser = None
                self._playwright = None
                raise

    async def _extract_metadata(self, page) -> Dict[str, Any]:
        """Extract metadata from a rendered page."""
        try:
            metadata = {}

            # Extract meta tags
            meta_tags = await page.query_selector_all("meta")

            for tag in meta_tags:
                name = await tag.get_attribute("name")
                property_attr = await tag.get_attribute("property")
                content = await tag.get_attribute("content")

                if content:
                    if name:
                        metadata[name] = content
                    elif property_attr:
                        metadata[property_attr] = content

            # Extract structured data
            try:
                json_ld = await page.query_selector_all(
                    'script[type="application/ld+json"]'
                )
                for script in json_ld:
                    script_content = await script.inner_text()
                    try:
                        import json

                        structured_data = json.loads(script_content)
                        metadata["structured_data"] = structured_data
                        break
                    except:
                        continue
            except:
                pass

            # Extract canonical URL
            canonical = await page.query_selector('link[rel="canonical"]')
            if canonical:
                metadata["canonical"] = await canonical.get_attribute("href")

            # Extract language
            html_element = await page.query_selector("html")
            if html_element:
                lang = await html_element.get_attribute("lang")
                if lang:
                    metadata["language"] = lang

            return metadata

        except Exception as e:
            logger.error(f"Metadata extraction failed: {e}")
            return {}

    async def health_check(self) -> Dict[str, Any]:
        """Check if Playwright is working properly."""
        if not async_playwright:
            return {
                "status": "unavailable",
                "service": "playwright",
                "error": "Playwright not installed",
            }

        try:
            # Try to launch browser briefly
            test_playwright = await async_playwright().start()
            test_browser = await test_playwright.chromium.launch(headless=True)
            await test_browser.close()
            await test_playwright.stop()

            return {
                "status": "healthy",
                "service": "playwright",
                "headless": self.headless,
            }

        except Exception as e:
            return {"status": "unhealthy", "service": "playwright", "error": str(e)}

    async def close(self):
        """Close browser and cleanup resources."""
        try:
            if self._browser:
                await self._browser.close()
                self._browser = None

            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            logger.info("Playwright resources cleaned up")

        except Exception as e:
            logger.error(f"Error closing Playwright: {e}")


# Global renderer instance
_renderer = None
_renderer_lock = asyncio.Lock()


async def get_playwright_renderer() -> PlaywrightRenderer:
    """Get a fresh Playwright renderer instance."""
    # Always create a new instance to avoid browser lifecycle issues
    return PlaywrightRenderer()

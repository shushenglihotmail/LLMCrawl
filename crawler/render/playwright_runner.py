"""
Playwright-based web rendering for JavaScript-heavy pages.
Provides fallback rendering when Firecrawl fails or for SPA content.
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from urllib.parse import urljoin, urlparse

try:
    from playwright.async_api import async_playwright, Page, Browser
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
        
        self._browser = None
        self._playwright = None
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        
        if not async_playwright:
            logger.warning("Playwright not installed - JavaScript rendering unavailable")
        
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
            try:
                await self._ensure_browser()
                
                context = await self._browser.new_context(
                    user_agent=self.user_agent,
                    viewport={"width": 1920, "height": 1080}
                )
                
                page = await context.new_page()
                
                # Set up page with reasonable defaults
                await page.set_extra_http_headers({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "keep-alive",
                })
                
                # Navigate to page
                response = await page.goto(
                    url, 
                    wait_until="domcontentloaded",
                    timeout=self.timeout
                )
                
                if not response or response.status >= 400:
                    logger.error(f"Failed to load page {url}: status {response.status if response else 'no response'}")
                    await context.close()
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
                
                await context.close()
                
                return {
                    "url": url,
                    "html": html,
                    "title": title,
                    "metadata": metadata,
                    "status_code": response.status,
                    "rendered_at": datetime.now().isoformat(),
                    "user_agent": self.user_agent
                }
                
            except Exception as e:
                logger.error(f"Playwright rendering failed for {url}: {e}")
                try:
                    await context.close()
                except:
                    pass
                return None
    
    async def render_multiple(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Render multiple URLs concurrently.
        
        Args:
            urls: List of URLs to render
            
        Returns:
            List of rendered page data
        """
        if not async_playwright:
            logger.error("Playwright not available for rendering")
            return []
            
        tasks = [self.render_page(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        documents = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Rendering failed: {result}")
            elif result:
                documents.append(result)
                
        return documents
    
    async def _ensure_browser(self):
        """Ensure browser is launched and ready."""
        if not self._browser:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-web-security",
                    "--disable-features=VizDisplayCompositor",
                    "--single-process"  # For Docker environments
                ]
            )
            logger.info("Playwright browser launched")
    
    async def _extract_metadata(self, page: Page) -> Dict[str, Any]:
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
                json_ld = await page.query_selector_all('script[type="application/ld+json"]')
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
                "error": "Playwright not installed"
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
                "headless": self.headless
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "service": "playwright",
                "error": str(e)
            }
    
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

async def get_playwright_renderer() -> PlaywrightRenderer:
    """Get or create the global Playwright renderer."""
    global _renderer
    if _renderer is None:
        _renderer = PlaywrightRenderer()
    return _renderer
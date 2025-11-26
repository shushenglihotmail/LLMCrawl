"""
FastAPI Crawler Service - Web crawling with Firecrawl, Playwright, and Trafilatura.
Provides endpoints for crawling, rendering, and extracting web content.
"""

import asyncio
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

# Import our crawler components
from .clients.firecrawl import FirecrawlClient
from .extract.trafilatura_wrap import get_trafilatura_extractor
from .render.playwright_runner import get_playwright_renderer
from .utils.robots import get_robots_checker

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CrawlRequest(BaseModel):
    """Request model for crawling."""

    query: str = Field(..., description="Search query or topic")
    seed_urls: List[str] = Field(default_factory=list, description="Optional seed URLs")
    freshness_days: int = Field(7, description="How recent content should be")
    depth: int = Field(1, description="Crawl depth")
    max_results: int = Field(10, description="Maximum number of results")
    allow_web_search: bool = Field(
        True, description="Allow crawling public internet via Firecrawl"
    )


class RenderRequest(BaseModel):
    """Request model for page rendering."""

    url: str = Field(..., description="URL to render")


class ExtractRequest(BaseModel):
    """Request model for content extraction."""

    url: str = Field(..., description="Source URL")
    html: str = Field(..., description="HTML content to extract from")


class CrawlResponse(BaseModel):
    """Response model for crawling."""

    docs: List[Dict[str, Any]] = Field(default_factory=list)
    query: str
    total_found: int
    processed: int
    duration_ms: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    logger.info("Starting Crawler service")

    # Initialize clients
    global firecrawl_client
    firecrawl_client = FirecrawlClient()

    logger.info("Crawler service started successfully")
    yield

    # Cleanup
    try:
        await firecrawl_client.close()
        renderer = await get_playwright_renderer()
        await renderer.close()
    except:
        pass

    logger.info("Crawler service shut down")


# Create FastAPI app
app = FastAPI(
    title="Web RAG Crawler",
    description="Web crawling service with Firecrawl, Playwright, and Trafilatura",
    version="1.0.0",
    lifespan=lifespan,
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global clients
firecrawl_client: Optional[FirecrawlClient] = None

# Setup Prometheus metrics
Instrumentator().instrument(app).expose(app)


def extract_links_from_html(html: str, base_url: str) -> List[str]:
    """Extract all links from HTML content."""
    links = []
    try:
        # Extract href attributes from <a> tags
        pattern = r'<a[^>]+href=["\'](.*?)["\']'
        matches = re.findall(pattern, html, re.IGNORECASE)

        base_domain = urlparse(base_url).netloc

        for match in matches:
            # Skip anchors, javascript, and mailto links
            if match.startswith(("#", "javascript:", "mailto:")):
                continue

            # Convert relative URLs to absolute
            absolute_url = urljoin(base_url, match)

            # Only include links from the same domain
            if urlparse(absolute_url).netloc == base_domain:
                links.append(absolute_url)
    except Exception as e:
        logger.error(f"Failed to extract links from HTML: {e}")

    return links


async def crawl_with_depth(
    seed_urls: List[str],
    depth: int,
    max_results: int,
    robots_checker,
    renderer,
    extractor,
    seen_urls: Set[str],
) -> List[Dict[str, Any]]:
    """
    Recursively crawl pages up to specified depth.

    Args:
        seed_urls: Starting URLs
        depth: Maximum depth to crawl (1 = seed URLs only)
        max_results: Maximum total documents to collect
        robots_checker: Robots.txt checker
        renderer: Playwright renderer
        extractor: Content extractor
        seen_urls: Set of already processed URLs

    Returns:
        List of crawled documents
    """
    documents = []
    current_level_urls = seed_urls.copy()

    for current_depth in range(depth):
        if not current_level_urls or len(documents) >= max_results:
            break

        logger.info(
            f"Crawling depth {current_depth + 1}/{depth} with {len(current_level_urls)} URLs"
        )

        # Limit URLs to crawl at this level
        urls_to_crawl = []
        for url in current_level_urls:
            if url in seen_urls:
                continue
            if len(urls_to_crawl) >= max_results - len(documents):
                break
            urls_to_crawl.append(url)
            seen_urls.add(url)

        if not urls_to_crawl:
            break

        # Render pages at current depth
        rendered_docs = await renderer.render_multiple(urls_to_crawl)

        # Collect links for next depth level
        next_level_urls = []

        for rendered_doc in rendered_docs:
            if not rendered_doc or rendered_doc.get("error"):
                continue

            # Extract content
            extraction = await extractor.extract_content(
                rendered_doc["html"], rendered_doc["url"]
            )

            if not extraction.get("error"):
                doc = {
                    "url": extraction["url"],
                    "title": extraction.get("title", ""),
                    "markdown": extraction.get("markdown", ""),
                    "published_at": extraction.get("published_at"),
                    "metadata": extraction.get("metadata", {}),
                    "fetched_at": datetime.now().isoformat(),
                    "source": "playwright+trafilatura",
                    "crawl_depth": current_depth + 1,
                }
                documents.append(doc)

                # Extract links for next depth (if not at max depth)
                if current_depth + 1 < depth and len(documents) < max_results:
                    links = extract_links_from_html(
                        rendered_doc["html"], rendered_doc["url"]
                    )
                    for link in links:
                        if link not in seen_urls:
                            next_level_urls.append(link)

        logger.info(
            f"Depth {current_depth + 1} completed: {len(rendered_docs)} documents crawled, {len(next_level_urls)} links found"
        )

        # Prepare for next depth
        current_level_urls = next_level_urls[
            : max_results * 2
        ]  # Limit to avoid explosion

    return documents


@app.post("/crawl", response_model=CrawlResponse)
async def crawl_endpoint(request: CrawlRequest, req: Request):
    """
    Main crawling endpoint that orchestrates the full pipeline.

    Pipeline:
    1. Use Firecrawl to search and crawl initial content
    2. Fall back to Playwright for JavaScript-heavy pages
    3. Extract clean text with Trafilatura
    4. Apply robots.txt filtering
    """
    start_time = datetime.now()
    request_id = req.headers.get("X-Request-ID", str(uuid.uuid4()))

    logger.info(f"Starting crawl request {request_id}: {request.query}")

    try:
        robots_checker = get_robots_checker()

        # Filter seed URLs by robots.txt
        if request.seed_urls:
            request.seed_urls = await robots_checker.filter_allowed_urls(
                request.seed_urls
            )

        # Step 1: Try Firecrawl first (only if allow_web_search=True)
        documents = []
        if firecrawl_client and request.allow_web_search:
            try:
                firecrawl_docs = await firecrawl_client.search_and_crawl(
                    query=request.query,
                    seed_urls=request.seed_urls,
                    freshness_days=request.freshness_days,
                    max_results=request.max_results,
                )
                documents.extend(firecrawl_docs)
                logger.info(f"Firecrawl found {len(firecrawl_docs)} documents")
            except Exception as e:
                logger.error(f"Firecrawl failed: {e}")
        elif not request.allow_web_search:
            logger.info(f"Skipping Firecrawl - allow_web_search=False")

        # Step 2: Playwright fallback for insufficient results or depth > 1 or seed URLs provided
        logger.info(
            f"Documents found: {len(documents)}, max_results: {request.max_results}"
        )
        threshold = max(1, request.max_results // 2)
        logger.info(f"Fallback threshold: {threshold}")

        # Use Playwright if we need more results OR if depth > 1 OR seed URLs provided
        needs_playwright = (
            len(documents) < threshold or request.depth > 1 or bool(request.seed_urls)
        )

        if needs_playwright:
            logger.info(
                f"Attempting Playwright fallback (depth={request.depth}, seed_urls={len(request.seed_urls) if request.seed_urls else 0})"
            )
            renderer = await get_playwright_renderer()
            extractor = get_trafilatura_extractor()

            # If we have seed URLs, crawl them with depth
            fallback_urls = request.seed_urls[:3] if request.seed_urls else []

            # If no seed URLs provided, use test URLs based on query content
            if not fallback_urls:
                test_urls = [
                    "https://www.bbc.com/news/technology",
                    "https://www.cnn.com/business/tech",
                    "https://news.ycombinator.com",
                    "https://www.theguardian.com/technology",
                    "https://www.npr.org/sections/technology",
                ]

                # Filter based on query content for better relevance
                query_lower = request.query.lower()
                if any(
                    term in query_lower
                    for term in [
                        "ai",
                        "artificial intelligence",
                        "machine learning",
                        "tech",
                        "technology",
                        "news",
                        "latest",
                        "today",
                        "market",
                        "developments",
                    ]
                ):
                    fallback_urls = test_urls[:3]
                    logger.info(
                        f"Using test URLs for query '{request.query}': {len(fallback_urls)} URLs"
                    )

            if fallback_urls:
                try:
                    seen_urls = set(
                        doc.get("url") for doc in documents if doc.get("url")
                    )

                    # Use depth-based crawling if depth > 1
                    if request.depth > 1:
                        depth_docs = await crawl_with_depth(
                            seed_urls=fallback_urls,
                            depth=request.depth,
                            max_results=request.max_results,
                            robots_checker=robots_checker,
                            renderer=renderer,
                            extractor=extractor,
                            seen_urls=seen_urls,
                        )
                        documents.extend(depth_docs)
                        logger.info(
                            f"Playwright depth crawl added {len(depth_docs)} documents"
                        )
                    else:
                        # Original single-level crawling
                        rendered_docs = await renderer.render_multiple(fallback_urls)

                        for rendered_doc in rendered_docs:
                            if rendered_doc and not rendered_doc.get("error"):
                                extraction = await extractor.extract_content(
                                    rendered_doc["html"], rendered_doc["url"]
                                )

                                if not extraction.get("error"):
                                    doc = {
                                        "url": extraction["url"],
                                        "title": extraction.get("title", ""),
                                        "markdown": extraction.get("markdown", ""),
                                        "published_at": extraction.get("published_at"),
                                        "metadata": extraction.get("metadata", {}),
                                        "fetched_at": datetime.now().isoformat(),
                                        "source": "playwright+trafilatura",
                                        "crawl_depth": 1,
                                    }
                                    documents.append(doc)

                        logger.info(
                            f"Playwright fallback added {len(rendered_docs)} documents"
                        )

                except Exception as e:
                    logger.error(f"Playwright fallback failed: {e}")

        # Step 3: Final robots.txt filtering and deduplication
        # Skip robots.txt filtering for authenticated sites (already successfully crawled)
        filtered_docs = []
        seen_urls = set()

        for doc in documents:
            url = doc.get("url", "")
            if not url or url in seen_urls:
                continue

            # If document was successfully crawled with Playwright+auth, trust it
            # Otherwise, check robots.txt
            if doc.get(
                "source"
            ) == "playwright+trafilatura" or await robots_checker.can_crawl(url):
                filtered_docs.append(doc)
                seen_urls.add(url)

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        logger.info(
            f"Crawl completed {request_id}: {len(filtered_docs)} documents in {duration_ms:.1f}ms"
        )

        return CrawlResponse(
            docs=filtered_docs,
            query=request.query,
            total_found=len(documents),
            processed=len(filtered_docs),
            duration_ms=duration_ms,
        )

    except Exception as e:
        logger.error(f"Crawl request failed {request_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Crawling failed: {e}")


@app.post("/render")
async def render_endpoint(request: RenderRequest):
    """Render a single page with Playwright."""
    try:
        robots_checker = get_robots_checker()

        if not await robots_checker.can_crawl(request.url):
            raise HTTPException(
                status_code=403, detail="Crawling blocked by robots.txt"
            )

        renderer = await get_playwright_renderer()
        result = await renderer.render_page(request.url)

        if not result:
            raise HTTPException(status_code=400, detail="Failed to render page")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rendering failed for {request.url}: {e}")
        raise HTTPException(status_code=500, detail=f"Rendering failed: {e}")


@app.post("/extract")
async def extract_endpoint(request: ExtractRequest):
    """Extract clean text from HTML content."""
    try:
        extractor = get_trafilatura_extractor()
        result = await extractor.extract_content(request.html, request.url)

        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Extraction failed for {request.url}: {e}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Check all components
        health_status = {
            "status": "healthy",
            "service": "crawler",
            "timestamp": datetime.now().isoformat(),
            "components": {},
        }

        # Check Firecrawl
        if firecrawl_client:
            health_status["components"][
                "firecrawl"
            ] = await firecrawl_client.health_check()
        else:
            health_status["components"]["firecrawl"] = {"status": "not_initialized"}

        # Check Playwright
        renderer = await get_playwright_renderer()
        health_status["components"]["playwright"] = await renderer.health_check()

        # Check Trafilatura
        extractor = get_trafilatura_extractor()
        health_status["components"]["trafilatura"] = await extractor.health_check()

        # Check Robots checker
        robots_checker = get_robots_checker()
        health_status["components"]["robots"] = await robots_checker.health_check()

        # Determine overall health
        unhealthy_components = [
            name
            for name, status in health_status["components"].items()
            if status.get("status") not in ["healthy", "not_initialized"]
        ]

        if unhealthy_components:
            health_status["status"] = "degraded"
            health_status["unhealthy_components"] = unhealthy_components

        return health_status

    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "crawler",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@app.get("/auth/status")
async def auth_status():
    """Check authentication status for configured sites."""
    import httpx

    auth_type = os.getenv("FIRECRAWL_AUTH_TYPE", "none")

    if auth_type == "none":
        return {"status": "disabled", "message": "Authentication not configured"}

    # Test a known authenticated URL if configured
    test_url = os.getenv("AUTH_TEST_URL")
    if not test_url:
        return {
            "status": "configured",
            "auth_type": auth_type,
            "message": "Authentication configured but no test URL set (AUTH_TEST_URL)",
        }

    try:
        # Get auth config
        auth_config = await firecrawl_client._get_auth_config()

        # Test the URL
        async with httpx.AsyncClient() as client:
            response = await client.get(
                test_url,
                cookies=auth_config.get("cookies", {}),
                headers={
                    **auth_config.get("headers", {}),
                    "User-Agent": "WebRAG/1.0 Auth-Check",
                },
                timeout=10.0,
                follow_redirects=True,
            )

            if response.status_code == 200:
                # Check for login indicators
                content = response.text.lower()
                if "sign in" in content or "login" in content:
                    return {
                        "status": "expired",
                        "auth_type": auth_type,
                        "test_url": test_url,
                        "message": "Authentication appears to be expired (login page detected)",
                        "action_required": "Run: python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page",
                    }
                else:
                    return {
                        "status": "valid",
                        "auth_type": auth_type,
                        "test_url": test_url,
                        "message": "Authentication is valid",
                    }
            elif response.status_code == 401:
                return {
                    "status": "expired",
                    "auth_type": auth_type,
                    "test_url": test_url,
                    "status_code": 401,
                    "message": "Authentication expired (401 Unauthorized)",
                    "action_required": "Run: python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page",
                }
            else:
                return {
                    "status": "unknown",
                    "auth_type": auth_type,
                    "test_url": test_url,
                    "status_code": response.status_code,
                    "message": f"Unexpected status code: {response.status_code}",
                }

    except Exception as e:
        return {
            "status": "error",
            "auth_type": auth_type,
            "error": str(e),
            "message": "Failed to check authentication status",
        }


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "web-rag-crawler",
        "version": "1.0.0",
        "description": "Web crawling service with Firecrawl, Playwright, and Trafilatura",
        "endpoints": {
            "crawl": "/crawl",
            "render": "/render",
            "extract": "/extract",
            "health": "/health",
            "auth_status": "/auth/status",
            "docs": "/docs",
        },
    }


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("CRAWLER_HOST", "0.0.0.0")
    port = int(os.getenv("CRAWLER_PORT", 8001))

    uvicorn.run("main:app", host=host, port=port, reload=True, log_level="info")

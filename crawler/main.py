"""
FastAPI Crawler Service - Web crawling with Firecrawl, Playwright, and Trafilatura.
Provides endpoints for crawling, rendering, and extracting web content.
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

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

        # Step 1: Try Firecrawl first
        documents = []
        if firecrawl_client:
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

        # Step 2: Playwright fallback for insufficient results
        logger.info(
            f"Documents found: {len(documents)}, max_results: {request.max_results}"
        )
        threshold = max(1, request.max_results // 2)
        logger.info(f"Fallback threshold: {threshold}")

        if len(documents) < threshold:
            logger.info("Attempting Playwright fallback")
            renderer = await get_playwright_renderer()

            # If we have seed URLs, try rendering them
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
                    rendered_docs = await renderer.render_multiple(fallback_urls)

                    # Extract content from rendered pages
                    extractor = get_trafilatura_extractor()
                    for rendered_doc in rendered_docs:
                        if rendered_doc and not rendered_doc.get("error"):
                            extraction = await extractor.extract_content(
                                rendered_doc["html"], rendered_doc["url"]
                            )

                            if not extraction.get("error"):
                                # Convert to standard format
                                doc = {
                                    "url": extraction["url"],
                                    "title": extraction.get("title", ""),
                                    "markdown": extraction.get("markdown", ""),
                                    "published_at": extraction.get("published_at"),
                                    "metadata": extraction.get("metadata", {}),
                                    "fetched_at": datetime.now().isoformat(),
                                    "source": "playwright+trafilatura",
                                }
                                documents.append(doc)

                    logger.info(
                        f"Playwright fallback added {len(rendered_docs)} documents"
                    )

                except Exception as e:
                    logger.error(f"Playwright fallback failed: {e}")

        # Step 3: Final robots.txt filtering and deduplication
        filtered_docs = []
        seen_urls = set()

        for doc in documents:
            url = doc.get("url", "")
            if not url or url in seen_urls:
                continue

            if await robots_checker.can_crawl(url):
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
            "docs": "/docs",
        },
    }


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("CRAWLER_HOST", "0.0.0.0")
    port = int(os.getenv("CRAWLER_PORT", 8001))

    uvicorn.run("main:app", host=host, port=port, reload=True, log_level="info")

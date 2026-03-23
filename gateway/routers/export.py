"""
Export router for downloading crawled content as markdown files.
Allows users to export web page content for offline use or manual LLM feeding.
"""

import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Directory to store temporary markdown exports
EXPORT_DIR = os.getenv("EXPORT_DIR", "/tmp/llmcrawl_exports")
os.makedirs(EXPORT_DIR, exist_ok=True)


class ExportRequest(BaseModel):
    """Request model for exporting crawled content as markdown."""

    seed_urls: List[str] = Field(
        ..., description="Seed URLs to crawl and export (required)"
    )
    depth: int = Field(1, description="Crawl depth for seed URLs", ge=1, le=5)
    freshness_days: int = Field(
        30, description="Only include content from the last N days"
    )


class ExportResponse(BaseModel):
    """Response model for export requests."""

    export_id: str = Field(..., description="Unique ID for this export")
    download_url: str = Field(..., description="URL to download the markdown file")
    pages_exported: int = Field(..., description="Number of pages exported")
    file_size_kb: int = Field(..., description="Size of exported file in KB")
    created_at: str = Field(..., description="Timestamp of export creation")


@router.post("/export/markdown", response_model=ExportResponse)
async def export_to_markdown(request: ExportRequest):
    """
    Export crawled web pages as a single markdown file.

    This endpoint crawls the specified seed URLs, extracts content,
    and combines them into a single downloadable markdown file.

    Args:
        request: ExportRequest with seed_urls, depth, and freshness_days

    Returns:
        ExportResponse with download URL and metadata

    Raises:
        HTTPException: If seed_urls is empty or crawling fails
    """
    if not request.seed_urls:
        raise HTTPException(
            status_code=400,
            detail="seed_urls is required. Please provide at least one URL to crawl.",
        )

    logger.info(
        f"Export request: {len(request.seed_urls)} seed URLs, depth={request.depth}"
    )

    try:
        # Import crawler client
        import httpx

        crawler_url = os.getenv("CRAWLER_URL", "http://crawler:8001")

        # Call crawler service
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{crawler_url}/crawl",
                json={
                    "urls": request.seed_urls,
                    "depth": request.depth,
                    "max_results": 100,  # Allow more results for export
                },
            )
            response.raise_for_status()
            crawl_result = response.json()

        docs = crawl_result.get("docs", [])
        if not docs:
            raise HTTPException(
                status_code=404,
                detail="No content found at the specified URLs. "
                "Please check if the URLs are accessible.",
            )

        # Generate export ID and filename
        export_id = str(uuid.uuid4())[:8]
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"crawl_export_{timestamp}_{export_id}.md"
        filepath = os.path.join(EXPORT_DIR, filename)

        # Build combined markdown content
        markdown_content = _build_export_markdown(docs, request.seed_urls)

        # Write to file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        # Get file size
        file_size_kb = os.path.getsize(filepath) // 1024

        logger.info(
            f"Export complete: {len(docs)} pages, {file_size_kb}KB, file: {filename}"
        )

        return ExportResponse(
            export_id=export_id,
            download_url=f"/api/v1/export/download/{filename}",
            pages_exported=len(docs),
            file_size_kb=file_size_kb,
            created_at=datetime.utcnow().isoformat(),
        )

    except httpx.HTTPError as e:
        logger.error(f"Crawler service error: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to crawl URLs: {str(e)}")
    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/export/download/{filename}")
async def download_export(filename: str):
    """
    Download an exported markdown file.

    Args:
        filename: Name of the exported file

    Returns:
        FileResponse with the markdown file

    Raises:
        HTTPException: If file not found or invalid filename
    """
    # Validate filename (security check)
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = os.path.join(EXPORT_DIR, filename)

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Export file not found")

    logger.info(f"Downloading export: {filename}")

    return FileResponse(
        path=filepath,
        media_type="text/markdown",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_export_markdown(docs: List[dict], seed_urls: List[str]) -> str:
    """
    Build a combined markdown document from crawled pages.

    Args:
        docs: List of crawled documents with url, title, markdown, etc.
        seed_urls: Original seed URLs for the crawl

    Returns:
        Combined markdown string
    """
    lines = []

    # Header
    lines.append("# Crawled Web Content Export")
    lines.append("")
    lines.append(
        f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    lines.append(f"**Pages Exported:** {len(docs)}")
    lines.append("")
    lines.append("## Seed URLs")
    lines.append("")
    for url in seed_urls:
        lines.append(f"- {url}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Table of Contents
    lines.append("## Table of Contents")
    lines.append("")
    for i, doc in enumerate(docs, 1):
        title = doc.get("title", "Untitled")
        url = doc.get("url", "")
        lines.append(f"{i}. [{title}]({url})")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Content sections
    for i, doc in enumerate(docs, 1):
        title = doc.get("title", "Untitled")
        url = doc.get("url", "")
        published_at = doc.get("published_at", "Unknown date")
        markdown = doc.get("markdown", "")

        lines.append(f"## {i}. {title}")
        lines.append("")
        lines.append(f"**URL:** {url}")
        lines.append(f"**Published:** {published_at}")
        lines.append("")
        lines.append(markdown.strip())
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)

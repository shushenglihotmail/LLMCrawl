"""
File download router - serves files from the in-memory file store.

Provides:
- GET /files/{file_id} - Download a stored file
- GET /files/{file_id}/info - Get file metadata without content
"""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..utils.file_store import get_file_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/{file_id}")
async def download_file(file_id: str) -> Response:
    """
    Download a stored file by ID.

    Returns the file content with appropriate Content-Type and
    Content-Disposition headers for browser download.
    """
    store = get_file_store()
    stored = store.get(file_id)

    if stored is None:
        raise HTTPException(
            status_code=404,
            detail="File not found or expired. Files are available for 30 minutes after creation.",
        )

    logger.info(f"Serving file download: {stored.filename} ({stored.size} bytes)")

    return Response(
        content=stored.content,
        media_type=stored.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{stored.filename}"',
            "Content-Length": str(stored.size),
        },
    )


@router.get("/{file_id}/info")
async def get_file_info(file_id: str) -> dict:
    """Get metadata about a stored file without downloading it."""
    store = get_file_store()
    stored = store.get(file_id)

    if stored is None:
        raise HTTPException(
            status_code=404,
            detail="File not found or expired.",
        )

    return {
        "file_id": stored.file_id,
        "filename": stored.filename,
        "size": stored.size,
        "content_type": stored.content_type,
    }

"""
In-memory file store for LLM-generated downloads.

Stores file content temporarily (with TTL) so the LLM can offer files
for download via the HiChat UI without needing filesystem access.

Flow:
1. LLM calls save_file_for_download tool → content stored here with UUID key
2. Gateway returns file metadata in response JSON
3. HiChat renders download button
4. User clicks → GET /api/files/{file_id} → content served from memory
5. Files auto-expire after TTL (default 30 minutes)
"""

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Default TTL: 4 hours (30 min was too aggressive for slow LLM round-trips)
DEFAULT_TTL_SECONDS = 4 * 60 * 60

# Max file size: 10 MB
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

# Max stored files (prevent memory exhaustion)
MAX_STORED_FILES = 200


@dataclass
class StoredFile:
    """A file stored in memory."""

    file_id: str
    filename: str
    content: str
    content_type: str
    size: int
    created_at: float = field(default_factory=time.time)
    # Which conversation produced this file
    conversation_id: Optional[str] = None


class FileStore:
    """Thread-safe in-memory file store with TTL expiration."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._files: Dict[str, StoredFile] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def store(
        self,
        filename: str,
        content: str,
        content_type: str = "text/plain",
        conversation_id: Optional[str] = None,
    ) -> StoredFile:
        """
        Store file content and return metadata.

        Args:
            filename: Original filename (e.g., "easyBMT.ps1")
            content: File content as string
            content_type: MIME type (default: text/plain)
            conversation_id: Optional conversation ID for tracking

        Returns:
            StoredFile with generated file_id

        Raises:
            ValueError: If content exceeds max size or store is full
        """
        size = len(content.encode("utf-8"))
        if size > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"File too large ({size} bytes). "
                f"Maximum size is {MAX_FILE_SIZE_BYTES} bytes."
            )

        # Clean up expired files first
        self._cleanup_expired()

        with self._lock:
            if len(self._files) >= MAX_STORED_FILES:
                # Evict oldest file
                oldest_id = min(self._files, key=lambda k: self._files[k].created_at)
                del self._files[oldest_id]
                logger.info(f"Evicted oldest file {oldest_id} to make room")

            file_id = str(uuid.uuid4())
            stored = StoredFile(
                file_id=file_id,
                filename=filename,
                content=content,
                content_type=content_type,
                size=size,
                conversation_id=conversation_id,
            )
            self._files[file_id] = stored
            logger.info(f"Stored file '{filename}' ({size} bytes) as {file_id}")
            return stored

    def get(self, file_id: str) -> Optional[StoredFile]:
        """
        Retrieve a stored file by ID.

        Returns None if not found or expired.
        """
        with self._lock:
            stored = self._files.get(file_id)
            if stored is None:
                return None

            # Check TTL
            if time.time() - stored.created_at > self._ttl:
                del self._files[file_id]
                logger.info(f"File {file_id} expired (TTL exceeded)")
                return None

            return stored

    def get_files_for_conversation(self, conversation_id: str) -> list[StoredFile]:
        """Get all non-expired files for a conversation."""
        self._cleanup_expired()
        with self._lock:
            return [
                f for f in self._files.values() if f.conversation_id == conversation_id
            ]

    def _cleanup_expired(self) -> None:
        """Remove expired files."""
        now = time.time()
        with self._lock:
            expired = [
                fid for fid, f in self._files.items() if now - f.created_at > self._ttl
            ]
            for fid in expired:
                del self._files[fid]
            if expired:
                logger.info(f"Cleaned up {len(expired)} expired files")

    @property
    def count(self) -> int:
        """Number of stored files (including potentially expired)."""
        return len(self._files)


# Singleton instance
_file_store: Optional[FileStore] = None


def get_file_store() -> FileStore:
    """Get or create the global file store instance."""
    global _file_store
    if _file_store is None:
        _file_store = FileStore()
    return _file_store

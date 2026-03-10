"""
Memory Service - FastAPI HTTP wrapper around memsearch library.

Provides OpenClaw-style auto-memory with HTTP endpoints for cross-language access.
Uses memsearch for markdown-first memory with semantic search.

All operations via HTTP REST API - no direct filesystem access needed by clients.
memsearch.watch() auto-indexes file changes in background.

Endpoints:
    GET  /health        - Health check
    POST /write_daily   - Write to daily log (auto-indexes)
    POST /write_memory  - Write to MEMORY.md
    POST /search        - Semantic search memories
    GET  /context       - Get context for conversation start
    POST /reindex       - Rebuild index from markdown
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import tiktoken
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from memsearch import MemSearch
from pydantic import BaseModel, Field

from . import __version__
from .client import MemoryClient

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration
MEMORY_DATA_PATH = Path(os.getenv("MEMORY_DATA_PATH", "/data/memory"))
EMBEDDING_PROVIDER = os.getenv(
    "EMBEDDING_PROVIDER", "local"
)  # local = sentence-transformers
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", None)  # None uses default for provider
# Use relative path for Milvus Lite (pymilvus 2.5+ requires this format)
MILVUS_URI = os.getenv("MILVUS_URI", "./milvus.db")

# Global memsearch instance and watcher
_mem: Optional[MemSearch] = None
_watcher = None  # FileWatcher from memsearch
_encoding = tiktoken.get_encoding("cl100k_base")


# --- Pydantic Models ---


class SearchRequest(BaseModel):
    """Request to search memories."""

    query: str = Field(..., description="Search query")
    limit: int = Field(5, ge=1, le=50, description="Maximum results to return")


class SearchResult(BaseModel):
    """A single search result."""

    content: str
    source: str
    heading: Optional[str] = None
    score: float


class SearchResponse(BaseModel):
    """Response from memory search."""

    results: List[SearchResult]
    query: str


class WriteMemoryRequest(BaseModel):
    """Request to write to MEMORY.md."""

    content: str = Field(..., description="Content to write/append")
    section: Optional[str] = Field(None, description="Section header")
    replace: bool = Field(False, description="If True, replace entire file")


class WriteMemoryResponse(BaseModel):
    """Response from write memory."""

    success: bool
    file_path: str
    message: str


class WriteDailyRequest(BaseModel):
    """Request to write to daily log."""

    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    session_id: Optional[str] = Field(
        None, description="Session/conversation ID for grouping messages"
    )


class WriteDailyResponse(BaseModel):
    """Response from write daily."""

    success: bool
    file_path: str
    message: str


class ContextResponse(BaseModel):
    """Response with relevant context."""

    context: str
    sources: List[str]
    token_count: int


class ReindexResponse(BaseModel):
    """Response from reindex."""

    success: bool
    chunks_indexed: int
    message: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str = "memory-service"
    version: str = __version__
    memory_file_exists: bool
    daily_log_count: int
    watcher_running: bool = False


# --- Helper Functions ---


def ensure_directories():
    """Ensure memory directories exist."""
    MEMORY_DATA_PATH.mkdir(parents=True, exist_ok=True)
    (MEMORY_DATA_PATH / "daily").mkdir(parents=True, exist_ok=True)


def get_daily_log_path(date_str: str) -> Path:
    """Get path to daily log file."""
    return MEMORY_DATA_PATH / "daily" / f"{date_str}.md"


def get_memory_md_path() -> Path:
    """Get path to MEMORY.md."""
    return MEMORY_DATA_PATH / "MEMORY.md"


def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken."""
    try:
        return len(_encoding.encode(text))
    except Exception:
        return len(text) // 4


def count_daily_logs() -> int:
    """Count daily log files."""
    daily_dir = MEMORY_DATA_PATH / "daily"
    if not daily_dir.exists():
        return 0
    return len(list(daily_dir.glob("*.md")))


# Fallback mode flag (when memsearch/Milvus not available)
_fallback_mode = False


# --- Lifespan ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize memsearch on startup, cleanup on shutdown."""
    global _mem, _watcher, _fallback_mode

    logger.info("Starting Memory Service...")
    ensure_directories()

    # Try to initialize memsearch with local embeddings
    logger.info(f"Initializing memsearch with path: {MEMORY_DATA_PATH}")
    logger.info(f"Embedding provider: {EMBEDDING_PROVIDER}")
    logger.info(f"Milvus URI: {MILVUS_URI}")

    try:
        _mem = MemSearch(
            paths=[str(MEMORY_DATA_PATH)],
            embedding_provider=EMBEDDING_PROVIDER,
            embedding_model=EMBEDDING_MODEL,
            milvus_uri=MILVUS_URI,
            collection="llmcrawl_memory",
        )

        # Initial index
        try:
            chunk_count = await _mem.index()
            logger.info(f"Indexed {chunk_count} chunks from memory files")
        except Exception as e:
            logger.warning(f"Initial indexing skipped (may be empty): {e}")

        # Start file watcher for auto-indexing
        try:

            def on_file_change(event_type: str, summary: str, path: str):
                logger.info(f"File change detected: {event_type} - {path}")

            _watcher = _mem.watch(
                on_event=on_file_change,
                debounce_ms=1500,
            )
            logger.info("File watcher started (auto-indexing enabled)")
        except Exception as e:
            logger.warning(f"File watcher not started: {e}")
            _watcher = None

        logger.info("Memory Service ready (full mode with semantic search)")

    except Exception as e:
        # Fallback mode - basic file operations without semantic search
        logger.warning(f"memsearch initialization failed: {e}")
        logger.warning(
            "Running in FALLBACK MODE - no semantic search, basic file operations only"
        )
        _fallback_mode = True
        _mem = None
        _watcher = None
        logger.info("Memory Service ready (fallback mode)")

    yield

    # Cleanup
    logger.info("Shutting down Memory Service...")
    if _watcher:
        try:
            _watcher.stop()
            logger.info("File watcher stopped")
        except Exception as e:
            logger.warning(f"Error stopping watcher: {e}")
    if _mem:
        try:
            _mem.close()
        except Exception:
            pass


# --- FastAPI App ---

app = FastAPI(
    title="Memory Service",
    description="OpenClaw-style auto-memory with memsearch",
    version=__version__,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    status = "healthy" if not _fallback_mode else "healthy (fallback mode)"
    return HealthResponse(
        status=status,
        memory_file_exists=get_memory_md_path().exists(),
        daily_log_count=count_daily_logs(),
        watcher_running=_watcher is not None,
    )


@app.post("/write_daily", response_model=WriteDailyResponse)
async def write_daily(request: WriteDailyRequest):
    """
    Write a message to today's daily log.

    Apps call this to log conversation messages. The file is auto-indexed
    by memsearch.watch() for semantic search.

    Messages are grouped by session_id. When a new session_id is seen,
    a session header is written to separate conversation sessions.

    Args:
        request: Contains role (user/assistant), content, and optional session_id
    """
    try:
        client = MemoryClient(str(MEMORY_DATA_PATH))
        file_path = client.append_to_daily_log(
            role=request.role,
            content=request.content,
            session_id=request.session_id,
        )
        today = datetime.now().strftime("%Y-%m-%d")
        logger.info(
            f"Wrote {request.role} message to daily log: {today} (session: {request.session_id})"
        )

        return WriteDailyResponse(
            success=True,
            file_path=file_path,
            message=f"Appended {request.role} message to daily log",
        )

    except Exception as e:
        logger.error(f"Failed to write daily log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search", response_model=SearchResponse)
async def search_memories(request: SearchRequest):
    """
    Search memories using semantic search.

    Called by LLM via memory_search tool.
    In fallback mode, returns empty results (semantic search unavailable).
    """
    if _fallback_mode:
        # Fallback: return empty results with a note
        logger.info(f"Search in fallback mode (no semantic search): {request.query}")
        return SearchResponse(
            results=[],
            query=request.query,
        )

    if not _mem:
        raise HTTPException(status_code=503, detail="Memory service not initialized")

    try:
        results = await _mem.search(request.query, top_k=request.limit)

        return SearchResponse(
            results=[
                SearchResult(
                    content=r.get("content", ""),
                    source=r.get("source", ""),
                    heading=r.get("heading"),
                    score=r.get("score", 0.0),
                )
                for r in results
            ],
            query=request.query,
        )

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/write_memory", response_model=WriteMemoryResponse)
async def write_memory(request: WriteMemoryRequest):
    """
    Write to MEMORY.md file.

    Called when LLM writes a summary in response to flush prompt.
    """
    try:
        memory_path = get_memory_md_path()

        if request.replace:
            content = request.content
        else:
            existing = ""
            if memory_path.exists():
                existing = memory_path.read_text(encoding="utf-8")

            if request.section:
                content = f"{existing}\n\n## {request.section}\n{request.content}"
            else:
                content = f"{existing}\n\n{request.content}"

        memory_path.write_text(content.strip() + "\n", encoding="utf-8")

        # Re-index
        if _mem:
            try:
                await _mem.index_file(memory_path)
            except Exception as e:
                logger.warning(f"Failed to index MEMORY.md: {e}")

        return WriteMemoryResponse(
            success=True,
            file_path=str(memory_path),
            message=f"Written {len(request.content)} chars to MEMORY.md",
        )

    except Exception as e:
        logger.error(f"Failed to write memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/context", response_model=ContextResponse)
async def get_context(
    query: Optional[str] = None,
    max_tokens: int = 2000,
):
    """
    Get relevant memory context for conversation start.

    If query is provided, returns semantically relevant memories.
    Otherwise, returns recent memories and MEMORY.md content.
    In fallback mode, only returns MEMORY.md content (no semantic search).
    """
    try:
        context_parts = []
        sources = []

        # Always include MEMORY.md if it exists
        memory_path = get_memory_md_path()
        if memory_path.exists():
            memory_content = memory_path.read_text(encoding="utf-8")
            if memory_content.strip():
                # Truncate if too long
                mem_tokens = count_tokens(memory_content)
                if mem_tokens > max_tokens // 2:
                    target_chars = (max_tokens // 2) * 4
                    memory_content = (
                        memory_content[:target_chars] + "\n\n[...truncated...]"
                    )

                context_parts.append(f"## Long-term Memory\n\n{memory_content}")
                sources.append("MEMORY.md")

        # If query provided and not in fallback mode, do semantic search
        if query and _mem and not _fallback_mode:
            results = await _mem.search(query, top_k=10)
            relevant_parts = []
            for r in results:
                content = r.get("content", "")
                source = r.get("source", "")
                if content and source not in sources:
                    relevant_parts.append(f"[From {source}]\n{content[:500]}")
                    sources.append(source)

            if relevant_parts:
                context_parts.append(
                    "## Relevant Memories\n\n" + "\n\n".join(relevant_parts[:5])
                )

        # Combine and truncate to max_tokens
        context = "\n\n---\n\n".join(context_parts)
        token_count = count_tokens(context)

        # Truncate if needed
        while token_count > max_tokens and len(context) > 100:
            context = context[: int(len(context) * 0.9)]
            token_count = count_tokens(context)

        return ContextResponse(
            context=context,
            sources=sources,
            token_count=token_count,
        )

    except Exception as e:
        logger.error(f"Failed to get context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reindex", response_model=ReindexResponse)
async def reindex(force: bool = False):
    """
    Rebuild the vector index from markdown files.

    Use force=True to re-embed all chunks even if unchanged.
    In fallback mode, returns success with 0 chunks (no indexing available).
    """
    if _fallback_mode:
        return ReindexResponse(
            success=True,
            chunks_indexed=0,
            message="Fallback mode - no indexing available",
        )

    if not _mem:
        raise HTTPException(status_code=503, detail="Memory service not initialized")

    try:
        chunk_count = await _mem.index(force=force)

        return ReindexResponse(
            success=True,
            chunks_indexed=chunk_count,
            message=f"Indexed {chunk_count} chunks",
        )

    except Exception as e:
        logger.error(f"Reindex failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Main ---

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8007")),
        reload=os.getenv("ENVIRONMENT", "development") == "development",
    )

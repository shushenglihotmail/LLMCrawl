"""
FastAPI Indexer Service - Document indexing and retrieval with LlamaIndex.
Provides endpoints for indexing documents and retrieving relevant results.
"""

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

from .adapters.llamaindex_store import get_llamaindex_store
from .utils.metrics import record_service_error, set_service_up

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IndexRequest(BaseModel):
    """Request model for indexing documents."""

    docs: List[Dict[str, Any]] = Field(..., description="Documents to index")


class RetrieveRequest(BaseModel):
    """Request model for retrieving documents."""

    query: str = Field(..., description="Search query")
    k: int = Field(8, description="Number of results to return")
    recency_boost_days: int = Field(14, description="Days for recency boosting")
    score_threshold: float = Field(0.1, description="Minimum similarity score")


class IndexResponse(BaseModel):
    """Response model for indexing."""

    indexed: int
    chunks: int = 0
    documents: int
    vector_db: str
    duration_ms: float


class RetrieveResponse(BaseModel):
    """Response model for retrieval."""

    hits: List[Dict[str, Any]]
    total_found: int
    query: str
    duration_ms: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    logger.info("Starting Indexer service")

    # Initialize the store
    vector_db = os.getenv("VECTOR_DB", "qdrant")
    global store
    try:
        store = await get_llamaindex_store(vector_db)
        set_service_up(True)
        logger.info(f"Indexer service started with {vector_db} backend")
        yield
    except Exception as e:
        record_service_error(e)
        raise
    finally:
        # Mark service as down on shutdown
        set_service_up(False)
        # Cleanup
        try:
            await store.close()
        except:
            pass
        logger.info("Indexer service shut down")


from .utils.token_context import set_token

# Create FastAPI app
app = FastAPI(
    title="Web RAG Indexer",
    description="Document indexing and retrieval service with LlamaIndex",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Extract Bearer token from Authorization header and set in context."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        set_token(token)
    else:
        logger.warning("No Bearer token found in Authorization header")

    response = await call_next(request)
    return response


# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global store instance
store = None

# Setup Prometheus metrics
Instrumentator().instrument(app).expose(app)


@app.post("/index", response_model=IndexResponse)
async def index_endpoint(request: IndexRequest, req: Request):
    """
    Index a list of documents with chunking and embedding.

    Documents should have the following structure:
    - url: Document URL
    - title: Document title (optional)
    - markdown: Main text content
    - published_at: Publication date (optional)
    - metadata: Additional metadata (optional)
    """
    start_time = datetime.now()
    request_id = req.headers.get("X-Request-ID", str(uuid.uuid4()))

    logger.info(f"Starting index request {request_id}: {len(request.docs)} documents")

    try:
        if not store:
            raise HTTPException(
                status_code=503, detail="Indexing service not initialized"
            )

        # Index the documents
        result = await store.index_documents(request.docs)

        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        logger.info(
            f"Index completed {request_id}: {result['indexed']} chunks indexed in {duration_ms:.1f}ms"
        )

        return IndexResponse(
            indexed=result["indexed"],
            chunks=result.get("chunks", 0),
            documents=result["documents"],
            vector_db=result["vector_db"],
            duration_ms=duration_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Index request failed {request_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {e}")


@app.post("/retrieve", response_model=RetrieveResponse)
async def retrieve_endpoint(request: RetrieveRequest, req: Request):
    """
    Retrieve relevant documents with semantic search and recency boosting.

    Returns documents ranked by similarity score with recency boosting applied.
    More recent documents get higher scores within the boost window.
    """
    start_time = datetime.now()
    request_id = req.headers.get("X-Request-ID", str(uuid.uuid4()))

    logger.info(f"Starting retrieve request {request_id}: '{request.query}'")

    try:
        if not store:
            raise HTTPException(
                status_code=503, detail="Indexing service not initialized"
            )

        # Retrieve documents
        result = await store.retrieve_documents(
            query=request.query,
            k=request.k,
            recency_boost_days=request.recency_boost_days,
            score_threshold=request.score_threshold,
        )

        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        logger.info(
            f"Retrieve completed {request_id}: {len(result['hits'])} hits in {duration_ms:.1f}ms"
        )

        return RetrieveResponse(
            hits=result["hits"],
            total_found=result["total_found"],
            query=request.query,
            duration_ms=duration_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Retrieve request failed {request_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {e}")


@app.get("/collection/info")
async def collection_info():
    """Get information about the document collection."""
    try:
        if not store:
            raise HTTPException(
                status_code=503, detail="Indexing service not initialized"
            )

        info = await store.vector_store.get_collection_info()
        return info

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Collection info request failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get collection info: {e}"
        )


@app.delete("/documents")
async def delete_documents(filter_conditions: Dict[str, Any]):
    """Delete documents matching filter conditions."""
    try:
        if not store:
            raise HTTPException(
                status_code=503, detail="Indexing service not initialized"
            )

        deleted_count = await store.vector_store.delete_documents(filter_conditions)

        return {"deleted": deleted_count, "filter_conditions": filter_conditions}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete request failed: {e}")
        raise HTTPException(status_code=500, detail=f"Deletion failed: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        if store:
            health = await store.health_check()
        else:
            health = {
                "status": "unhealthy",
                "service": "indexer",
                "error": "Store not initialized",
            }

        health["timestamp"] = datetime.now().isoformat()
        return health

    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "indexer",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "web-rag-indexer",
        "version": "1.0.0",
        "description": "Document indexing and retrieval service with LlamaIndex",
        "vector_db": os.getenv("VECTOR_DB", "qdrant"),
        "endpoints": {
            "index": "/index",
            "retrieve": "/retrieve",
            "collection_info": "/collection/info",
            "delete_documents": "/documents",
            "health": "/health",
            "docs": "/docs",
        },
    }


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("INDEXER_HOST", "0.0.0.0")
    port = int(os.getenv("INDEXER_PORT", 8002))

    uvicorn.run("main:app", host=host, port=port, reload=True, log_level="info")

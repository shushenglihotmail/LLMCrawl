"""
FastAPI Gateway Service - Main orchestrator for the Web RAG system.
Handles chat interactions, tool calling, and coordinates with crawler/indexer services.
"""

import os  # noqa: E402

# Strip NODE_OPTIONS early — it can break Node.js-based CLI subprocesses
# (e.g. Copilot, Claude) with errors like "unknown option '--no-warnings'".
os.environ.pop("NODE_OPTIONS", None)

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from .routers import agent, export, models
from .utils.claude_bridge_manager import get_claude_bridge_manager
from .utils.copilot_bridge_manager import get_copilot_bridge_manager
from .utils.logging import get_logger, setup_logging
from .utils.metrics import record_service_error, set_service_up
from .utils.token_context import set_token

# Setup logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    logger.info("Starting Gateway service")

    # Startup
    try:
        # Mark service as up
        set_service_up("gateway", True)

        # Probe Claude CLI/Bridge and cache available models.
        bridge_mgr = get_claude_bridge_manager()
        await bridge_mgr.probe_and_discover(max_retries=3, retry_delay=2.0)

        # Probe Copilot CLI/Bridge and cache available models.
        copilot_mgr = get_copilot_bridge_manager()
        await copilot_mgr.probe_and_discover(max_retries=2, retry_delay=1.0)

        logger.info("Gateway service started successfully")
        yield
    except Exception as e:
        record_service_error("gateway", e)
        raise
    finally:
        # Mark service as down on shutdown
        set_service_up("gateway", False)
        logger.info("Shutting down Gateway service")


# Create FastAPI app
app = FastAPI(
    title="Web RAG Gateway",
    description="Gateway service for web crawling and RAG-based question answering",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Middleware to extract Bearer token and set it in context."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        set_token(token)

    response = await call_next(request)
    return response


# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["*"]  # Configure appropriately for production
)

# Include routers
app.include_router(export.router, prefix="/api/v1")  # Export endpoints
app.include_router(agent.router)  # Agent router has its own /agent prefix
app.include_router(models.router, prefix="/api")  # Models endpoint
# File download endpoint removed — files are now saved directly to disk

# Setup Prometheus metrics
Instrumentator().instrument(app).expose(app)


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "web-rag-gateway",
        "version": "1.0.0",
        "description": "Gateway service for web crawling and RAG-based question answering",
        "endpoints": {
            "agent": "/agent/chat",
            "export": "/api/v1/export/markdown",
            "download": "/api/v1/export/download/{filename}",
            "view_file": "/api/view-file?path=...",
            "health": "/health",
            "docs": "/docs",
        },
    }


@app.get("/health")
async def health():
    """Service health check."""
    return {"status": "healthy", "service": "gateway"}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("GATEWAY_HOST", "0.0.0.0")
    port = int(os.getenv("GATEWAY_PORT", 8000))

    uvicorn.run("main:app", host=host, port=port, reload=True, log_level="info")

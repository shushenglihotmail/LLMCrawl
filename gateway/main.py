"""
FastAPI Gateway Service - Main orchestrator for the Web RAG system.
Handles chat interactions, tool calling, and coordinates with crawler/indexer services.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from .routers import chat
from .utils.logging import setup_logging, get_logger

# Setup logging
setup_logging()
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    logger.info("Starting Gateway service")
    
    # Startup
    try:
        # Initialize any startup tasks here
        logger.info("Gateway service started successfully")
        yield
    finally:
        # Cleanup
        logger.info("Shutting down Gateway service")

# Create FastAPI app
app = FastAPI(
    title="Web RAG Gateway",
    description="Gateway service for web crawling and RAG-based question answering",
    version="1.0.0",
    lifespan=lifespan
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["*"]  # Configure appropriately for production
)

# Include routers
app.include_router(chat.router, prefix="/api/v1")

@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "web-rag-gateway",
        "version": "1.0.0",
        "description": "Gateway service for web crawling and RAG-based question answering",
        "endpoints": {
            "chat": "/api/v1/chat",
            "health": "/api/v1/health",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health():
    """Service health check."""
    return {
        "status": "healthy",
        "service": "gateway"
    }

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("GATEWAY_HOST", "0.0.0.0")
    port = int(os.getenv("GATEWAY_PORT", 8000))
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )
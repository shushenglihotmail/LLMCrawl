"""
HTTP server wrapper for Azure DevOps MCP Server.
Provides REST API for LLMCrawl integration.
"""

import logging
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .server import AzureDevOpsMCPServer

logger = logging.getLogger(__name__)


class ToolRequest(BaseModel):
    """Request model for tool invocation."""

    tool_name: str = Field(..., description="Name of the tool to invoke")
    arguments: Dict[str, Any] = Field(..., description="Tool arguments")


class ToolResponse(BaseModel):
    """Response model for tool results."""

    success: bool
    result: Any
    error: Optional[str] = None


def create_http_app() -> FastAPI:
    """Create FastAPI application for HTTP mode."""
    app = FastAPI(
        title="Azure DevOps MCP Server",
        description="MCP server for Azure DevOps code search and file retrieval",
        version="1.0.0",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Get configuration from environment
    organization = os.getenv("AZURE_DEVOPS_ORG", "microsoft")
    project = os.getenv("AZURE_DEVOPS_PROJECT", "OS")
    repository = os.getenv("AZURE_DEVOPS_REPO", "os.2020")
    branch = os.getenv("AZURE_DEVOPS_BRANCH", "main")
    max_results = int(os.getenv("AZURE_DEVOPS_MAX_RESULTS", "50"))
    pat = os.getenv("AZURE_DEVOPS_PAT")

    # Create server instance
    mcp_server = AzureDevOpsMCPServer(
        organization, project, repository, pat, branch, max_results
    )

    @app.on_event("startup")
    async def startup_event():
        """Initialize server on startup."""
        logger.info(
            f"Starting Azure DevOps MCP Server for {organization}/{project}/{repository}"
        )

        # Authenticate using PAT
        # In HTTP mode, allow server to start even if connection test fails
        # The actual requests will handle auth errors
        init_result = await mcp_server.initialize()
        if not init_result:
            logger.warning(
                "Failed to initialize server - authentication may be required for requests"
            )
        else:
            logger.info("Server started successfully")

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "azure-devops-mcp-server",
            "organization": organization,
            "project": project,
            "repository": repository,
        }

    @app.get("/tools")
    async def get_tools():
        """
        Return available tools in OpenAI function calling format.
        This endpoint is called by the gateway to get available tools.
        """
        return {"tools": mcp_server.get_tools()}

    @app.post("/invoke", response_model=ToolResponse)
    async def invoke_tool(request: ToolRequest):
        """
        Execute a tool with given arguments.

        Args:
            request: Tool invocation request

        Returns:
            Tool execution result
        """
        try:
            result = await mcp_server.handle_tool_call(
                request.tool_name, request.arguments
            )

            if "error" in result:
                return ToolResponse(success=False, result=None, error=result["error"])

            return ToolResponse(success=True, result=result, error=None)

        except Exception as e:
            logger.error(f"Tool invocation failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/auth/interactive")
    async def initiate_auth():
        """
        Initiate interactive authentication flow.

        Returns:
            Authentication status
        """
        try:
            success = await mcp_server.initialize(use_interactive_auth=True)
            return {"success": success}
        except Exception as e:
            logger.error(f"Authentication failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    return app

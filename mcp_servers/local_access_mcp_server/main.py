"""
MCP Server for local file operations.
Provides tools to list and read files under a configured root directory.
Supports both stdio transport (for VS Code) and HTTP REST API (for LLMCrawl).
"""

import logging
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .file_reader import FileReader

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration
ROOT_FOLDER = os.getenv("MCP_ROOT_FOLDER", "/data/files")

app = FastAPI(title="MCP File Server", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize file reader
file_reader = FileReader(root_folder=ROOT_FOLDER)


class ToolRequest(BaseModel):
    """Request model for tool invocation."""

    tool_name: str = Field(..., description="Name of the tool to invoke")
    arguments: Dict[str, Any] = Field(..., description="Tool arguments")


class ToolResponse(BaseModel):
    """Response model for tool results."""

    success: bool
    result: Any
    error: Optional[str] = None


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info(f"MCP Server starting with root folder: {ROOT_FOLDER}")

    # Ensure root directory exists
    os.makedirs(ROOT_FOLDER, exist_ok=True)
    logger.info("MCP Server started successfully")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "root_folder": ROOT_FOLDER,
    }


@app.get("/tools")
async def get_tools():
    """
    Return tool definitions in MCP format.
    This endpoint is called by the gateway to get available tools.
    """
    tools = [
        {
            "name": "list_files",
            "description": (
                "List files and directories in a folder. "
                "Use this to explore the file system and find files. "
                "Supports filtering by file extension and recursive search. "
                "Returns both files and subdirectories."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "folder_path": {
                        "type": "string",
                        "description": (
                            "Path to the folder to list (relative to root or absolute). "
                            "Use '.' for root folder."
                        ),
                        "default": ".",
                    },
                    "extension": {
                        "type": "string",
                        "description": (
                            "Filter by file extension (e.g., '.json', '.txt'). "
                            "Leave empty to list all files."
                        ),
                        "default": "",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": (
                            "If true, list files in all subdirectories recursively. "
                            "If false, only list files in the specified folder."
                        ),
                        "default": False,
                    },
                },
                "required": ["folder_path"],
            },
        },
        {
            "name": "read_local_file",
            "description": (
                "Read and return the full content of a file. "
                "Use this after list_files to read a specific file's content. "
                "Supports text files (UTF-8). Binary files return size info only."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to the file to read (relative to root or absolute). "
                            "Get the path from list_files results."
                        ),
                    }
                },
                "required": ["file_path"],
            },
        },
    ]
    return {"tools": tools}


@app.post("/invoke", response_model=ToolResponse)
async def invoke_tool(request: ToolRequest):
    """
    Invoke a tool with the given arguments.
    Called by the gateway when LLM decides to use a tool.
    """
    logger.info(f"Invoking tool: {request.tool_name} with args: {request.arguments}")

    try:
        if request.tool_name == "list_files":
            result = await file_reader.list_files(
                folder_path=request.arguments.get("folder_path", "."),
                extension=request.arguments.get("extension", ""),
                recursive=request.arguments.get("recursive", False),
            )
            return ToolResponse(success=True, result=result)

        elif request.tool_name == "read_local_file":
            result = await file_reader.read_file(
                file_path=request.arguments["file_path"]
            )
            return ToolResponse(success=True, result=result)

        else:
            raise HTTPException(
                status_code=400, detail=f"Unknown tool: {request.tool_name}"
            )

    except ValueError as e:
        # Security/validation errors
        logger.error(f"Tool validation error: {e}")
        return ToolResponse(success=False, result=None, error=str(e))

    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return ToolResponse(success=False, result=None, error=str(e))

"""
MCP Server for local file operations.
Provides tools to read, search, and index files under a configured root directory.
Supports both stdio transport (for VS Code) and HTTP REST API (for LLMCrawl).
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .file_indexer import FileIndexer
from .file_reader import FileReader

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration
ROOT_FOLDER = os.getenv("MCP_ROOT_FOLDER", "/data/files")
VECTOR_DB_PATH = os.getenv("MCP_VECTOR_DB_PATH", "/data/mcp_vector_db")

app = FastAPI(title="MCP File Server", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
file_reader = FileReader(root_folder=ROOT_FOLDER)
file_indexer = FileIndexer(root_folder=ROOT_FOLDER, vector_db_path=VECTOR_DB_PATH)


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
    logger.info(f"Vector DB path: {VECTOR_DB_PATH}")

    # Ensure directories exist
    os.makedirs(ROOT_FOLDER, exist_ok=True)
    os.makedirs(VECTOR_DB_PATH, exist_ok=True)

    # Initialize indexer
    await file_indexer.initialize()
    logger.info("MCP Server started successfully")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "root_folder": ROOT_FOLDER,
        "vector_db_path": VECTOR_DB_PATH,
    }


@app.get("/tools")
async def get_tools():
    """
    Return tool definitions in OpenAI function calling format.
    This endpoint is called by the gateway to get available tools.
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_local_file",
                "description": (
                    "Read and return the content of a local file. "
                    "The file path must be relative to the configured root folder, "
                    "or an absolute path that is within the root folder. "
                    "Use this when the user asks to 'read', 'show', 'display', or "
                    "'get content of' a specific file."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": (
                                "Path to the file (relative to root folder or "
                                "absolute path within root folder)"
                            ),
                        }
                    },
                    "required": ["file_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": (
                    "List files in a directory under the root folder. "
                    "Supports filtering by file extension and recursive search. "
                    "Use this when the user asks to 'list', 'find files', 'show files' "
                    "in a specific folder."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "folder_path": {
                            "type": "string",
                            "description": (
                                "Path to the folder (relative to root or absolute "
                                "within root)"
                            ),
                            "default": ".",
                        },
                        "extension": {
                            "type": "string",
                            "description": (
                                "Filter by file extension (e.g., '.json', '.txt'). "
                                "Leave empty for all files."
                            ),
                            "default": "",
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "Whether to search subdirectories",
                            "default": False,
                        },
                    },
                    "required": ["folder_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_file_content",
                "description": (
                    "Search for files containing specific text or matching a query. "
                    "Files are indexed and searchable using semantic similarity. "
                    "Use this when the user asks to 'find files containing', "
                    "'search for', or 'look for files with' specific content."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query or text to find",
                        },
                        "folder_path": {
                            "type": "string",
                            "description": (
                                "Limit search to specific folder (relative to root)"
                            ),
                            "default": ".",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results to return",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "index_files",
                "description": (
                    "Index files in a folder for semantic search. "
                    "This processes and embeds file content for efficient searching. "
                    "Use this before searching if files haven't been indexed yet."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "folder_path": {
                            "type": "string",
                            "description": "Path to folder to index (relative to root)",
                            "default": ".",
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "Whether to index subdirectories",
                            "default": True,
                        },
                        "extensions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "File extensions to index (e.g., ['.txt', '.json']). "
                                "Empty for all text files."
                            ),
                            "default": [],
                        },
                    },
                    "required": ["folder_path"],
                },
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
        if request.tool_name == "read_local_file":
            result = await file_reader.read_file(
                file_path=request.arguments["file_path"]
            )
            return ToolResponse(success=True, result=result)

        elif request.tool_name == "list_files":
            result = await file_reader.list_files(
                folder_path=request.arguments.get("folder_path", "."),
                extension=request.arguments.get("extension", ""),
                recursive=request.arguments.get("recursive", False),
            )
            return ToolResponse(success=True, result=result)

        elif request.tool_name == "search_file_content":
            result = await file_indexer.search(
                query=request.arguments["query"],
                folder_path=request.arguments.get("folder_path", "."),
                top_k=request.arguments.get("top_k", 5),
            )
            return ToolResponse(success=True, result=result)

        elif request.tool_name == "index_files":
            result = await file_indexer.index_folder(
                folder_path=request.arguments.get("folder_path", "."),
                recursive=request.arguments.get("recursive", True),
                extensions=request.arguments.get("extensions", []),
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

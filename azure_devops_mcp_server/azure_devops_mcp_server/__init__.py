"""
Azure DevOps MCP Server

A Model Context Protocol server for querying files from Azure DevOps repositories.
Supports both stdio transport (for VS Code) and HTTP REST API (for LLMCrawl).
"""

__version__ = "1.0.0"

from .server import AzureDevOpsMCPServer

__all__ = ["AzureDevOpsMCPServer"]

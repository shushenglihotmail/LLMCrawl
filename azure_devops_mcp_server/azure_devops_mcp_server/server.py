"""
Azure DevOps MCP Server

Supports both stdio transport (for VS Code) and HTTP REST API (for LLMCrawl).
"""

import json
import logging
import sys
from typing import Any, Dict, List, Optional

from .azure_client import AzureDevOpsClient

logger = logging.getLogger(__name__)


class AzureDevOpsMCPServer:
    """MCP Server for Azure DevOps code search and file retrieval."""

    def __init__(
        self,
        organization: str,
        project: str,
        repository: str,
        pat: Optional[str] = None,
        branch: str = "main",
        max_results: int = 50,
    ):
        """
        Initialize Azure DevOps MCP Server.

        Args:
            organization: Azure DevOps organization
            project: Project name
            repository: Repository name
            pat: Personal Access Token (optional)
            branch: Default branch (default: main)
            max_results: Default max results per query (default: 50)
        """
        self.client = AzureDevOpsClient(
            organization, project, repository, pat, branch, max_results
        )
        self.tools = self._define_tools()

    def _define_tools(self) -> List[Dict[str, Any]]:
        """Define available MCP tools."""
        return [
            {
                "name": "search_azure_devops_code",
                "description": (
                    "Search for code in Azure DevOps repository. "
                    "Use this when user asks to find, search, or "
                    "locate code, files, functions, or classes in "
                    "the repository. Returns file paths and code "
                    "previews matching the query."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Search query (e.g., 'manifest builder', " "'OneCore')"
                            ),
                        },
                        "file_type": {
                            "type": "string",
                            "description": (
                                "Filter by file extension "
                                "(e.g., '*.cpp', '*.h', '*.cs')"
                            ),
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 20)",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "search_azure_devops_files",
                "description": (
                    "Search for files in Azure DevOps repository "
                    "with flexible filtering. "
                    "⚠️ IMPORTANT: Searches only root directory by "
                    "default (non-recursive). "
                    "Set recursive=true to search subdirectories in "
                    "large repos. "
                    "\n\nSupports path patterns, file name patterns, "
                    "extensions, and keyword search. "
                    "Use this when user wants to list, find, or "
                    "filter files by name, location, or type. "
                    "Returns list of file paths matching the criteria. "
                    "\n\nFilter patterns:\n"
                    "- Path: 'src/' or 'path:src/Services' or "
                    "'path:**/pipelines/**' (** = any depth, "
                    "requires recursive=true)\n"
                    "- File: 'file:azure-pipelines*' or "
                    "'file:*test*' or 'file:README.md'\n"
                    "- Extension: 'ext:yml' or 'ext:cs' or "
                    "'ext:json'\n"
                    "- Keyword: Search in file content "
                    "(use wildcards: 'Azure*', '*timeout', "
                    "requires recursive=true)\n"
                    "- Glob patterns: ** (any depth), * (any chars), "
                    "? (single char)\n"
                    "\nExamples:\n"
                    "- List root files: (no filters)\n"
                    "- Root YAML files: ext:yml\n"
                    "- Recursive search: ext:cs recursive:true\n"
                    "- Deep search: path:**/pipelines/** ext:yml "
                    "recursive:true"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path_pattern": {
                            "type": "string",
                            "description": (
                                "Path filter pattern. Examples: "
                                "'src/', 'path:src/Services', "
                                "'path:**/pipelines/**'. "
                                "Note: ** patterns require recursive=true."
                            ),
                        },
                        "file_pattern": {
                            "type": "string",
                            "description": (
                                "File name pattern (matches only "
                                "filename, not path). Examples: "
                                "'file:azure-pipelines*', 'file:*test*', "
                                "'file:README.md', '*service*.cs'. "
                                "Supports * and ? wildcards."
                            ),
                        },
                        "extension": {
                            "type": "string",
                            "description": (
                                "File extension filter. Examples: "
                                "'ext:yml', 'ext:json', 'ext:cs', 'yml', "
                                "'.yml'"
                            ),
                        },
                        "keyword": {
                            "type": "string",
                            "description": (
                                "Keyword to search in file content. "
                                "Supports wildcards. Examples: 'Azure', "
                                "'connection timeout', 'Http*Request'. "
                                "Note: Searches first 100 matching files. "
                                "Requires recursive=true."
                            ),
                        },
                        "branch": {
                            "type": "string",
                            "description": (
                                "Branch name (default: configured " "default branch)"
                            ),
                        },
                        "max_results": {
                            "type": "integer",
                            "description": (
                                "Maximum number of results " "(default: configured max)"
                            ),
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": (
                                "Search subdirectories recursively. "
                                "Default: false (root only). "
                                "Set to true for deep searches in large "
                                "repos (slower but thorough)."
                            ),
                            "default": False,
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "get_azure_devops_file",
                "description": (
                    "Retrieve the full content of a file from Azure "
                    "DevOps repository. Use this when user asks to "
                    "read, show, display, or get the content of a "
                    "specific file. Requires the full file path."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": (
                                "Path to the file in repository "
                                "(e.g., 'src/main.cpp', '.gitignore')"
                            ),
                        },
                        "branch": {
                            "type": "string",
                            "description": (
                                "Branch name (default: repository " "default branch)"
                            ),
                        },
                    },
                    "required": ["file_path"],
                },
            },
        ]

    async def initialize(self, use_interactive_auth: bool = True) -> bool:
        """
        Initialize and authenticate the server.

        Args:
            use_interactive_auth: Use interactive OAuth flow

        Returns:
            True if initialization successful
        """
        logger.info("Initializing Azure DevOps MCP Server...")
        success = await self.client.authenticate(use_interactive=use_interactive_auth)

        if success:
            # Test connection
            if await self.client.test_connection():
                logger.info("Server initialized successfully")
                return True
            else:
                logger.error("Connection test failed")
                return False
        else:
            logger.error("Authentication failed")
            return False

    def get_tools(self) -> List[Dict[str, Any]]:
        """Get available tools."""
        return self.tools

    async def handle_tool_call(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle tool invocation.

        Args:
            tool_name: Name of the tool to invoke
            arguments: Tool arguments

        Returns:
            Tool result
        """
        try:
            if tool_name == "search_azure_devops_code":
                return await self._handle_search_code(arguments)
            elif tool_name == "search_azure_devops_files":
                return await self._handle_search_files(arguments)
            elif tool_name == "get_azure_devops_file":
                return await self._handle_get_file(arguments)
            else:
                return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return {"error": str(e)}

    async def _handle_search_code(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle code search tool."""
        query = arguments.get("query")
        file_type = arguments.get("file_type")
        max_results = arguments.get("max_results", 20)

        if not query:
            return {"error": "query parameter is required"}

        results = await self.client.search_code(query, file_type, max_results)

        return {
            "success": True,
            "query": query,
            "results_count": len(results),
            "results": results,
        }

    async def _handle_search_files(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle file search tool with flexible filtering."""
        path_pattern = arguments.get("path_pattern")
        file_pattern = arguments.get("file_pattern")
        extension = arguments.get("extension")
        keyword = arguments.get("keyword")
        branch = arguments.get("branch")
        max_results = arguments.get("max_results")
        recursive = arguments.get("recursive", False)

        results = await self.client.search_files(
            path_pattern=path_pattern,
            file_pattern=file_pattern,
            extension=extension,
            keyword=keyword,
            branch=branch,
            max_results=max_results,
            recursive=recursive,
        )

        return {
            "success": True,
            "filters": {
                "path_pattern": path_pattern,
                "file_pattern": file_pattern,
                "extension": extension,
                "keyword": keyword,
                "recursive": recursive,
            },
            "results_count": len(results),
            "results": results,
        }

    async def _handle_get_file(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get file tool."""
        file_path = arguments.get("file_path")
        branch = arguments.get("branch", "main")

        if not file_path:
            return {"error": "file_path parameter is required"}

        result = await self.client.get_file_content(file_path, branch)

        return {"success": True, **result}

    async def run_stdio(self) -> None:
        """
        Run server in stdio mode for VS Code MCP integration.

        Reads JSON-RPC messages from stdin and writes responses to stdout.
        """
        logger.info("Starting stdio transport...")

        # Initialize server
        if not await self.initialize(use_interactive_auth=True):
            sys.exit(1)

        # Main message loop - wait for initialize request from client
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                message = json.loads(line)
                response = await self._handle_jsonrpc_message(message)

                if response:
                    self._send_message(response)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Message handling error: {e}", exc_info=True)

        logger.info("Stdio transport stopped")

    async def _handle_jsonrpc_message(
        self, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Handle JSON-RPC message from MCP client."""
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params", {})

        # Handle initialize request (required by MCP protocol)
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "azure-devops-mcp", "version": "1.0.0"},
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": self.tools},
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            result = await self.handle_tool_call(tool_name, arguments)

            # MCP requires content array format
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                },
            }

        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"status": "ok"},
            }

        return None

    def _send_message(self, message: Dict[str, Any]) -> None:
        """Send JSON-RPC message to stdout."""
        print(json.dumps(message), flush=True)

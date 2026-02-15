"""
Azure DevOps MCP Server

Supports both stdio transport (for VS Code) and HTTP REST API (for LLMCrawl).

This server exposes Azure DevOps Code Search API directly.
Search patterns match Azure DevOps Code Search API syntax:
https://learn.microsoft.com/en-us/rest/api/azure/devops/search/code-search-results/fetch-code-search-results
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
            organization, project, repository, branch, pat or "", max_results
        )
        self.tools = self._define_tools()

    def _define_tools(self) -> List[Dict[str, Any]]:
        """Define available MCP tools."""
        return [
            {
                "name": "search_azure_devops_code",
                "description": (
                    "Search for code/files in Azure DevOps repository using Azure "
                    "DevOps Code Search API. This is the primary tool for finding "
                    "files and code in Azure DevOps repositories.\n\n"
                    "**IMPORTANT**: The `branch` parameter is REQUIRED. You must "
                    "specify the correct branch name. Ask the user which branch "
                    "to search if you are unsure. Common branches:\n"
                    "- official/rs_sparc_ctr\n"
                    "- official/rs_sparc_ctr_exp\n"
                    "- main\n\n"
                    "The search_text is passed DIRECTLY to Azure DevOps Code Search "
                    "API. Use Azure DevOps search syntax in search_text:\n\n"
                    "**Search Syntax Examples:**\n"
                    "- File Extension: `mySearchTerm ext:xml` or `ext:cpp`\n"
                    "- File Name: `file:config` or `file:*config.xml`\n"
                    "- Path keyword: `mySearchTerm path:Services`\n"
                    "- Boolean Logic: `mySearchTerm AND NOT ext:json`\n"
                    "- Code Element: `class:MyClass` (C#, Java) or `func:MyFunction`\n"
                    "- Aggregate: `(term1 OR term2) ext:xml`\n"
                    "- File name specific: `(term1 OR term2) file:*config.xml`\n"
                    "- Find all XML files: `ext:xml`\n"
                    "- Find specific file: `file:azure-pipelines.yml`\n"
                    "- Find files with pattern: `file:*manifest*.xml`\n\n"
                    "Use the `path` parameter to limit search scope to a specific "
                    "folder."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "search_text": {
                            "type": "string",
                            "description": (
                                "Search query text passed directly to Azure DevOps "
                                "Code Search API. Include filters in this string "
                                "using Azure DevOps syntax:\n"
                                "- keyword (search by keyword)\n"
                                "- ext:xml (file extension)\n"
                                "- file:config or file:*pattern* (file name)\n"
                                "- path:folder (path contains)\n"
                                "- class:ClassName or func:FuncName (code elements)\n"
                                "- AND, OR, NOT (boolean operators)\n"
                                "Examples: 'ext:xml', 'manifest ext:xml', "
                                "'file:*config*.json', 'CreateWindow AND ext:cpp'"
                            ),
                        },
                        "path": {
                            "type": "string",
                            "description": (
                                "Path scope - folder path to limit search scope. "
                                "Must be exact folder path (no wildcards). "
                                "Examples: '/src', '/vm/compute', "
                                "'/Nanoserver/merged'. "
                                "Default: '/' (entire repository)"
                            ),
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 20)",
                        },
                        "branch": {
                            "type": "string",
                            "description": (
                                "REQUIRED. Branch name to search in. "
                                "You MUST specify the correct branch. "
                                "Ask the user which branch if unsure. "
                                "Examples: 'official/rs_sparc_ctr', "
                                "'official/rs_sparc_ctr_exp', 'main'"
                            ),
                        },
                        "project": {
                            "type": "string",
                            "description": (
                                "Azure DevOps project name override. "
                                "Use this to search in a different project than the "
                                "default. Example: 'OS', 'OneCore'"
                            ),
                        },
                        "repository": {
                            "type": "string",
                            "description": (
                                "Azure DevOps repository name override. "
                                "Use this to search in a different repository than "
                                "the default. Example: 'os.2020', "
                                "'WindowsCompositionData'"
                            ),
                        },
                    },
                    "required": ["search_text", "branch"],
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
                                "Absolute path to the file in repository, "
                                "MUST start with forward slash. "
                                "Examples: '/src/main.cpp', "
                                "'/Nanoserver/merged/pkggen/file.json', '/.gitignore'"
                            ),
                        },
                        "branch": {
                            "type": "string",
                            "description": (
                                "REQUIRED. Branch name to retrieve the file from. "
                                "You MUST specify the correct branch. "
                                "Ask the user which branch if unsure. "
                                "Examples: 'official/rs_sparc_ctr', "
                                "'official/rs_sparc_ctr_exp', 'main'"
                            ),
                        },
                        "project": {
                            "type": "string",
                            "description": (
                                "Azure DevOps project name override. "
                                "Use this to search in a different project than the "
                                "default. Example: 'OS', 'OneCore'"
                            ),
                        },
                        "repository": {
                            "type": "string",
                            "description": (
                                "Azure DevOps repository name override. "
                                "Use this to search in a different repository than "
                                "the default. Example: 'os.2020', "
                                "'WindowsCompositionData'"
                            ),
                        },
                    },
                    "required": ["file_path", "branch"],
                },
            },
            {
                "name": "get_azure_devops_commit_changes",
                "description": (
                    "Get the changes associated with a specific commit in Azure DevOps. "
                    "This returns the list of files that were added, modified, deleted, "
                    "or renamed in the commit. Use this when you need to understand "
                    "what changes were made in a specific commit."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "commit_id": {
                            "type": "string",
                            "description": (
                                "The commit ID (SHA-1 hash) to retrieve changes for. "
                                "Example: 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0'"
                            ),
                        },
                        "project": {
                            "type": "string",
                            "description": (
                                "Azure DevOps project name override. "
                                "Use this to query a different project than the "
                                "default. Example: 'OS', 'OneCore'"
                            ),
                        },
                        "repository": {
                            "type": "string",
                            "description": (
                                "Azure DevOps repository name override. "
                                "Use this to query a different repository than "
                                "the default. Example: 'os.2020', "
                                "'WindowsCompositionData'"
                            ),
                        },
                    },
                    "required": ["commit_id"],
                },
            },
            {
                "name": "get_azure_devops_commit_file_diff",
                "description": (
                    "Get line-level diff for a specific file in a commit. This shows "
                    "the actual code changes (additions and deletions) for a particular "
                    "file that was modified in the commit. Use this after getting commit "
                    "changes to see the detailed line-by-line diff of what changed in a file."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "commit_id": {
                            "type": "string",
                            "description": (
                                "The commit ID (SHA-1 hash) to retrieve diff for. "
                                "Example: 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0'"
                            ),
                        },
                        "file_path": {
                            "type": "string",
                            "description": (
                                "Path to the file in the repository to get diff for. "
                                "Should match the path from get_azure_devops_commit_changes. "
                                "Example: '/src/main.cpp' or 'src/main.cpp'"
                            ),
                        },
                        "project": {
                            "type": "string",
                            "description": (
                                "Azure DevOps project name override. "
                                "Use this to query a different project than the "
                                "default. Example: 'OS', 'OneCore'"
                            ),
                        },
                        "repository": {
                            "type": "string",
                            "description": (
                                "Azure DevOps repository name override. "
                                "Use this to query a different repository than "
                                "the default. Example: 'os.2020', "
                                "'WindowsCompositionData'"
                            ),
                        },
                    },
                    "required": ["commit_id", "file_path"],
                },
            },
        ]

    async def initialize(self) -> bool:
        """
        Initialize and authenticate the server using PAT.

        Returns:
            True if initialization successful
        """
        logger.info("Initializing Azure DevOps MCP Server...")
        success = await self.client.authenticate()

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
            elif tool_name == "get_azure_devops_file":
                return await self._handle_get_file(arguments)
            elif tool_name == "get_azure_devops_commit_changes":
                return await self._handle_get_commit_changes(arguments)
            elif tool_name == "get_azure_devops_commit_file_diff":
                return await self._handle_get_commit_file_diff(arguments)
            else:
                return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return {"error": str(e)}

    async def _handle_search_code(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle code search tool."""
        search_text = arguments.get("search_text")
        path = arguments.get("path", "/")
        max_results = arguments.get("max_results", 20)
        branch = arguments.get("branch", "")
        project = arguments.get("project")
        repository = arguments.get("repository")

        if not search_text:
            return {"error": "search_text parameter is required"}

        if not branch:
            return {
                "error": (
                    "Missing required 'branch' parameter. "
                    "You must specify which branch to search. "
                    "Examples: 'official/rs_sparc_ctr', 'official/rs_sparc_ctr_exp', 'main'. "
                    "Ask the user which branch to search if you are unsure."
                )
            }

        results = await self.client.search_code(
            search_text=search_text,
            max_results=max_results,
            branch=branch,
            path=path,
            project=project,
            repository=repository,
        )

        # Include effective filters in response for diagnostics
        effective_project = project or self.client.project
        effective_repo = repository or self.client.repository

        response = {
            "success": True,
            "search_text": search_text,
            "path_scope": path,
            "branch": branch,
            "project": effective_project,
            "repository": effective_repo,
            "results_count": len(results),
            "results": results,
        }

        if len(results) == 0:
            response["hint"] = (
                f"No results found. Verify that repository "
                f"'{effective_repo}' exists in project '{effective_project}', "
                f"that branch '{branch}' exists in that repository, "
                f"and that the search text matches actual code content. "
                f"Azure DevOps Code Search requires repositories to be indexed."
            )

        return response

    async def _handle_get_file(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get file tool."""
        file_path = arguments.get("file_path")
        branch = arguments.get("branch", "")
        project = arguments.get("project")
        repository = arguments.get("repository")

        if not file_path:
            return {"error": "file_path parameter is required"}

        if not branch:
            return {
                "error": (
                    "Missing required 'branch' parameter. "
                    "You must specify which branch to retrieve the file from. "
                    "Examples: 'official/rs_sparc_ctr', 'official/rs_sparc_ctr_exp', 'main'. "
                    "Ask the user which branch if you are unsure."
                )
            }

        result = await self.client.get_file_content(
            file_path, branch, project=project, repository=repository
        )

        return {"success": True, **result}

    async def _handle_get_commit_changes(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle get commit changes tool."""
        commit_id = arguments.get("commit_id")
        project = arguments.get("project")
        repository = arguments.get("repository")

        if not commit_id:
            return {"error": "commit_id parameter is required"}

        result = await self.client.get_commit_changes(
            commit_id, project=project, repository=repository
        )

        return {"success": True, **result}

    async def _handle_get_commit_file_diff(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle get commit file diff tool."""
        commit_id = arguments.get("commit_id")
        file_path = arguments.get("file_path")
        project = arguments.get("project")
        repository = arguments.get("repository")

        if not commit_id:
            return {"error": "commit_id parameter is required"}
        if not file_path:
            return {"error": "file_path parameter is required"}

        result = await self.client.get_commit_file_diff(
            commit_id, file_path, project=project, repository=repository
        )

        return {"success": True, **result}

    async def run_stdio(self) -> None:
        """
        Run server in stdio mode for VS Code MCP integration.

        Reads JSON-RPC messages from stdin and writes responses to stdout.
        """
        logger.info("Starting stdio transport...")

        # Initialize server
        if not await self.initialize():
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
                    "serverInfo": {"name": "azure-devops-mcp", "version": "1.1.5"},
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

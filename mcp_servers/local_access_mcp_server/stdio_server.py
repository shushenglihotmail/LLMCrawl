"""
Stdio transport for MCP File Server.
Enables communication via stdin/stdout for VS Code and other stdio-based clients.
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict, Optional

from .file_indexer import FileIndexer
from .file_reader import FileReader

logger = logging.getLogger(__name__)


class StdioMCPServer:
    """MCP Server with stdio transport for local file operations."""

    def __init__(self, root_folder: str, vector_db_path: str):
        """
        Initialize MCP Server with stdio transport.

        Args:
            root_folder: Root folder for file operations
            vector_db_path: Path to vector database
        """
        self.root_folder = root_folder
        self.vector_db_path = vector_db_path
        self.file_reader = FileReader(root_folder=root_folder)
        self.file_indexer = FileIndexer(
            root_folder=root_folder, vector_db_path=vector_db_path
        )
        self.tools = self._define_tools()

    def _define_tools(self):
        """Define available MCP tools."""
        return [
            {
                "name": "read_local_file",
                "description": (
                    "Read and return the content of a local file. "
                    "The file path must be relative to the configured root folder, "
                    "or an absolute path that is within the root folder. "
                    "Use this when the user asks to 'read', 'show', 'display', or "
                    "'get content of' a specific file."
                ),
                "inputSchema": {
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
            {
                "name": "list_files",
                "description": (
                    "List files in a directory under the root folder. "
                    "Supports filtering by file extension and recursive search. "
                    "Use this when the user asks to 'list', 'find files', 'show files' "
                    "in a specific folder."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "folder_path": {
                            "type": "string",
                            "description": (
                                "Path to the folder (relative to root or absolute "
                                "within root)"
                            ),
                        },
                        "extension": {
                            "type": "string",
                            "description": (
                                "Filter by file extension (e.g., '.json', '.txt'). "
                                "Leave empty for all files."
                            ),
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "Whether to search subdirectories",
                        },
                    },
                    "required": ["folder_path"],
                },
            },
            {
                "name": "search_file_content",
                "description": (
                    "Search for files containing specific text or matching a query. "
                    "Files are indexed and searchable using semantic similarity. "
                    "Use this when the user asks to 'find files containing', "
                    "'search for', or 'look for files with' specific content."
                ),
                "inputSchema": {
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
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results to return",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "index_files",
                "description": (
                    "Index files in a folder for semantic search. "
                    "This processes and embeds file content for efficient searching. "
                    "Use this before searching if files haven't been indexed yet."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "folder_path": {
                            "type": "string",
                            "description": "Path to folder to index (relative to root)",
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "Whether to index subdirectories",
                        },
                        "extensions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "File extensions to index (e.g., ['.txt', '.json']). "
                                "Empty for all text files."
                            ),
                        },
                    },
                    "required": ["folder_path"],
                },
            },
        ]

    async def initialize(self) -> bool:
        """
        Initialize the server.

        Returns:
            True if initialization successful
        """
        try:
            await self.file_indexer.initialize()
            logger.info(
                f"MCP Server initialized - Root: {self.root_folder}, "
                f"Vector DB: {self.vector_db_path}"
            )
            return True
        except Exception as e:
            logger.error(f"Initialization failed: {e}", exc_info=True)
            return False

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
            if tool_name == "read_local_file":
                return await self.file_reader.read_file(
                    file_path=arguments["file_path"]
                )

            elif tool_name == "list_files":
                return await self.file_reader.list_files(
                    folder_path=arguments.get("folder_path", "."),
                    extension=arguments.get("extension", ""),
                    recursive=arguments.get("recursive", False),
                )

            elif tool_name == "search_file_content":
                return await self.file_indexer.search(
                    query=arguments["query"],
                    folder_path=arguments.get("folder_path", "."),
                    top_k=arguments.get("top_k", 5),
                )

            elif tool_name == "index_files":
                return await self.file_indexer.index_folder(
                    folder_path=arguments.get("folder_path", "."),
                    recursive=arguments.get("recursive", True),
                    extensions=arguments.get("extensions", []),
                )

            else:
                return {"error": f"Unknown tool: {tool_name}"}

        except ValueError as e:
            logger.error(f"Tool validation error: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return {"error": str(e)}

    async def run_stdio(self) -> None:
        """
        Run server in stdio mode.

        Reads JSON-RPC messages from stdin and writes responses to stdout.
        """
        logger.info("Starting MCP File Server in stdio mode...")
        logger.info(f"Root folder: {self.root_folder}")
        logger.info(f"Vector DB: {self.vector_db_path}")

        # Initialize server
        if not await self.initialize():
            logger.error("Server initialization failed")
            sys.exit(1)

        logger.info("Server initialized, waiting for messages...")

        # Main message loop
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                message = json.loads(line.strip())
                response = await self._handle_jsonrpc_message(message)

                if response:
                    self._send_message(response)

            except KeyboardInterrupt:
                logger.info("Received interrupt signal")
                break
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON received: {e}")
            except Exception as e:
                logger.error(f"Message handling error: {e}", exc_info=True)

        logger.info("Stdio transport stopped")

    async def _handle_jsonrpc_message(
        self, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Handle JSON-RPC message from MCP client.

        Args:
            message: JSON-RPC message

        Returns:
            Response message or None
        """
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params", {})

        logger.debug(f"Received message: method={method}, id={msg_id}")

        # Handle initialize request (required by MCP protocol)
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "local-file-mcp",
                        "version": "1.0.0",
                    },
                },
            }

        # Handle tools/list request
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": self.tools},
            }

        # Handle tools/call request
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            logger.info(f"Calling tool: {tool_name} with args: {arguments}")
            result = await self.handle_tool_call(tool_name, arguments)

            # MCP requires content array format
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                },
            }

        # Handle ping
        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"status": "ok"},
            }

        # Handle notifications (no response needed)
        elif msg_id is None:
            logger.debug(f"Received notification: {method}")
            return None

        # Unknown method
        else:
            logger.warning(f"Unknown method: {method}")
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            }

    def _send_message(self, message: Dict[str, Any]) -> None:
        """
        Send JSON-RPC message to stdout.

        Args:
            message: Message to send
        """
        try:
            output = json.dumps(message)
            print(output, flush=True)
            logger.debug(f"Sent message: {output[:200]}...")
        except Exception as e:
            logger.error(f"Failed to send message: {e}", exc_info=True)


async def run_stdio_server(root_folder: str, vector_db_path: str):
    """
    Run MCP server in stdio mode.

    Args:
        root_folder: Root folder for file operations
        vector_db_path: Path to vector database
    """
    server = StdioMCPServer(root_folder, vector_db_path)
    await server.run_stdio()

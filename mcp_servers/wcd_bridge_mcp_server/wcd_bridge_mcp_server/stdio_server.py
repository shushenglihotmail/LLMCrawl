"""Stdio MCP server for the WCD Bridge wrapper.

Implements MCP JSON-RPC over stdin/stdout (VS Code Copilot compatible).
Uses simple newline-delimited JSON (same as local_access_mcp_server).
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, List, Optional

import httpx

from .wcd_client import WcdBridgeClient

logger = logging.getLogger(__name__)


class WcdBridgeMCPServer:
    def __init__(self, base_url: str, timeout_s: float = 60.0) -> None:
        self.client = WcdBridgeClient(base_url=base_url, timeout_s=timeout_s)
        self.tools = self._define_tools()

    def _define_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "wcd_health",
                "description": (
                    "Check whether the Windows Composition Bridge is reachable "
                    "and healthy. Returns the bridge /health payload including "
                    "WCD tool status."
                ),
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "wcd_query",
                "description": (
                    "Query the Windows Composition Database (WCD) via the "
                    "global $d object. WCD models the relationship between "
                    "Editions, Packages, Assemblies, Files, and APIs in "
                    "Windows builds. Common entry points on $d include: "
                    "Editions, Packages, Assemblies, BuildFiles, "
                    "RegistryValues, Apis, ProductGroups. "
                    "You can use methods like GetInclusionGraph() to trace "
                    "dependencies. "
                    "OUTPUT FORMAT: The result includes PowerShell console output. "
                    "Lines starting with '>> ' are command echoes (ignore them). "
                    "The actual data follows the command echo. "
                    "Output is text-based (tables, trees, or lists), not JSON. "
                    "Example raw output:\\n"
                    ">> $d.Editions['ServerDatacenter'] | Out-String\\n"
                    "Name                    Type\\n"
                    "----                    ----\\n"
                    "ServerDatacenter        Edition\\n"
                    "For GetInclusionGraph(), output is a tree:\\n"
                    "(EDITION):ServerDatacenterNano\\n"
                    "  (PACKAGE):Microsoft-Windows-ServerDatacenterNanoEdition"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "PowerShell command snippet accessing $d. "
                                "Examples: "
                                "$d.Editions['Professional'].AssemblyFilesDeep, "
                                "$d.Packages['*ServerCore*'], "
                                "$($d.BuildFiles['*file.dll'])"
                                ".GetInclusionGraph($d.Editions['Professional']), "
                                "$d.RegistryValues['HKEY_CLASSES_ROOT\\\\*']"
                                ".ContainingPackages"
                            ),
                        }
                    },
                    "required": ["query"],
                },
            },
        ]

    async def initialize(self) -> bool:
        try:
            # Best-effort connectivity check; do not hard-fail to allow offline configs.
            try:
                await self.client.health()
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"Initialization failed: {e}", exc_info=True)
            return False

    async def handle_tool_call(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            if tool_name == "wcd_health":
                return await self.client.health()

            if tool_name == "wcd_query":
                return await self.client.query(arguments["query"])

            return {"error": f"Unknown tool: {tool_name}"}

        except httpx.HTTPStatusError as e:
            return {
                "error": (
                    f"HTTP error from WCD bridge: "
                    f"{e.response.status_code} {e.response.text}"
                )
            }
        except httpx.ConnectError:
            return {
                "error": (
                    "Could not connect to WCD bridge. "
                    "Ensure the host service is running "
                    "(e.g. tools/windows_composition_bridge.py) "
                    "and that your base URL is correct "
                    "(default http://localhost:8005)."
                )
            }
        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return {"error": str(e)}

    def _send_message(self, message: Dict[str, Any]) -> None:
        """Send JSON-RPC message to stdout (newline-delimited)."""
        try:
            output = json.dumps(message)
            print(output, flush=True)
            logger.debug(f"Sent message: {output[:200]}...")
        except Exception as e:
            logger.error(f"Failed to send message: {e}", exc_info=True)

    async def run_stdio(self) -> None:
        """Run MCP server with stdio transport (newline-delimited JSON)."""
        logger.info("Starting MCP stdio server...")

        if not await self.initialize():
            sys.exit(1)

        logger.info("Server initialized, waiting for messages...")

        # Main message loop - simple newline-delimited JSON
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                message = json.loads(line.strip())
                logger.debug(f"Received message: {message.get('method')}")

                response = await self._handle_jsonrpc_message(message)
                if response is not None:
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
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "wcd-bridge-mcp",
                        "version": "0.1.0",
                    },
                },
            }

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": self.tools}}

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            result = await self.handle_tool_call(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                },
            }

        if method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"status": "ok"}}

        if msg_id is None:
            return None

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


async def run_stdio_server(base_url: str, timeout_s: float = 60.0) -> None:
    server = WcdBridgeMCPServer(base_url=base_url, timeout_s=timeout_s)
    await server.run_stdio()

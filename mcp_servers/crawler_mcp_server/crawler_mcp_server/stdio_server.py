"""Stdio MCP server for the Crawler wrapper."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, List, Optional

import httpx

from .crawler_client import CrawlerClient

logger = logging.getLogger(__name__)


class CrawlerMCPServer:
    def __init__(self, base_url: str, timeout_s: float = 120.0) -> None:
        self.client = CrawlerClient(base_url=base_url, timeout_s=timeout_s)
        self.tools = self._define_tools()

    def _define_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "crawler_health",
                "description": "Check crawler health via /health.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "crawler_crawl",
                "description": (
                    "Crawl web pages and return complete extracted content. "
                    "This method handles rendering with Playwright, extracting with Trafilatura, "
                    "and returns the full content (markdown, HTML, text) directly. "
                    "Specify the URL in the query parameter to crawl that specific page."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "URL to crawl or search query. For MCP usage, provide the URL here.",
                        },
                        "freshness_days": {
                            "type": "integer",
                            "description": "How recent content should be (default: 7 days)",
                            "default": 7,
                        },
                        "depth": {
                            "type": "integer",
                            "description": "Crawl depth: 1=single page, >1=follow links (default: 1)",
                            "default": 1,
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of documents to return (default: 10)",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            },
        ]

    async def initialize(self) -> bool:
        try:
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
            if tool_name == "crawler_health":
                return await self.client.health()

            if tool_name == "crawler_crawl":
                return await self.client.crawl(
                    query=arguments["query"],
                    freshness_days=int(arguments.get("freshness_days", 7)),
                    depth=int(arguments.get("depth", 1)),
                    max_results=int(arguments.get("max_results", 10)),
                )

            return {"error": f"Unknown tool: {tool_name}"}

        except httpx.HTTPStatusError as e:
            err = f"HTTP error: {e.response.status_code} {e.response.text}"
            return {"error": err}
        except httpx.ConnectError:
            return {
                "error": (
                    "Could not connect to crawler. "
                    "Ensure the crawler service is running (default localhost:8001)."
                )
            }
        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return {"error": str(e)}

    async def run_stdio(self) -> None:
        if not await self.initialize():
            sys.exit(1)

        while True:
            line = sys.stdin.readline()
            if not line:
                break

            try:
                message = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            response = await self._handle_jsonrpc_message(message)
            if response is not None:
                self._send_message(response)

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
                        "name": "crawler-mcp",
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

    def _send_message(self, message: Dict[str, Any]) -> None:
        print(json.dumps(message), flush=True)


async def run_stdio_server(base_url: str, timeout_s: float = 120.0) -> None:
    server = CrawlerMCPServer(base_url=base_url, timeout_s=timeout_s)
    await server.run_stdio()

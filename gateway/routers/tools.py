"""
Tool calling router and handlers.
Manages the crawl_and_refresh tool and orchestrates the RAG pipeline.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from ..utils.logging import log_tool_call, log_tool_result

logger = logging.getLogger(__name__)


class ToolHandler:
    """Handles tool function calls and orchestrates the RAG pipeline."""

    def __init__(self):
        self.crawler_url = "http://crawler:8001"
        self.indexer_url = "http://indexer:8002"
        self.mcp_server_url = os.getenv("MCP_SERVER_URL", "http://mcp-server:8003")
        # Increased from 30s to allow for slower FireCrawl
        # + Playwright fallback
        self.timeout = 45.0
        self.mcp_tools = [
            "read_local_file",
            "list_files",
            "search_file_content",
            "index_files",
        ]

    async def handle_tool_call(
        self,
        tool_call: Dict[str, Any],
        request_id: str,
        seed_urls: Optional[List[str]] = None,
        depth: Optional[int] = None,
        skip_embedding: bool = False,
    ) -> Dict[str, Any]:
        """
        Handle a tool function call and return the result.

        Args:
            tool_call: Tool call from LLM response
            request_id: Request tracking ID
            seed_urls: Optional seed URLs to override tool arguments
            depth: Optional crawl depth to override tool arguments
            skip_embedding: Skip embedding/indexing, return raw content

        Returns:
            Tool result for LLM context
        """
        tool_name = tool_call["function"]["name"]
        arguments = json.loads(tool_call["function"]["arguments"])

        # Override arguments with user-provided seed_urls and depth
        if seed_urls:
            arguments["seed_urls"] = seed_urls
            logger.info(f"Overriding seed_urls with user-provided: {seed_urls}")
        if depth is not None:
            arguments["depth"] = depth
            logger.info(f"Overriding depth with user-provided: {depth}")

        log_tool_call(logger, request_id, tool_name, arguments)
        start_time = datetime.now()

        try:
            if tool_name == "crawl_and_refresh":
                result = await self._handle_crawl_and_refresh(
                    arguments, request_id, skip_embedding
                )
                success = True
            elif tool_name in self.mcp_tools:
                result = await self._handle_mcp_tool(tool_name, arguments, request_id)
                success = True
            elif tool_name in [
                "search_azure_devops_code",
                "search_azure_devops_files",
                "get_azure_devops_file",
            ]:
                result = await self._handle_azure_devops_tool(
                    tool_name, arguments, request_id
                )
                success = True
            else:
                result = {"error": f"Unknown tool: {tool_name}"}
                success = False

        except Exception as e:
            logger.error(f"Tool call failed: {e}")
            result = {"error": str(e)}
            success = False

        # Log result
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        result_size = len(json.dumps(result))
        log_tool_result(
            logger, request_id, tool_name, success, duration_ms, result_size
        )

        return {
            "tool_call_id": tool_call["id"],
            "role": "tool",
            "content": json.dumps(result),
        }

    async def _handle_crawl_and_refresh(
        self, arguments: Dict[str, Any], request_id: str, skip_embedding: bool = False
    ) -> Dict[str, Any]:
        """
        Handle the crawl_and_refresh tool call.

        Pipeline:
        1. Crawl web content with Firecrawl/Playwright
        2. If skip_embedding=False: Index documents and retrieve with vector search
        3. If skip_embedding=True: Return raw crawled content directly

        Args:
            arguments: Tool arguments (query, seed_urls, etc.)
            request_id: Request tracking ID
            skip_embedding: Skip embedding/indexing, return raw content

        Returns:
            Formatted tool result with sources
        """
        query = arguments["query"]
        seed_urls = arguments.get("seed_urls", [])
        freshness_days = arguments.get("freshness_days", 7)
        depth = arguments.get("depth", 1)

        logger.info(f"Starting crawl_and_refresh for query: {query}")

        # Step 1: Crawl web content
        crawl_result = await self._call_crawler(
            query=query,
            seed_urls=seed_urls,
            freshness_days=freshness_days,
            depth=depth,
            request_id=request_id,
        )

        if not crawl_result.get("docs"):
            return {
                "error": "No documents found during crawling",
                "query": query,
                "count": 0,
            }

        docs = crawl_result["docs"]
        logger.info(f"Crawled {len(docs)} documents")

        # If skip_embedding is True, return raw content directly
        if skip_embedding:
            logger.info(
                "skip_embedding=True, returning raw crawled content " "without indexing"
            )
            return {
                "count": len(docs),
                "examples": [
                    {
                        "url": doc["url"],
                        "title": doc.get("title", ""),
                        "published_at": doc.get("published_at", ""),
                    }
                    for doc in docs[:3]  # Show first 3 as examples
                ],
                "hits": [
                    {
                        "url": doc["url"],
                        "title": doc.get("title", ""),
                        "content": doc.get(
                            "markdown", ""
                        ),  # Full content, not truncated
                        "published_at": doc.get("published_at", ""),
                        "score": 1.0,
                    }
                    for doc in docs
                ],
                "query": query,
                "indexed": 0,
                "skip_embedding": True,
            }

        # Step 2: Try to index documents, but continue if it fails
        index_result = await self._call_indexer_index(docs, request_id)
        logger.info(f"Index result: {index_result}")

        if not index_result.get("indexed", 0) or index_result.get("error"):
            logger.warning(
                f"Failed to index documents (result: {index_result}) - "
                f"using direct document results"
            )
            # Fallback: return crawled documents directly without vector search
            return {
                "count": len(docs),
                "examples": [
                    {
                        "url": doc["url"],
                        "title": doc.get("title", ""),
                        "published_at": doc.get("published_at", ""),
                    }
                    for doc in docs[:3]  # Show first 3 as examples
                ],
                "hits": [
                    {
                        "url": doc["url"],
                        "title": doc.get("title", ""),
                        "content": (
                            doc.get("markdown", "")[:500] + "..."
                            if len(doc.get("markdown", "")) > 500
                            else doc.get("markdown", "")
                        ),
                        "published_at": doc.get("published_at", ""),
                        "score": 1.0,  # Fixed high relevance score for crawled content
                    }
                    for doc in docs
                ],
                "query": query,
                "indexed": 0,
                "fallback_mode": True,
            }

        # Step 3: Retrieve relevant results using vector search
        retrieve_result = await self._call_indexer_retrieve(
            query=query, k=8, recency_boost_days=freshness_days, request_id=request_id
        )

        hits = retrieve_result.get("hits", [])

        # If retrieval returns no results, fall back to direct crawled content
        if not hits:
            logger.warning(
                "Retrieval returned 0 hits, using direct crawled content " "(fallback)"
            )
            return {
                "count": len(docs),
                "examples": [
                    {
                        "url": doc["url"],
                        "title": doc.get("title", ""),
                        "published_at": doc.get("published_at", ""),
                    }
                    for doc in docs[:3]  # Show first 3 as examples
                ],
                "hits": [
                    {
                        "url": doc["url"],
                        "title": doc.get("title", ""),
                        "content": (
                            doc.get("markdown", "")[:500] + "..."
                            if len(doc.get("markdown", "")) > 500
                            else doc.get("markdown", "")
                        ),
                        "published_at": doc.get("published_at", ""),
                        "score": 1.0,  # Fixed high relevance score for crawled content
                    }
                    for doc in docs
                ],
                "query": query,
                "indexed": index_result.get("indexed", 0),
                "fallback_mode": True,
            }

        # Format result for LLM
        return {
            "count": len(hits),
            "examples": [
                {
                    "url": hit["url"],
                    "title": hit.get("title", ""),
                    "published_at": hit.get("published_at", ""),
                }
                for hit in hits[:3]  # Show first 3 as examples
            ],
            "hits": hits,
            "query": query,
            "indexed": index_result.get("indexed", 0),
        }

    async def _call_crawler(
        self,
        query: str,
        seed_urls: List[str],
        freshness_days: int,
        depth: int,
        request_id: str,
    ) -> Dict[str, Any]:
        """Call the crawler service to fetch web content."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.crawler_url}/crawl",
                    json={
                        "query": query,
                        "seed_urls": seed_urls,
                        "freshness_days": freshness_days,
                        "depth": depth,
                    },
                    headers={"X-Request-ID": request_id},
                )
                response.raise_for_status()
                return response.json()

            except httpx.RequestError as e:
                logger.error(f"Crawler request failed: {e}")
                return {"error": f"Crawler service unavailable: {e}"}
            except httpx.HTTPStatusError as e:
                logger.error(f"Crawler HTTP error: {e.response.status_code}")
                return {"error": f"Crawler error: {e.response.status_code}"}

    async def _call_indexer_index(
        self, docs: List[Dict[str, Any]], request_id: str
    ) -> Dict[str, Any]:
        """Call the indexer service to index documents."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.indexer_url}/index",
                    json={"docs": docs},
                    headers={"X-Request-ID": request_id},
                )
                response.raise_for_status()
                return response.json()

            except Exception as e:
                logger.error(f"Indexing failed: {e}")
                return {"error": f"Indexing failed: {e}"}

    async def _call_indexer_retrieve(
        self, query: str, k: int, recency_boost_days: int, request_id: str
    ) -> Dict[str, Any]:
        """Call the indexer service to retrieve relevant documents."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.indexer_url}/retrieve",
                    json={
                        "query": query,
                        "k": k,
                        "recency_boost_days": recency_boost_days,
                        # Accept all results, recency boost handles ranking
                        "score_threshold": 0.0,
                    },
                    headers={"X-Request-ID": request_id},
                )
                response.raise_for_status()
                return response.json()

            except Exception as e:
                logger.error(f"Retrieval failed: {e}")
                return {"error": f"Retrieval failed: {e}"}

    async def _handle_mcp_tool(
        self, tool_name: str, arguments: Dict[str, Any], request_id: str
    ) -> Dict[str, Any]:
        """
        Handle MCP server tool calls for local file operations.

        Args:
            tool_name: Name of the MCP tool
            arguments: Tool arguments
            request_id: Request tracking ID

        Returns:
            Tool result
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.mcp_server_url}/invoke",
                    json={"tool_name": tool_name, "arguments": arguments},
                    headers={"X-Request-ID": request_id},
                )
                response.raise_for_status()
                result = response.json()

                if not result.get("success"):
                    return {"error": result.get("error", "MCP tool execution failed")}

                return result.get("result", {})

            except httpx.RequestError as e:
                logger.error(f"MCP server request failed: {e}")
                return {"error": f"MCP server unavailable: {e}"}
            except httpx.HTTPStatusError as e:
                logger.error(f"MCP server HTTP error: {e.response.status_code}")
                return {"error": f"MCP server error: {e.response.status_code}"}

    async def _handle_azure_devops_tool(
        self, tool_name: str, arguments: Dict[str, Any], request_id: str
    ) -> Dict[str, Any]:
        """
        Handle Azure DevOps MCP server tool calls.

        Args:
            tool_name: Name of the Azure DevOps tool
            arguments: Tool arguments
            request_id: Request tracking ID

        Returns:
            Tool result
        """
        azure_devops_mcp_url = os.getenv(
            "AZURE_DEVOPS_MCP_URL", "http://azure-devops-mcp-server:8004"
        )

        # Add branch parameter if not provided and environment variable exists
        if tool_name == "get_azure_devops_file" and "branch" not in arguments:
            branch = os.getenv("AZURE_DEVOPS_BRANCH")
            if branch:
                arguments["branch"] = branch
                logger.debug(f"Added branch from environment: {branch}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{azure_devops_mcp_url}/invoke",
                    json={"tool_name": tool_name, "arguments": arguments},
                    headers={"X-Request-ID": request_id},
                )
                response.raise_for_status()
                result = response.json()

                if not result.get("success"):
                    return {
                        "error": result.get(
                            "error", "Azure DevOps tool execution failed"
                        )
                    }

                return result.get("result", {})

            except httpx.RequestError as e:
                logger.error(f"Azure DevOps MCP server request failed: {e}")
                return {"error": f"Azure DevOps MCP server unavailable: {e}"}
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Azure DevOps MCP server HTTP error: {e.response.status_code}"
                )
                return {
                    "error": f"Azure DevOps MCP server error: {e.response.status_code}"
                }


# Global tool handler
_tool_handler = None


def get_tool_handler() -> ToolHandler:
    """Get or create the global tool handler instance."""
    global _tool_handler
    if _tool_handler is None:
        _tool_handler = ToolHandler()
    return _tool_handler

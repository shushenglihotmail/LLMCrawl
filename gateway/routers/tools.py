"""
Tool calling router and handlers.
Manages the crawl_and_refresh tool and orchestrates the RAG pipeline.
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List

import httpx

from ..agents.windows_composition import get_composition_client
from ..utils.azdo_uri import is_azdo_uri, parse_azdo_uri
from ..utils.logging import log_tool_call, log_tool_result
from ..utils.metrics import (
    classify_error,
    get_domain_from_url,
    record_crawl_request,
    record_tool_call,
)
from ..utils.tool_constants import (
    TOOL_AZURE_DEVOPS_GET_FILE,
    TOOL_AZURE_DEVOPS_SEARCH_CODE,
    TOOL_CRAWL_AND_REFRESH,
    TOOL_INDEX_FILES,
    TOOL_LIST_FILES,
    TOOL_QUERY_COMPOSITION_DB,
    TOOL_READ_LOCAL_FILE,
    TOOL_SEARCH_FILE_CONTENT,
)

logger = logging.getLogger(__name__)


class ToolHandler:
    """Handles tool function calls and orchestrates the RAG pipeline."""

    def __init__(self) -> None:
        self.crawler_url = "http://crawler:8001"
        self.indexer_url = "http://indexer:8002"
        self.mcp_server_url = os.getenv("MCP_SERVER_URL", "http://mcp-server:8003")
        # Increased to 90s to allow for depth crawling with Playwright
        # which can take 60-70s for depth=2 with authentication
        self.timeout = 90.0
        self.mcp_tools = [
            TOOL_READ_LOCAL_FILE,
            TOOL_LIST_FILES,
            TOOL_SEARCH_FILE_CONTENT,
            TOOL_INDEX_FILES,
        ]

    async def handle_tool_call(
        self,
        tool_call: Dict[str, Any],
        request_id: str,
        skip_embedding: bool = False,
        initiator: str = "llm",  # 'llm' or 'agent' or 'user'
    ) -> Dict[str, Any]:
        """
        Handle a tool function call and return the result.

        Args:
            tool_call: Tool call from LLM response
            request_id: Request tracking ID
            skip_embedding: Skip embedding/indexing, return raw content
            initiator: Who initiated the tool call (llm, agent, user)

        Returns:
            Tool result for LLM context
        """
        tool_name = tool_call["function"]["name"]
        arguments = json.loads(tool_call["function"]["arguments"])

        log_tool_call(logger, request_id, tool_name, arguments)
        start_time = time.time()
        status = "success"
        error_type = None

        try:
            if tool_name == TOOL_CRAWL_AND_REFRESH:
                result = await self._handle_crawl_and_refresh(
                    arguments, request_id, skip_embedding, initiator
                )
            elif tool_name in self.mcp_tools:
                result = await self._handle_mcp_tool(
                    tool_name, arguments, request_id, initiator
                )
            elif tool_name in [
                TOOL_AZURE_DEVOPS_SEARCH_CODE,
                TOOL_AZURE_DEVOPS_GET_FILE,
            ]:
                result = await self._handle_azure_devops_tool(
                    tool_name, arguments, request_id, initiator
                )
            elif tool_name == TOOL_QUERY_COMPOSITION_DB:
                result = await self._handle_composition_tool(arguments, request_id)
            else:
                result = {"error": f"Unknown tool: {tool_name}"}
                status = "error"
                error_type = "unknown_tool"

        except Exception as e:
            logger.error(f"Tool call failed: {e}")
            result = {"error": str(e)}
            status = "error"
            error_type = classify_error(e)

        # Record metrics with parameters for debugging
        duration = time.time() - start_time
        record_tool_call(
            tool_name=tool_name,
            status=status,
            duration=duration,
            error_type=error_type,
            parameters=arguments,
        )

        # Log result
        duration_ms = duration * 1000
        result_size = len(json.dumps(result))
        log_tool_result(
            logger, request_id, tool_name, status == "success", duration_ms, result_size
        )

        return {
            "tool_call_id": tool_call["id"],
            "role": "tool",
            "content": json.dumps(result),
        }

    async def _handle_crawl_and_refresh(
        self,
        arguments: Dict[str, Any],
        request_id: str,
        skip_embedding: bool = False,
        initiator: str = "llm",
    ) -> Dict[str, Any]:
        """
        Handle the crawl_and_refresh tool call with proper separation of concerns.

        Gateway orchestration:
        1. If seed_urls provided: prefetch those URLs via crawler
        2. If skip_embedding=False: Index documents and retrieve with vector search
        3. If skip_embedding=True: Return raw crawled content directly

        Args:
            arguments: Tool arguments (query, seed_urls, etc.)
            request_id: Request tracking ID
            skip_embedding: Skip embedding/indexing, return raw content
            initiator: Who initiated the crawl (llm, agent, user)

        Returns:
            Formatted tool result with sources
        """
        query = arguments["query"]
        freshness_days = arguments.get("freshness_days", 7)
        depth = arguments.get("depth", 1)
        max_results = arguments.get("max_results", 10)

        logger.info(f"Starting crawl_and_refresh for URL: {query}")

        # LLM should provide a URL in the query parameter
        if not query or not query.startswith(("http://", "https://")):
            return {
                "error": "Invalid URL. Please provide a valid http:// or https:// URL.",
                "query": query,
                "count": 0,
            }

        urls_to_crawl = [query]
        logger.info(f"Crawling URL: {query}")

        # Crawl the URL (crawler just does: crawl → render → extract)
        crawl_result = None
        source = "firecrawl"

        for url in urls_to_crawl[:3]:  # Track metrics for first few URLs
            domain = get_domain_from_url(url)
            crawl_start = time.time()
            crawl_status = "success"
            try:
                crawl_result = await self._call_crawler(
                    urls=urls_to_crawl,
                    depth=depth,
                    max_results=max_results,
                    request_id=request_id,
                )
            except Exception as e:
                crawl_status = "error"
                record_crawl_request(
                    status=crawl_status,
                    domain=domain,
                    source=source,
                    duration=time.time() - crawl_start,
                )
                raise
            finally:
                if crawl_status == "success":
                    crawl_duration = time.time() - crawl_start
                    record_crawl_request(
                        status=crawl_status,
                        domain=domain,
                        source=source,
                        duration=crawl_duration,
                    )
            break  # Only measure once

        if not crawl_result or not crawl_result.get("docs"):
            return {
                "error": "No documents found during crawling",
                "query": query,
                "count": 0,
            }

        docs = crawl_result["docs"]
        logger.info(f"Crawled {len(docs)} documents")

        # Step 3: Handle embedding (if enabled)
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
        urls: List[str],
        depth: int,
        max_results: int,
        request_id: str,
    ) -> Dict[str, Any]:
        """Call the simplified crawler service to crawl URLs."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.crawler_url}/crawl",
                    json={
                        "urls": urls,
                        "depth": depth,
                        "max_results": max_results,
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
        headers = {"X-Request-ID": request_id}
        token = get_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            logger.warning("No Bearer token available for Indexer request")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.indexer_url}/index",
                    json={"docs": docs},
                    headers=headers,
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
        headers = {"X-Request-ID": request_id}
        token = get_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

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
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()

            except Exception as e:
                logger.error(f"Retrieval failed: {e}")
                return {"error": f"Retrieval failed: {e}"}

    async def _handle_mcp_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        request_id: str,
        initiator: str = "llm",
    ) -> Dict[str, Any]:
        """
        Handle MCP server tool calls for local file operations.

        Args:
            tool_name: Name of the MCP tool
            arguments: Tool arguments
            request_id: Request tracking ID
            initiator: Who initiated the call (llm, agent, user)

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
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        request_id: str,
        initiator: str = "llm",
    ) -> Dict[str, Any]:
        """
        Handle Azure DevOps MCP server tool calls.

        Supports azdo:// URI format for multi-repository access:
          azdo:/path/to/file.cpp              - Use default project, repo, and branch
          azdo:/path/to/file.cpp?branch=main  - Use default project, repo; override branch
          azdo://Project/repo/path/to/file.cpp  - Use specified project, repo; default branch
          azdo://Project/repo/path/to/file.cpp?branch=main  - Fully specified

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

        # Check for azdo:// URI in file_path argument
        file_path = arguments.get("file_path", "")
        if file_path and is_azdo_uri(file_path):
            parsed = parse_azdo_uri(file_path)
            if parsed:
                logger.info(f"Parsed azdo URI: {file_path} -> {parsed}")
                # Update arguments with parsed values
                arguments["file_path"] = parsed.path
                if parsed.project:
                    arguments["project"] = parsed.project
                if parsed.repository:
                    arguments["repository"] = parsed.repository
                if parsed.branch:
                    arguments["branch"] = parsed.branch
            else:
                logger.warning(f"Failed to parse azdo URI: {file_path}")

        # Add branch parameter if not provided and environment variable exists
        if tool_name == TOOL_AZURE_DEVOPS_GET_FILE and "branch" not in arguments:
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

            except httpx.TimeoutException as e:
                logger.error(f"Azure DevOps MCP tool '{tool_name}' timed out: {e}")
                return {
                    "error": (
                        f"Tool '{tool_name}' timed out. Try using "
                        "search_azure_devops_code instead of "
                        "search_azure_devops_files for large directories."
                    )
                }
            except httpx.RequestError as e:
                logger.error(f"Azure DevOps MCP server request failed: {e}")
                return {"error": f"Azure DevOps MCP server connection failed: {e}"}
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"Azure DevOps MCP server HTTP error: {e.response.status_code}"
                )
                return {
                    "error": f"Azure DevOps MCP server error: {e.response.status_code}"
                }

    async def _handle_composition_tool(
        self, arguments: Dict[str, Any], request_id: str
    ) -> Dict[str, Any]:
        """
        Handle Windows Composition Database query tool.
        """
        query = arguments.get("query")
        if not query:
            return {"error": "Query parameter is required"}

        client = get_composition_client()
        if not client:
            return {
                "error": "Windows Composition Bridge not configured. "
                "Set WIN_COMP_BRIDGE_URL environment variable."
            }

        try:
            result_json = await client.run_query(query)
            return {"result": result_json}
        except Exception as e:
            logger.error(f"Composition query failed: {e}")
            return {"error": str(e)}


# Global tool handler
_tool_handler = None


def get_tool_handler() -> ToolHandler:
    """Get or create the global tool handler instance."""
    global _tool_handler
    if _tool_handler is None:
        _tool_handler = ToolHandler()
    return _tool_handler


from ..utils.token_context import get_token

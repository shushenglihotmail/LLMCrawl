"""
Tool calling router and handlers.
Manages the crawl_and_refresh tool and orchestrates the RAG pipeline.
"""

import json
import uuid
import asyncio
from typing import Dict, Any, List, Optional
import httpx
import logging
from datetime import datetime

from ..utils.logging import log_tool_call, log_tool_result

logger = logging.getLogger(__name__)

class ToolHandler:
    """Handles tool function calls and orchestrates the RAG pipeline."""
    
    def __init__(self):
        self.crawler_url = "http://crawler:8001"
        self.indexer_url = "http://indexer:8002"
        self.timeout = 30.0
        
    async def handle_tool_call(
        self,
        tool_call: Dict[str, Any],
        request_id: str
    ) -> Dict[str, Any]:
        """
        Handle a tool function call and return the result.
        
        Args:
            tool_call: Tool call from LLM response
            request_id: Request tracking ID
            
        Returns:
            Tool result for LLM context
        """
        tool_name = tool_call["function"]["name"]
        arguments = json.loads(tool_call["function"]["arguments"])
        
        log_tool_call(logger, request_id, tool_name, arguments)
        start_time = datetime.now()
        
        try:
            if tool_name == "crawl_and_refresh":
                result = await self._handle_crawl_and_refresh(arguments, request_id)
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
        log_tool_result(logger, request_id, tool_name, success, duration_ms, result_size)
        
        return {
            "tool_call_id": tool_call["id"],
            "role": "tool",
            "content": json.dumps(result)
        }
    
    async def _handle_crawl_and_refresh(
        self,
        arguments: Dict[str, Any],
        request_id: str
    ) -> Dict[str, Any]:
        """
        Handle the crawl_and_refresh tool call.
        
        Pipeline:
        1. Crawl web content with Firecrawl/Playwright
        2. Index documents in vector database
        3. Retrieve relevant results with recency boost
        
        Args:
            arguments: Tool arguments (query, seed_urls, etc.)
            request_id: Request tracking ID
            
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
            request_id=request_id
        )
        
        if not crawl_result.get("docs"):
            return {
                "error": "No documents found during crawling",
                "query": query,
                "count": 0
            }
            
        docs = crawl_result["docs"]
        logger.info(f"Crawled {len(docs)} documents")
        
        # Step 2: Index documents  
        index_result = await self._call_indexer_index(docs, request_id)
        
        if not index_result.get("indexed", 0):
            logger.warning("Failed to index documents")
            
        # Step 3: Retrieve relevant results
        retrieve_result = await self._call_indexer_retrieve(
            query=query,
            k=8,
            recency_boost_days=freshness_days,
            request_id=request_id
        )
        
        hits = retrieve_result.get("hits", [])
        
        # Format result for LLM
        return {
            "count": len(hits),
            "examples": [
                {
                    "url": hit["url"],
                    "title": hit.get("title", ""),
                    "published_at": hit.get("published_at", "")
                }
                for hit in hits[:3]  # Show first 3 as examples
            ],
            "hits": hits,
            "query": query,
            "indexed": index_result.get("indexed", 0)
        }
    
    async def _call_crawler(
        self,
        query: str,
        seed_urls: List[str],
        freshness_days: int,
        depth: int,
        request_id: str
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
                        "depth": depth
                    },
                    headers={"X-Request-ID": request_id}
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
        self,
        docs: List[Dict[str, Any]],
        request_id: str
    ) -> Dict[str, Any]:
        """Call the indexer service to index documents."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.indexer_url}/index",
                    json={"docs": docs},
                    headers={"X-Request-ID": request_id}
                )
                response.raise_for_status()
                return response.json()
                
            except Exception as e:
                logger.error(f"Indexing failed: {e}")
                return {"error": f"Indexing failed: {e}"}
    
    async def _call_indexer_retrieve(
        self,
        query: str,
        k: int,
        recency_boost_days: int,
        request_id: str
    ) -> Dict[str, Any]:
        """Call the indexer service to retrieve relevant documents."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.indexer_url}/retrieve",
                    json={
                        "query": query,
                        "k": k,
                        "recency_boost_days": recency_boost_days
                    },
                    headers={"X-Request-ID": request_id}
                )
                response.raise_for_status()
                return response.json()
                
            except Exception as e:
                logger.error(f"Retrieval failed: {e}")
                return {"error": f"Retrieval failed: {e}"}

# Global tool handler
_tool_handler = None

def get_tool_handler() -> ToolHandler:
    """Get or create the global tool handler instance."""
    global _tool_handler
    if _tool_handler is None:
        _tool_handler = ToolHandler()
    return _tool_handler
"""Crawler MCP Server.

A simple MCP wrapper that connects LLMCrawl crawler service to VS Code AI agents.

Prerequisites:
- LLMCrawl crawler service running at http://localhost:8001
- Authenticated via LLMCrawl CLI (llmcrawl authenticate)

Usage:
    # Run MCP server
    crawler-mcp-server

    # Or with custom URL
    crawler-mcp-server --base-url http://my-crawler:8001
"""

__all__ = ["__version__"]
__version__ = "0.3.0"

"""Crawler MCP Server.

A comprehensive package for the LLMCrawl Crawler service:
- MCP Tools: Expose crawler to VS Code AI agents
- Container Management: Start/stop/restart Docker containers
- Authentication: Cookie-based auth for internal sites
- Native Service: Run crawler without Docker (optional)

Usage:
    # As CLI
    crawler-mcp-server start        # Start containers
    crawler-mcp-server stop         # Stop containers
    crawler-mcp-server restart      # Restart containers
    crawler-mcp-server status       # Check health
    crawler-mcp-server auth <url>   # Authenticate to internal site
    crawler-mcp-server mcp          # Run MCP server for VS Code
    crawler-mcp-server serve        # Run crawler natively

    # As library
    from crawler_mcp_server import containers, auth
    containers.start_services()
    containers.stop_services()
"""

__all__ = ["__version__", "containers", "auth"]
__version__ = "0.2.0"

# Crawler MCP Server

A simple MCP (Model Context Protocol) server that connects LLMCrawl crawler to VS Code AI agents.

## What It Does

Exposes LLMCrawl crawler functionality as MCP tools for VS Code AI agents (GitHub Copilot, etc.).

## Prerequisites

- **LLMCrawl crawler service running** at http://localhost:8001
  - Use the main LLMCrawl deployment (see main README)
  - Or run from source: `cd crawler && uvicorn main:app --port 8001`

## Installation

```bash
# From wheel
pip install dist/crawler_mcp_server-*.whl

# From PyPI (when published)
pip install crawler-mcp-server
```

## Usage

```bash
# Run MCP server (connects to http://localhost:8001)
crawler-mcp-server

# Connect to custom URL
crawler-mcp-server --base-url http://my-crawler:8001
```

## VS Code Integration

Add to your VS Code `settings.json` or `.vscode/mcp.json`:

```json
{
    "mcp": {
        "servers": {
            "crawler": {
                "command": "python",
                "args": ["-m", "crawler_mcp_server"]
            }
        }
    }
}
```

Or with custom URL:

```json
{
    "mcp": {
        "servers": {
            "crawler": {
                "command": "python",
                "args": ["-m", "crawler_mcp_server", "--base-url", "http://localhost:8001"]
            }
        }
    }
}
```

**Note:** Using `python -m crawler_mcp_server` ensures VS Code can find the command regardless of PATH settings. If you have multiple Python environments, use the full path to python.exe:

```json
{
    "mcp": {
        "servers": {
            "crawler": {
                "command": "C:/path/to/venv/Scripts/python.exe",
                "args": ["-m", "crawler_mcp_server"]
            }
        }
    }
}
```

## MCP Tools

The server exposes these tools to VS Code AI agents:

| Tool | Description |
|------|-------------|
| `crawler_health` | Check crawler service health |
| `crawler_crawl` | Crawl web pages with topic/query |
| `crawler_render` | Render JavaScript-heavy pages |
| `crawler_extract` | Extract content from HTML |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CRAWLER_MCP_BASE_URL` | Crawler service URL | `http://localhost:8001` |
| `CRAWLER_MCP_TIMEOUT_S` | Request timeout | `120` |

## Development

```bash
# Install in editable mode
pip install -e .

# Build wheel
python -m build --wheel
```

## Authentication

Authentication to internal sites is handled by the main LLMCrawl deployment.
Use the LLMCrawl CLI tools to configure authentication before running the crawler service.

## Architecture

```
VS Code + GitHub Copilot
    ↓ (MCP protocol)
crawler-mcp-server (this package)
    ↓ (HTTP)
LLMCrawl Crawler Service
    ↓
Firecrawl + Playwright + etc.
```

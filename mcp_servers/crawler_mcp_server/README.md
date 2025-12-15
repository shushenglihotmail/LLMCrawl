# Crawler MCP Server

A comprehensive MCP server for web crawling with:
- **MCP Tools**: Expose Firecrawl functionality to VS Code AI agents
- **Container Management**: Start/stop/restart Docker containers
- **Authentication**: Cookie-based auth for internal sites

## Crawler Stack

The Docker stack includes these containers:

| Container | Port | Description |
|-----------|------|-------------|
| **firecrawl** | 3002 | Web crawling engine (main API) |
| **playwright** | 3000 | Browser rendering for JS-heavy pages |
| **redis** | 6379 | Caching and rate limiting |
| **postgres** | 5432 | Database for firecrawl |

The MCP server connects directly to **Firecrawl** (port 3002) for crawling.

## Installation

### Basic (MCP client only)

```bash
pip install crawler-mcp-server
```

### With Authentication Support

```bash
pip install crawler-mcp-server[auth]
```

### All Features

```bash
pip install crawler-mcp-server[all]
```

## Commands

### Container Management

```bash
# Start all services
crawler-mcp-server start

# Start with rebuild
crawler-mcp-server start --build

# Stop services
crawler-mcp-server stop

# Restart specific service
crawler-mcp-server restart crawler

# Check status
crawler-mcp-server status

# View logs
crawler-mcp-server logs
crawler-mcp-server logs crawler --tail 50
```

### Authentication (for internal sites)

```bash
# Authenticate to internal site
crawler-mcp-server auth https://www.osgwiki.com/wiki/Main_Page

# With custom profile name
crawler-mcp-server auth https://internal.site.com --name my_site

# List saved credentials
crawler-mcp-server auth --list

# Clear credentials
crawler-mcp-server auth --clear
```

### MCP Server (for VS Code)

```bash
# Run MCP server (default when no command specified)
crawler-mcp-server mcp

# With custom crawler URL
crawler-mcp-server mcp --base-url http://localhost:8001
```

### Native Service (without Docker)

```bash
# Run crawler service natively
crawler-mcp-server serve --port 8001

# With auto-reload for development
crawler-mcp-server serve --reload
```

## MCP Tools

The server exposes these tools to VS Code AI agents:

| Tool | Description |
|------|-------------|
| `crawler_health` | Check crawler service health |
| `crawler_crawl` | Crawl web pages with topic/query |
| `crawler_render` | Render JavaScript-heavy pages |
| `crawler_extract` | Extract content from HTML |

## VS Code Integration

Add to your `settings.json` or `mcp.json`:

```json
{
    "mcp": {
        "servers": {
            "crawler": {
                "command": "crawler-mcp-server",
                "args": ["mcp"]
            }
        }
    }
}
```

Or with container auto-start:

```json
{
    "mcp": {
        "servers": {
            "crawler": {
                "command": "crawler-mcp-server",
                "args": ["mcp", "--base-url", "http://localhost:8001"]
            }
        }
    }
}
```

See `vscode-mcp-example.jsonc` for more examples.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CRAWLER_MCP_BASE_URL` | Crawler service URL | `http://localhost:8001` |
| `CRAWLER_MCP_TIMEOUT_S` | Request timeout | `120` |
| `LLMCRAWL_DEPLOY_DIR` | Deploy directory path | Auto-detected |
| `LLMCRAWL_AUTH_DIR` | Auth credentials directory | `.auth/` |

## Development

```bash
# Install in editable mode
pip install -e mcp_servers/crawler_mcp_server[dev]

# Build wheel
cd mcp_servers/crawler_mcp_server
python -m build --wheel
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                 crawler-mcp-server                       │
├─────────────────────────────────────────────────────────┤
│  CLI Commands                                            │
│  ├── start/stop/restart  → Docker Compose               │
│  ├── auth               → Browser-based cookie auth      │
│  ├── mcp                → MCP stdio server               │
│  └── serve              → Native FastAPI service         │
├─────────────────────────────────────────────────────────┤
│  MCP Tools (stdio)                                       │
│  └── crawler_crawl, crawler_render, crawler_extract     │
├─────────────────────────────────────────────────────────┤
│  HTTP Client → Crawler Service (Docker or Native)        │
└─────────────────────────────────────────────────────────┘
```

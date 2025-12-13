# MCP Servers

This directory contains Model Context Protocol (MCP) servers that extend the capabilities of the LLMCrawl system.

## Available Servers

### 1. Local Access MCP Server (`local_access_mcp_server/`)

MCP server for reading and indexing local files with semantic search capabilities.

**Features:**
- Secure file reading with path validation
- File indexing with LlamaIndex
- Semantic search across indexed files
- VS Code integration support

**Quick Links:**
- [Quick Start](local_access_mcp_server/QUICKSTART.md)
- [Full Documentation](local_access_mcp_server/README.md)
- [Integration Guide](local_access_mcp_server/INTEGRATION_GUIDE.md)

**Installation:**
```bash
# For development
pip install -e mcp_servers/local_access_mcp_server/

# For VS Code MCP integration
cd mcp_servers/local_access_mcp_server
pip install -e .
```

### 2. Azure DevOps MCP Server (`azure_devops_mcp_server/`)

MCP server for integrating with Azure DevOps repositories, enabling file reading and search across Azure DevOps projects.

**Features:**
- Azure DevOps Code Search integration
- Git Items API support for file listing
- PAT and OAuth authentication
- Branch-specific file access
- Wildcard pattern matching

**Quick Links:**
- [Quick Start](azure_devops_mcp_server/docs/QUICKSTART.md)
- [Full Documentation](azure_devops_mcp_server/docs/README.md)
- [Integration Guide](azure_devops_mcp_server/docs/INTEGRATION.md)

**Installation:**
```bash
# For development
pip install -e mcp_servers/azure_devops_mcp_server/

# For VS Code MCP integration
cd mcp_servers/azure_devops_mcp_server
pip install -e .
```

### 3. WCD Bridge MCP Server (`wcd_bridge_mcp_server/`)

MCP stdio server for the **Windows Composition Bridge**.

By default it starts an embedded bridge HTTP service and then runs the MCP server (single-command deployment). Use `--no-bridge` if you prefer to run the bridge separately.

**Features:**
- `wcd_query` forwards to the bridge `POST /query` endpoint (default `http://localhost:8005`)
- `wcd_health` forwards to `GET /health`

**Installation:**
```bash
pip install -e mcp_servers/wcd_bridge_mcp_server/
```

### 4. Crawler MCP Server (`crawler_mcp_server/`)

MCP stdio server that forwards calls to the existing **Crawler** service (default `http://localhost:8001`).

**Features:**
- `crawler_crawl` forwards to `POST /crawl`
- `crawler_render` forwards to `POST /render`
- `crawler_extract` forwards to `POST /extract`
- `crawler_health` forwards to `GET /health`

**Installation:**
```bash
pip install -e mcp_servers/crawler_mcp_server/
```

## Architecture

These MCP servers can be deployed:

1. **Standalone** - As independent services (Docker or local)
2. **VS Code Integration** - As MCP servers in VS Code's Copilot
3. **LLMCrawl Integration** - As part of the LLMCrawl gateway architecture

## Docker Deployment

Some servers are included in the main docker-compose configuration:

```bash
# Start all services including MCP servers
docker-compose -f deploy/docker-compose.yml up -d

# Start only local MCP server
docker-compose -f deploy/docker-compose.yml up -d mcp-server

# Start only Azure DevOps MCP server
docker-compose -f deploy/docker-compose.yml up -d azure-devops-mcp-server
```

## Development

For local development with hot-reload:

```bash
# Start dev environment
cd deploy && docker-compose up -d

# The local MCP server is mounted with volume for live updates
# Hot-reload is enabled by default in docker-compose.yml
```

## VS Code Integration

Each MCP server can be configured independently in VS Code:

1. Install the MCP server package
2. Add configuration to VS Code settings
3. Restart VS Code

See individual server documentation for detailed setup instructions.

For a consolidated guide (build/install + VS Code), see `docs/MCP_SERVERS.md`.

## Contributing

When adding new MCP servers:

1. Create a new directory under `mcp_servers/`
2. Include comprehensive README, QUICKSTART, and documentation
3. Ensure Docker support with Dockerfile
4. Add VS Code integration instructions
5. Update this README

## License

These MCP servers follow the main project license.

# Crawler MCP Server

This is a thin Model Context Protocol (MCP) server that exposes the existing LLMCrawl **Crawler** service as MCP tools.

It does **not** replace or change the crawler. It only forwards MCP tool calls to the crawler's existing HTTP API (typically running in Docker).

## What it connects to

- Existing service: `crawler/main.py` (FastAPI)
- Default base URL: `http://localhost:8001`
- Endpoints used:
  - `GET /health`
  - `POST /crawl`
  - `POST /render`
  - `POST /extract`

## Tools exposed

- `crawler_health`: returns `/health`
- `crawler_crawl`: forwards to `/crawl`
- `crawler_render`: forwards to `/render`
- `crawler_extract`: forwards to `/extract`

## Install (editable)

From repo root:

```bash
pip install -e mcp_servers/crawler_mcp_server
```

For deploying to another machine, prefer installing from a built wheel (see below).

## Build a wheel

```bash
cd mcp_servers/crawler_mcp_server
python -m pip install --upgrade build
python -m build --wheel
```

## Run (stdio MCP for VS Code)

```bash
python -m crawler_mcp_server --base-url http://localhost:8001
```

Environment variables:

- `CRAWLER_MCP_BASE_URL`: default base URL (overrides the default)

## VS Code integration

See `vscode-mcp-example.jsonc`.

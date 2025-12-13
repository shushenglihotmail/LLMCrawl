# WCD Bridge MCP Server

This is a Model Context Protocol (MCP) server that exposes the LLMCrawl **Windows Composition Bridge** as MCP tools.

By default it runs a self-contained deployment: an embedded bridge HTTP service plus the MCP stdio server that forwards to it. You can also run the bridge separately and launch the MCP server with `--no-bridge`.

## What it connects to

- Bridge API: compatible with `tools/windows_composition_bridge.py`
- Default base URL: `http://localhost:8005`
- Endpoints used:
  - `GET /health`
  - `POST /query` with JSON `{ "query": "<powershell script block>" }`

## Tools exposed

- `wcd_health`: returns the bridge `/health` payload
- `wcd_query`: runs a PowerShell script block through the bridge `/query`

## Install (editable)

From repo root:

```bash
pip install -e mcp_servers/wcd_bridge_mcp_server
```

For deploying to another machine, prefer installing from a built wheel (see below).

## Build a wheel

```bash
cd mcp_servers/wcd_bridge_mcp_server
python -m pip install --upgrade build
python -m build --wheel
```

The wheel will be created under `dist/`.

## Run (stdio MCP for VS Code)

```bash
python -m wcd_bridge_mcp_server
```

### Self-contained behavior (default)

When you run the module, it starts **both**:

- the Windows Composition Bridge HTTP service (default `http://127.0.0.1:8005`)
- the MCP stdio server (forwarding to that local bridge)

```powershell
$env:WIN_COMP_SHARE_CMD = "\\server\share\InteractViaPowerShell.cmd"
python -m wcd_bridge_mcp_server
```

Environment variables:

- `WCD_BRIDGE_URL`: default base URL (overrides the default)
- `WCD_BRIDGE_LISTEN_HOST`: embedded bridge bind host (default `127.0.0.1`)
- `WCD_BRIDGE_LISTEN_PORT`: embedded bridge bind port (default `8005`)

Advanced:

- `--no-bridge`: if you are running the bridge separately and only want the MCP server

## VS Code integration

See `vscode-mcp-example.jsonc`.

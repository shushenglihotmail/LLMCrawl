# MCP Servers

This document describes the Model Context Protocol (MCP) servers available in LLMCrawl, how to build/install them as separate wheels, and how to integrate them with VS Code.

## What “MCP server” means here

An MCP server exposes one or more **tools** over the MCP JSON-RPC protocol.

In LLMCrawl there are two patterns:

1. **Native MCP servers** that implement the tool logic directly (e.g., local file access, Azure DevOps).
2. **Wrapper MCP servers** that forward MCP tool calls to an existing HTTP service (e.g., Crawler, WCD Bridge).

Wrapper servers are intentionally thin so the underlying services can keep their current runtime format.

## Available MCP servers

### Local Access MCP Server

- Folder: `mcp_servers/local_access_mcp_server/`
- Purpose: local file operations (list/read) for tools and agents.

### Azure DevOps MCP Server

- Folder: `mcp_servers/azure_devops_mcp_server/`
- Purpose: search and read files from Azure DevOps repositories.

### WCD Bridge MCP Server (wrapper)

- Folder: `mcp_servers/wcd_bridge_mcp_server/`
- Purpose: expose the Windows Composition Bridge as MCP tools.
- Default bridge URL: `http://localhost:8005`
- Tools:
  - `wcd_health`
  - `wcd_query`

### Crawler MCP Server (wrapper)

- Folder: `mcp_servers/crawler_mcp_server/`
- Purpose: expose the LLMCrawl crawler service as MCP tools for VS Code agents.
- Default crawler URL: `http://localhost:8001`
- Tools:
  - `crawler_health` – check crawler service status
  - `crawler_crawl` – crawl web pages by query (params: `query`, `freshness_days`, `depth`, `max_results`)
  - `crawler_render` – render a page using Playwright
  - `crawler_extract` – extract clean text from HTML using Trafilatura

The wheel package includes:
- MCP stdio server for VS Code integration
- CLI for container management (`start`, `stop`, `restart`, `status`, `logs`)
- Bundled `docker-compose.crawler.yml`, `Dockerfile.crawler`, and `requirements.crawler.txt`
- Browser-based authentication module for internal sites

## Building each MCP server as a separate wheel

Each MCP server under `mcp_servers/` is intended to be buildable and installable independently.

Prerequisite (only if your environment doesn’t already have it):

```bash
python -m pip install --upgrade build
```

Then build a wheel for any server:

```bash
cd mcp_servers/<server_dir>
python -m build --wheel
```

This produces a wheel under `mcp_servers/<server_dir>/dist/`.

### Does `python -m build --wheel` at repo root build all MCP wheels?

No. Running `python -m build` from the repository root only builds the **root** project (LLMCrawl). It does not automatically recurse into `mcp_servers/*`.

To build MCP server wheels, run the build command inside each MCP server folder (or script a loop).

Example PowerShell loop from repo root:

```powershell
Get-ChildItem mcp_servers -Directory |
  Where-Object { Test-Path (Join-Path $_.FullName 'pyproject.toml') } |
  ForEach-Object {
    Push-Location $_.FullName
    python -m build --wheel
    Pop-Location
  }
```

## Installing MCP servers

### Install from wheel (recommended for deploying to other machines)

Copy the wheel file to the target machine and install it:

```bash
pip install <wheel_file>.whl
```

Example (from repo build output):

```bash
pip install mcp_servers/<server_dir>/dist/<wheel_file>.whl
```

If the target machine has no internet access, you’ll also need the dependency wheels (e.g. `httpx`) available locally and install with something like:

```bash
pip install --no-index --find-links <folder_with_wheels> <wheel_file>.whl
```

### Editable install (optional; development only)

```bash
pip install -e mcp_servers/<server_dir>
```

Editable installs are convenient when developing in this repo, but they are not required for deployment.

## VS Code integration

VS Code MCP servers are typically configured using a JSON file:

- Windows: `%APPDATA%\Code\User\mcp.json`
- macOS: `~/Library/Application Support/Code/User/mcp.json`
- Linux: `~/.config/Code/User/mcp.json`

Each server entry runs a command in **stdio** mode (stdin/stdout transport).

### WCD Bridge MCP Server (VS Code)

Default behavior: **self-contained** (no separate host step). When launched, it starts:

- an embedded Windows Composition Bridge HTTP service (default `http://127.0.0.1:8005`)
- the MCP stdio server (forwarding to that embedded bridge)

#### Option 1: Using network share path (--win-comp-path)

Use this when you have access to the Windows build release share:

```powershell
python -m wcd_bridge_mcp_server --win-comp-path "\\winbuilds\release\rs_sparc_ctr_exp\29498.1001.251201-1700" --arch amd64fre
```

The `--win-comp-path` argument constructs the full path as:
`<path>/<arch>/WindowsCompositionData/SDK/InteractViaPowerShell.cmd`

VS Code config example:

```jsonc
{
  "inputs": [],
  "servers": {
    "llmcrawl-wcd-bridge": {
      "command": "C:/Path/To/python.exe",
      "args": [
        "-m", "wcd_bridge_mcp_server",
        "--win-comp-path", "\\\\winbuilds\\release\\rs_sparc_ctr_exp\\29498.1001.251201-1700",
        "--arch", "amd64fre"
      ],
      "type": "stdio"
    }
  }
}
```

#### Option 2: Using WCDaaS local download (--use-wcdaas-local)

Use this when the network share is not accessible. WCDaaS (WCD-as-a-Service) downloads the tools locally and loads the database from the cloud.

**Step 1:** Run the WCDaaS URL in a browser to download the tools (one-time setup):

```
https://wcdaas-pme.azurewebsites.net/default.aspx?action=wcd&branch=rs_sparc_ctr_exp&buildName=29503.1000.251209-1700&arch=amd64
```

This authenticates and downloads WCD tools to `%LOCALAPPDATA%\Temp\wcdaas\<GUID>\`.

**Step 2:** Start the MCP server with `--use-wcdaas-local`:

```powershell
python -m wcd_bridge_mcp_server --use-wcdaas-local --branch rs_sparc_ctr_exp --build-name 29503.1000.251209-1700 --arch amd64
```

**Arguments for WCDaaS local mode:**

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--use-wcdaas-local` | Yes | - | Enable WCDaaS local mode |
| `--build-name` | Yes | - | Build name (e.g., `29503.1000.251209-1700`) |
| `--branch` | No | `rs_sparc_ctr_exp` | Branch name |
| `--arch` | No | `amd64fre` | Architecture (`amd64fre`, `arm64fre`, etc.) |
| `--wcdaas-folder` | No | (most recent) | Specific GUID folder to use |

VS Code config example:

```jsonc
{
  "inputs": [],
  "servers": {
    "llmcrawl-wcd-bridge": {
      "command": "C:/Path/To/python.exe",
      "args": [
        "-m", "wcd_bridge_mcp_server",
        "--use-wcdaas-local",
        "--branch", "rs_sparc_ctr_exp",
        "--build-name", "29503.1000.251209-1700",
        "--arch", "amd64"
      ],
      "type": "stdio"
    }
  }
}
```

**Note:** The downloaded WCDaaS tools are identical for all builds. The `--branch`, `--build-name`, and `--arch` parameters determine which database is loaded from the cloud at runtime.

#### Option 3: Using WIN_COMP_SHARE_CMD environment variable

Alternatively, set the full path directly via environment variable:

```jsonc
{
  "inputs": [],
  "servers": {
    "llmcrawl-wcd-bridge": {
      "command": "C:/Path/To/python.exe",
      "args": ["-m", "wcd_bridge_mcp_server"],
      "env": {
        "WIN_COMP_SHARE_CMD": "\\\\server\\share\\amd64fre\\WindowsCompositionData\\SDK\\InteractViaPowerShell.cmd"
      },
      "type": "stdio"
    }
  }
}
```

#### Running bridge separately (advanced)

If you want to run the bridge separately, start it yourself and run the MCP server with `--no-bridge`:

```powershell
$env:WIN_COMP_SHARE_CMD = "\\server\share\InteractViaPowerShell.cmd"
python tools\windows_composition_bridge.py
python -m wcd_bridge_mcp_server --no-bridge --base-url http://localhost:8005
```

### Azure DevOps MCP Server (VS Code)

Prerequisite: install the Azure DevOps MCP server in the Python environment that VS Code will use to launch MCP servers.

Wheel-first install (recommended for deploying to other machines):

```bash
cd mcp_servers/azure_devops_mcp_server
python -m build --wheel
pip install dist/azure_devops_mcp_server-*.whl
```

On another machine, copy `dist/azure_devops_mcp_server-*.whl` to the target and install it:

```bash
pip install azure_devops_mcp_server-*.whl
```

Example `mcp.json` entry (PAT auth):

```jsonc
{
  "inputs": [],
  "servers": {
    "llmcrawl-azure-devops": {
      "command": "C:/Path/To/python.exe",
      "args": [
        "-m",
        "azure_devops_client",
        "--mode",
        "stdio",
        "--organization",
        "<org>",
        "--project",
        "<project>",
        "--repository",
        "<repo>",
        "--branch",
        "<branch>",
        "--auth-mode",
        "pat"
      ],
      "env": {
        "AZURE_DEVOPS_PAT": "<your_pat>"
      },
      "type": "stdio"
    }
  }
}
```

Notes:

- The module is `azure_devops_client` (the package supports `--mode stdio` for VS Code).
- Prefer keeping secrets like `AZURE_DEVOPS_PAT` in environment variables rather than hardcoding them in files.

### Crawler MCP Server (VS Code)

The Crawler MCP Server is a self-contained wheel package that includes both the MCP server and container management tools.

#### Building and Installing

```bash
cd mcp_servers/crawler_mcp_server
python -m build --wheel
pip install dist/crawler_mcp_server-*.whl
```

#### Starting the Crawler Service

The wheel includes a CLI to manage the crawler Docker stack:

```bash
# Start all crawler services (postgres, redis, playwright, firecrawl, crawler)
crawler-mcp-server start

# Check service status
crawler-mcp-server status

# View logs
crawler-mcp-server logs

# Stop services
crawler-mcp-server stop

# Restart services
crawler-mcp-server restart
```

The `start` command uses the bundled `docker-compose.crawler.yml` which starts:
- **postgres** (5432) – database for Firecrawl
- **redis** (6379) – caching/rate limiting
- **playwright** (3000) – browser rendering via Browserless
- **firecrawl** (3002) – web crawling engine
- **crawler** (8001) – LLMCrawl crawler service (the MCP server connects here)

#### Alternative: Using dev environment

If you're working in the LLMCrawl repo, you can also start the crawler via:

```bash
make dev-up
```

Or start only crawler-related services:

```bash
docker compose -f deploy/docker-compose.dev.yml up -d crawler firecrawl playwright redis postgres
```

#### VS Code MCP Configuration

Once the crawler service is running, add this to your VS Code `mcp.json`:

```jsonc
{
  "inputs": [],
  "servers": {
    "llmcrawl-crawler": {
      "command": "C:/Path/To/python.exe",
      "args": ["-m", "crawler_mcp_server", "mcp"],
      "type": "stdio"
    }
  }
}
```

To use a different crawler URL (e.g., remote host):

```jsonc
{
  "inputs": [],
  "servers": {
    "llmcrawl-crawler": {
      "command": "C:/Path/To/python.exe",
      "args": ["-m", "crawler_mcp_server", "mcp", "--base-url", "http://remote-host:8001"],
      "type": "stdio"
    }
  }
}
```

#### Authentication for Internal Sites

To crawl internal sites that require authentication:

```bash
# Launch browser for SSO authentication and capture cookies
crawler-mcp-server auth https://internal-site.example.com
```

This opens a browser window where you can log in. After authentication, cookies are saved and used for subsequent crawl requests.

## Notes / troubleshooting

- `crawler_mcp_server` requires the crawler service to be running. Use `crawler-mcp-server start` to start it, or check status with `crawler-mcp-server status`.
- `wcd_bridge_mcp_server` starts an embedded bridge by default; use `--no-bridge` only if you run the bridge separately.
- If your service is not on localhost (remote host, WSL2, different port), set `--base-url` accordingly.
- For crawler container issues, check logs with `crawler-mcp-server logs` or `docker compose logs`.

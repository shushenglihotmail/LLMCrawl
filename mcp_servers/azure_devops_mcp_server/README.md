# Azure DevOps MCP Server

A Model Context Protocol (MCP) server for searching code and retrieving files from Azure DevOps repositories. Uses the Azure DevOps Code Search API directly for fast indexed search.

## Features

- **Code Search**: Search using Azure DevOps Code Search API syntax
- **File Retrieval**: Get content of specific files
- **PAT Authentication**: Personal Access Token authentication
- **Dual Transport**: Supports both stdio (VS Code) and HTTP (LLMCrawl)

## Available Tools

### 1. `search_azure_devops_code`

Search for code/files using Azure DevOps Code Search API. The `search_text` is passed directly to the API.

**Search Syntax:**
- File Extension: `ext:xml` or `mySearchTerm ext:cpp`
- File Name: `file:config` or `file:*config.xml`
- Path keyword: `mySearchTerm path:Services`
- Boolean Logic: `mySearchTerm AND NOT ext:json`
- Code Element: `class:MyClass` or `func:MyFunction`
- Aggregate: `(term1 OR term2) ext:xml`

**Parameters:**
- `search_text` (required): Search query using Azure DevOps syntax
- `path`: Path scope to limit search (e.g., "/src", "/vm/compute")
- `max_results`: Maximum results (default: 20)
- `branch`: Branch name (default: configured branch)

### 2. `get_azure_devops_file`

Retrieve the full content of a file from the repository.

**Parameters:**
- `file_path` (required): Absolute path to file (must start with `/`)
- `branch`: Branch name (default: repository default)

## URI Format for HiChat

Use the `azdo://` URI format:

```
azdo:/path:searchText?branch=branchName
```

Examples:
- `azdo:/:ext:xml` - Find all XML files
- `azdo:/onecore/vm/compute:HCS ext:md` - Find HCS docs in compute folder
- `azdo:/src:file:*config*.json` - Find config files in src

## Configuration

### Environment Variables

```bash
AZURE_DEVOPS_ORG=microsoft
AZURE_DEVOPS_PROJECT=OS
AZURE_DEVOPS_REPO=os.2020
AZURE_DEVOPS_BRANCH=official/rs_sparc_ctr_exp
AZURE_DEVOPS_PAT=your_personal_access_token
HTTP_PORT=8004
```

### VS Code Configuration

Add to `mcp.json` in `%APPDATA%\Code\User\`:

```json
{
  "servers": {
    "azure-devops": {
      "command": "C:\\path\\to\\python.exe",
      "args": [
        "-m", "azure_devops_client",
        "--mode", "stdio",
        "--organization", "microsoft",
        "--project", "OS",
        "--repository", "os.2020",
        "--auth-mode", "pat"
      ],
      "env": {
        "AZURE_DEVOPS_PAT": "YOUR_PAT_TOKEN"
      },
      "type": "stdio"
    }
  }
}
```

## Quick Start

```bash
# Install
cd azure_devops_mcp_server
pip install -e .

# Set PAT
$env:AZURE_DEVOPS_PAT = "your_pat_token"

# Run HTTP mode
python -m azure_devops_client --mode http --port 8004

# Test
curl http://localhost:8004/health
curl http://localhost:8004/tools
```

## Docker Setup

```yaml
azure-devops-mcp-server:
  build:
    context: ./mcp_servers/azure_devops_mcp_server
  ports:
    - "8004:8004"
  environment:
    - AZURE_DEVOPS_PAT=${AZURE_DEVOPS_PAT}
```

## Architecture

```
HiChat/VS Code -> Gateway (8000) -> Azure DevOps MCP (8004) -> Code Search API
```

## Search API

- **Endpoint**: `https://almsearch.dev.azure.com/{org}/_apis/search/codesearchresults`
- **Performance**: ~1 second for indexed searches

See: https://learn.microsoft.com/en-us/rest/api/azure/devops/search/code-search-results

## Troubleshooting

- **Auth Failed**: Check PAT is valid and has "Code (Read)" scope
- **No Results**: Verify search syntax and path exists
- **Timeout**: Check network connectivity to Azure DevOps

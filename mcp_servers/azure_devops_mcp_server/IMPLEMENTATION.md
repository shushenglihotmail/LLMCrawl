# Azure DevOps MCP Server - Implementation

## Overview

Simplified Azure DevOps MCP server that uses the Code Search API directly for fast indexed search.

## Architecture

```
Client (HiChat/VS Code)
         |
    Gateway (8000)
         |
Azure DevOps MCP (8004)
         |
   Code Search API
(almsearch.dev.azure.com)
```

## Core Files

### `azure_client.py`
- `AzureDevOpsClient` class
- PAT authentication only (interactive auth removed)
- `search_code()` - Passes search_text directly to Code Search API
- `get_file_content()` - Retrieves file via Git Items API
- `test_connection()` - Tests API connectivity

### `server.py`
- `AzureDevOpsMCPServer` class
- Two tools: `search_azure_devops_code`, `get_azure_devops_file`
- JSON-RPC message handling for stdio mode
- Tool definitions with Azure search syntax examples

### `http_server.py`
- FastAPI HTTP server for LLMCrawl integration
- Endpoints: `/health`, `/tools`, `/invoke`

## Tools

### search_azure_devops_code
Passes `search_text` directly to Azure DevOps Code Search API.

Search syntax (Azure DevOps native):
- `ext:xml` - File extension
- `file:*config*` - File name pattern
- `path:Services` - Path contains
- `class:MyClass` - Code element
- `AND`, `OR`, `NOT` - Boolean operators

### get_azure_devops_file
Retrieves file content via Git Items API.

## URI Format

For HiChat integration:
```
azdo:/path:searchText?branch=branchName
```

Parsed by `azdo_uri.py`:
- path: Folder scope for search
- searchText: Passed to Code Search API
- branch: Optional branch override

## API Endpoints

### Code Search API
```
POST https://almsearch.dev.azure.com/{org}/_apis/search/codesearchresults
API Version: 6.0-preview.1
```

### Git Items API
```
GET https://dev.azure.com/{org}/{project}/_apis/git/repositories/{repo}/items
API Version: 7.0
```

## Authentication

PAT only (Personal Access Token):
- Set via `AZURE_DEVOPS_PAT` environment variable
- Requires "Code (Read)" scope
- Basic auth with empty username

## Configuration

| Variable | Description |
|----------|-------------|
| `AZURE_DEVOPS_ORG` | Organization name |
| `AZURE_DEVOPS_PROJECT` | Project name |
| `AZURE_DEVOPS_REPO` | Repository name |
| `AZURE_DEVOPS_BRANCH` | Default branch |
| `AZURE_DEVOPS_PAT` | Personal Access Token |
| `HTTP_PORT` | HTTP server port (default: 8004) |

## Recent Changes

- Removed interactive OAuth/MSAL authentication
- Removed `search_files()` method (consolidated into `search_code()`)
- Simplified to PAT-only authentication
- Search text passed directly to Azure API (no client-side processing)
- New URI format: `azdo:/path:searchText`

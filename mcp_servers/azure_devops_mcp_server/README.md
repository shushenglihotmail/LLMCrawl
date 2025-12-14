# Azure DevOps MCP Server

An MCP (Model Context Protocol) server for Azure DevOps code search and file retrieval.

## Features

- **Code Search**: Search for code in Azure DevOps repositories using the Code Search API
- **File Retrieval**: Get file content from repositories
- **Dual Mode**: Supports both stdio (VS Code) and HTTP modes

## Installation

### From wheel (recommended)

```bash
cd mcp_servers/azure_devops_mcp_server
python -m build --wheel
pip install dist/azure_devops_mcp_server-*.whl
```

### Editable install (development)

```bash
pip install -e mcp_servers/azure_devops_mcp_server
```

## Usage

### VS Code Integration (stdio mode)

Add to your VS Code MCP configuration (`%APPDATA%\Code\User\mcp.json`):

```jsonc
{
  "servers": {
    "azure-devops": {
      "command": "python",
      "args": [
        "-m", "azure_devops_client",
        "--mode", "stdio",
        "--organization", "your-org",
        "--project", "your-project",
        "--repository", "your-repo",
        "--branch", "main",
        "--auth-mode", "pat",
        "--pat", "YOUR_PAT_TOKEN"
      ],
      "type": "stdio"
    }
  }
}
```

### HTTP Mode

```bash
python -m azure_devops_client --mode http --port 8004
```

## Authentication

### Personal Access Token (PAT)

1. Go to Azure DevOps → User Settings → Personal Access Tokens
2. Create a new token with **Code (Read)** and **Project and Team (Read)** scopes
3. Use `--auth-mode pat --pat YOUR_TOKEN` or set `AZURE_DEVOPS_PAT` environment variable

## Available Tools

- `search_azure_devops_code`: Search for code/files using Azure DevOps Code Search API
- `get_azure_devops_file`: Get file content from a repository
- `list_azure_devops_files`: List files in a repository path

## License

MIT

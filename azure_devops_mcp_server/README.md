# Azure DevOps MCP Server

A Model Context Protocol (MCP) server for querying files from Azure DevOps repositories. This server provides code search and file retrieval capabilities that can be used by:

- VS Code Copilot (via MCP stdio transport)
- LLMCrawl Gateway (via HTTP REST API)
- Any MCP-compatible client

## Features

- **File Search**: Flexible file search with path patterns, file patterns, extensions, and keywords
- **File Retrieval**: Fetch file contents from specific paths
- **Smart Filtering**: Support for glob patterns (**, *), wildcards, and complex queries
- **Safe by Default**: Non-recursive search at root level, opt-in for deep searches
- **Interactive Authentication**: Browser-based OAuth flow for Azure DevOps
- **PAT Support**: Personal Access Token authentication
- **Dual Transport**: Supports both stdio (for VS Code) and HTTP (for LLMCrawl)
- **Command-Line Testing**: Standalone test utility for quick queries

## Installation

### Standalone Installation

```bash
cd azure_devops_mcp_server
pip install -e .
```

### Docker Installation

```bash
docker build -t azure-devops-mcp-server .
docker run -p 8004:8004 azure-devops-mcp-server
```

## Configuration

Create a `.env` file or set environment variables:

```env
# Azure DevOps Configuration
AZURE_DEVOPS_ORG=microsoft
AZURE_DEVOPS_PROJECT=OS
AZURE_DEVOPS_REPO=os.2020
AZURE_DEVOPS_BRANCH=official/rs_sparc_ctr_exp  # Optional, defaults to repository default

# Authentication (choose one)
AZURE_DEVOPS_PAT=your_personal_access_token
# OR use interactive auth (will prompt for browser login)

# Server Configuration
SERVER_MODE=http  # 'stdio' for VS Code, 'http' for LLMCrawl
HTTP_PORT=8004
AZURE_DEVOPS_MAX_RESULTS=50  # Default max results per query
```

## Usage

### As VS Code MCP Server (stdio mode)

Add to your VS Code settings (`.vscode/settings.json` or `settings.json`):

```json
{
  "mcp.servers": {
    "azure-devops": {
      "command": "python",
      "args": ["-m", "azure_devops_mcp_server"],
      "env": {
        "AZURE_DEVOPS_ORG": "microsoft",
        "AZURE_DEVOPS_PROJECT": "OS",
        "AZURE_DEVOPS_REPO": "os.2020",
        "SERVER_MODE": "stdio"
      }
    }
  }
}
```

### As HTTP Server for LLMCrawl

```bash
# Start the server
python -m azure_devops_mcp_server --mode http --port 8004

# Or with Docker
docker run -p 8004:8004 \
  -e AZURE_DEVOPS_ORG=microsoft \
  -e AZURE_DEVOPS_PROJECT=OS \
  -e AZURE_DEVOPS_REPO=os.2020 \
  azure-devops-mcp-server
```

### Programmatic Usage

```python
from azure_devops_mcp_server.azure_client import AzureDevOpsClient

# Create client instance
client = AzureDevOpsClient(
    organization="microsoft",
    project="OS",
    repository="os.2020",
    pat="your_pat_token",  # or None for interactive auth
    branch="official/rs_sparc_ctr_exp",  # optional
    max_results=50
)

# Authenticate
await client.authenticate(use_interactive=False)

# Search for files (non-recursive by default - safe for large repos)
results = await client.search_files(
    extension="json",
    max_results=10
)

# Search in specific path
results = await client.search_files(
    path_pattern="src/MergedComponents",
    extension="cpp",
    max_results=20
)

# Deep recursive search with glob patterns
results = await client.search_files(
    path_pattern="**/test/**",
    file_pattern="*test*.cpp",
    recursive=True,  # Explicit opt-in for recursion
    max_results=50
)

# Keyword search in file content (requires recursive=True)
results = await client.search_files(
    extension="json",
    keyword="Azure",
    recursive=True,
    max_results=10
)

# Get file content
content = await client.get_file_content(
    file_path=".gitignore",
    branch="official/rs_sparc_ctr_exp"
)
print(content["content"])
```

## API Endpoints (HTTP Mode)

### GET /health
Health check endpoint.

### GET /tools
Returns available MCP tools in OpenAI function calling format.

### POST /invoke
Execute a tool with arguments.

**Example 1: Search for files**
```json
{
  "tool_name": "search_azure_devops_files",
  "arguments": {
    "extension": "json",
    "max_results": 10
  }
}
```

**Example 2: Get file content**
```json
{
  "tool_name": "get_azure_devops_file",
  "arguments": {
    "file_path": ".gitignore"
  }
}
```

**Example 3: Deep search**
```json
{
  "tool_name": "search_azure_devops_files",
  "arguments": {
    "path_pattern": "**/test/**",
    "extension": "cpp",
    "recursive": true,
    "max_results": 20
  }
}
```

### POST /auth/interactive
Initiate interactive OAuth authentication flow.

## MCP Tools

The server provides three main tools accessible via MCP protocol:

### 1. search_azure_devops_files

**NEW**: Flexible file search with multiple filter types. **Safe by default** - searches only root directory unless `recursive=true`.

**Parameters:**
- `path_pattern` (string, optional): Path filter pattern
  - Examples: `"src/"`, `"src/MergedComponents"`, `"**/test/**"` (requires recursive=true)
  - Supports glob patterns: `**` (any depth), `*` (any chars), `?` (single char)
- `file_pattern` (string, optional): File name pattern (matches filename only, not path)
  - Examples: `"azure-pipelines*"`, `"*test*"`, `"README.md"`
  - Supports wildcards: `*` and `?`
- `extension` (string, optional): File extension filter
  - Examples: `"yml"`, `"json"`, `"cpp"`, `"cs"`
- `keyword` (string, optional): Search in file content (requires recursive=true)
  - Examples: `"Azure"`, `"connection timeout"`, `"Http*Request"`
  - Note: Searches first 100 matching files for performance
- `branch` (string, optional): Branch name (default: configured branch or repository default)
- `max_results` (integer, optional): Maximum results (default: 50)
- `recursive` (boolean, optional): Search subdirectories recursively (default: false)
  - ⚠️ Set to `true` for deep searches in large repos (slower but thorough)

**Examples:**

```json
// List root files
{
  "tool_name": "search_azure_devops_files",
  "arguments": {}
}

// Search YAML files at root
{
  "tool_name": "search_azure_devops_files",
  "arguments": {
    "extension": "yml"
  }
}

// Search in specific path (non-recursive)
{
  "tool_name": "search_azure_devops_files",
  "arguments": {
    "path_pattern": "src/MergedComponents",
    "extension": "json"
  }
}

// Deep recursive search
{
  "tool_name": "search_azure_devops_files",
  "arguments": {
    "path_pattern": "**/test/**",
    "extension": "cpp",
    "recursive": true
  }
}

// Search with file pattern
{
  "tool_name": "search_azure_devops_files",
  "arguments": {
    "file_pattern": "azure-pipelines*",
    "extension": "yml",
    "recursive": true
  }
}

// Keyword search in content (requires recursive)
{
  "tool_name": "search_azure_devops_files",
  "arguments": {
    "extension": "json",
    "keyword": "Azure",
    "recursive": true,
    "max_results": 10
  }
}
```

**Response:**
```json
{
  "success": true,
  "filters": {
    "path_pattern": "src/",
    "extension": "cpp",
    "recursive": false
  },
  "results_count": 5,
  "results": [
    {
      "path": "src/main.cpp",
      "name": "main.cpp",
      "size": 1234,
      "objectId": "abc123...",
      "url": "https://dev.azure.com/..."
    }
  ]
}
```

### 2. get_azure_devops_file

Retrieve the full content of a specific file from the repository.

**Parameters:**
- `file_path` (string, required): Path to the file in repository
  - Examples: `".gitignore"`, `"src/main.cpp"`, `"docs/README.md"`
- `branch` (string, optional): Branch name (default: repository default)

**Examples:**

```json
// Get file from root
{
  "tool_name": "get_azure_devops_file",
  "arguments": {
    "file_path": ".gitignore"
  }
}

// Get file from specific path
{
  "tool_name": "get_azure_devops_file",
  "arguments": {
    "file_path": "src/MergedComponents/config.json"
  }
}

// Get file from specific branch
{
  "tool_name": "get_azure_devops_file",
  "arguments": {
    "file_path": "README.md",
    "branch": "main"
  }
}
```

**Response:**
```json
{
  "success": true,
  "file_path": ".gitignore",
  "branch": "official/rs_sparc_ctr_exp",
  "content": "# Git ignore file content...",
  "content_type": "text/plain",
  "size": 5932
}
```

### 3. search_azure_devops_code

**Legacy**: Search for code using Azure DevOps Search API (requires Search service to be enabled).

**Parameters:**
- `query` (string, required): Search query
- `file_type` (string, optional): Filter by file extension (e.g., "*.cpp", "*.h")
- `max_results` (number, optional): Maximum results (default: 20)

**Note**: This tool requires Azure DevOps Search service. If Search is not enabled, use `search_azure_devops_files` instead.

## Authentication Methods

### Interactive Authentication (Recommended)
The server will open a browser window for you to sign in with your Microsoft account.

```bash
python -m azure_devops_mcp_server --mode http --auth interactive
```

### Personal Access Token (PAT)
Generate a PAT from Azure DevOps with "Code (Read)" permission:
1. Go to https://dev.azure.com/{organization}/_usersSettings/tokens
2. Create new token with "Code (Read)" scope
3. Set `AZURE_DEVOPS_PAT` environment variable

```bash
export AZURE_DEVOPS_PAT=your_pat_token
python -m azure_devops_mcp_server --mode http
```

## Integration with LLMCrawl

Add to `docker-compose.yml`:

```yaml
services:
  azure-devops-mcp:
    build: ./azure_devops_mcp_server
    environment:
      - AZURE_DEVOPS_ORG=microsoft
      - AZURE_DEVOPS_PROJECT=OS
      - AZURE_DEVOPS_REPO=os.2020
      - SERVER_MODE=http
      - HTTP_PORT=8004
    ports:
      - "8004:8004"
    volumes:
      - ./data/azure_devops_cache:/data/cache
```

Update gateway environment:
```env
AZURE_DEVOPS_MCP_URL=http://azure-devops-mcp:8004
```

## Security Considerations

- **Never commit PAT tokens** to version control
- Use interactive auth in development
- Use PAT with minimal required scopes in production
- Consider using Azure Key Vault for token storage in production
- Restrict network access to MCP server in production

## Troubleshooting

### Authentication Failures
```bash
# Clear cached credentials
rm -rf ~/.azure/mcp_cache

# Test authentication
python -m azure_devops_mcp_server --test-auth
```

### Connection Issues
```bash
# Test connectivity
curl http://localhost:8004/health

# View logs
docker logs azure-devops-mcp-server
```

## Testing and Development

### Command-Line Test Tool

The `tests/test_search.py` utility provides a command-line interface for testing file search and retrieval:

```bash
cd azure_devops_mcp_server/tests

# Set your PAT
export AZURE_DEVOPS_PAT=your_pat_token  # Linux/Mac
$env:AZURE_DEVOPS_PAT = "your_pat_token"  # PowerShell

# Search examples
python test_search.py --filter "ext:json"
python test_search.py --path /src/MergedComponents --filter "Azure ext:json"
python test_search.py --filter "file:*.cpp" --recursive
python test_search.py --path /src --filter "ext:yml" --recursive --max-results 10

# Get file content
python test_search.py --get-file ".gitignore"
python test_search.py --get-file "src/main.cpp" --max-lines 50
python test_search.py --get-file "README.md" --branch main

# Advanced options
python test_search.py --filter "ext:cs" --verbose
python test_search.py --organization your-org --project your-project --filter "ext:yml"
```

**Test Tool Options:**
- `--filter`: Filter string (e.g., `"Azure ext:json"`, `"file:*.cpp"`)
- `--path`: Path pattern (e.g., `/src/MergedComponents`, `**/test/**`)
- `--get-file`: Get content of specific file
- `--recursive`: Search subdirectories (default: false for safety)
- `--max-results`: Limit results (default: 50)
- `--max-lines`: Limit file content display lines
- `--branch`: Branch name (default: `official/rs_sparc_ctr_exp`)
- `--verbose`, `-v`: Show detailed information
- `--organization`: Azure DevOps organization (default: microsoft)
- `--project`: Project name (default: OS)
- `--repository`: Repository name (default: os.2020)

See `tests/README.md` for more examples and filter syntax details.

### Development Setup

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Format code
black .
isort .

# Type checking
mypy azure_devops_mcp_server/
```

## Filter Syntax Guide

### Path Patterns
- `src/` - Files in src directory (root level only)
- `src/MergedComponents` - Files in specific path
- `**/test/**` - Files in any test directory (requires recursive=true)
- `**/*.yml` - All YAML files anywhere (requires recursive=true)

### File Patterns
- `file:*.cpp` - All C++ files
- `file:azure-*` - Files starting with "azure-"
- `file:*test*` - Files containing "test"
- `file:README.md` - Exact filename match

### Extensions
- `ext:json` - All JSON files
- `ext:yml` - All YAML files
- `ext:cpp` - All C++ files

### Keywords (requires recursive=true)
- `"Azure"` - Files containing "Azure"
- `"connection timeout"` - Phrase search
- `"Http*Request"` - With wildcards

### Combining Filters
Filters work with AND logic:
- `path:src/ ext:cpp` - C++ files in src directory
- `file:*test* ext:cpp recursive:true` - Test C++ files anywhere
- `ext:json keyword:Azure recursive:true` - JSON files containing "Azure"

## License

MIT License - See LICENSE file for details

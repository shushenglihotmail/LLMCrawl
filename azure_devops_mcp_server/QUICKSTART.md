# Azure DevOps MCP Server - Quick Start Guide

## Installation

### From Source

```bash
cd azure_devops_mcp_server
pip install -e .
```

## Quick Testing

Before integrating with VS Code or LLMCrawl, test the server with the command-line tool:

```bash
cd azure_devops_mcp_server/tests

# Set your PAT token
export AZURE_DEVOPS_PAT=your_pat_token  # Linux/Mac
$env:AZURE_DEVOPS_PAT = "your_pat_token"  # PowerShell

# List files at root
python test_search.py --filter "ext:txt"

# Get file content
python test_search.py --get-file ".gitignore" --max-lines 20

# Search in specific path
python test_search.py --path /src --filter "ext:yml" --max-results 10

# See all options
python test_search.py --help
```

See `tests/README.md` for detailed examples and filter syntax.

## Usage

### 1. VS Code MCP Integration (stdio mode)

**Step 1: Configure VS Code**

Copy `vscode-settings.example.json` to your workspace `.vscode/settings.json`:

```json
{
  "mcpServers": {
    "azure-devops": {
      "command": "python",
      "args": [
        "-m",
        "azure_devops_mcp_server",
        "--mode",
        "stdio",
        "--organization",
        "microsoft",
        "--project",
        "OS",
        "--repository",
        "os.2020",
        "--auth-mode",
        "interactive"
      ]
    }
  }
}
```

**Step 2: Start Using**

When you open VS Code with Copilot, the Azure DevOps MCP server will:
1. Automatically launch in stdio mode
2. Prompt for interactive authentication (browser OAuth)
3. Cache credentials for future use
4. Make tools available to Copilot

**Available Tools:**
- `search_azure_devops_files` - Search files with flexible filters (path, file pattern, extension, keyword)
- `get_azure_devops_file` - Get specific file content
- `search_azure_devops_code` - Legacy code search (requires Azure DevOps Search service)

**Example Prompts:**
- "List all YAML files in the OS repository"
- "Search for JSON files in src/MergedComponents"
- "Show me the .gitignore file from the OS repository"
- "Find all C++ files in test directories"
- "Search for files containing 'Azure' in JSON files"

### 2. LLMCrawl Integration (HTTP mode)

**Step 1: Add to docker-compose.yml**

The service is already added in `deploy/docker-compose.yml`:

```yaml
azure-devops-mcp-server:
  build:
    context: ../azure_devops_mcp_server
    dockerfile: Dockerfile
  ports:
    - "8004:8004"
  environment:
    - MCP_MODE=http
    - AZURE_DEVOPS_PAT=${AZURE_DEVOPS_PAT}
```

**Step 2: Set Environment Variable**

Add to `.env` file:

```bash
AZURE_DEVOPS_PAT=your-personal-access-token
```

**Step 3: Start Services**

```bash
cd deploy
docker-compose up -d azure-devops-mcp-server
```

**Step 4: Test Endpoints**

```bash
# Health check
curl http://localhost:8004/health

# Get available tools
curl http://localhost:8004/tools

# Search code
curl -X POST http://localhost:8004/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "search_azure_devops_code",
    "arguments": {
      "query": "authentication",
      "top": 5
    }
  }'

# Get file content
curl -X POST http://localhost:8004/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "get_azure_devops_file",
    "arguments": {
      "file_path": "src/main.cpp"
    }
  }'
```

### 3. Standalone Usage (Command Line)

**Interactive Auth (stdio mode):**

```bash
python -m azure_devops_mcp_server \
  --mode stdio \
  --organization microsoft \
  --project OS \
  --repository os.2020 \
  --auth-mode interactive
```

**PAT Auth (HTTP mode):**

```bash
export AZURE_DEVOPS_PAT=your-pat-token

python -m azure_devops_mcp_server \
  --mode http \
  --port 8004 \
  --organization microsoft \
  --project OS \
  --repository os.2020 \
  --auth-mode pat
```

## Authentication Methods

### Interactive OAuth (Recommended for VS Code)

1. Run with `--auth-mode interactive`
2. Device code will be displayed
3. Browser opens automatically to https://microsoft.com/devicelogin
4. Enter device code and authenticate
5. Credentials cached in `~/.mcp_cache/azure_devops_token.bin`

### Personal Access Token (Recommended for Docker)

1. Create PAT in Azure DevOps:
   - Go to User Settings → Personal Access Tokens
   - Click "New Token"
   - Select scopes: Code (Read), Project and Team (Read)
   - Copy token

2. Use with `--auth-mode pat` or set `AZURE_DEVOPS_PAT` environment variable

## Troubleshooting

### "Failed to authenticate"

- Check PAT has correct scopes (Code Read, Project Read)
- Verify organization/project names are correct
- Try interactive auth instead of PAT

### "Connection timeout"

- Check network connectivity
- Verify Azure DevOps URL is accessible
- Check firewall/proxy settings

### "Tool not found"

- Ensure server is initialized: Check health endpoint
- Verify VS Code MCP configuration
- Check server logs for initialization errors

### VS Code Not Finding Server

- Verify `python` command is in PATH
- Check VS Code Output → MCP for error messages
- Try absolute path to Python executable in settings

## Configuration Options

| Option | Environment Variable | Default | Description |
|--------|---------------------|---------|-------------|
| `--mode` | `MCP_MODE` | `stdio` | Server mode: stdio or http |
| `--port` | `MCP_PORT` | `8004` | HTTP server port |
| `--host` | `MCP_HOST` | `0.0.0.0` | HTTP server host |
| `--organization` | `AZURE_DEVOPS_ORG` | `microsoft` | Azure DevOps organization |
| `--project` | `AZURE_DEVOPS_PROJECT` | `OS` | Azure DevOps project |
| `--repository` | `AZURE_DEVOPS_REPO` | `os.2020` | Azure DevOps repository |
| `--branch` | `AZURE_DEVOPS_BRANCH` | None | Default branch (None = repo default) |
| `--max-results` | `AZURE_DEVOPS_MAX_RESULTS` | `50` | Default max results per query |
| `--auth-mode` | `AZURE_DEVOPS_AUTH_MODE` | `interactive` | Auth mode: interactive or pat |
| `--pat` | `AZURE_DEVOPS_PAT` | None | Personal Access Token |

## Tool Usage Examples

### search_azure_devops_files

**List root files:**
```json
{
  "tool_name": "search_azure_devops_files",
  "arguments": {}
}
```

**Search by extension (non-recursive - safe and fast):**
```json
{
  "tool_name": "search_azure_devops_files",
  "arguments": {
    "extension": "json",
    "max_results": 10
  }
}
```

**Search in specific path:**
```json
{
  "tool_name": "search_azure_devops_files",
  "arguments": {
    "path_pattern": "src/MergedComponents",
    "extension": "cpp"
  }
}
```

**Deep recursive search with glob patterns:**
```json
{
  "tool_name": "search_azure_devops_files",
  "arguments": {
    "path_pattern": "**/test/**",
    "file_pattern": "*test*.cpp",
    "recursive": true,
    "max_results": 20
  }
}
```

**Search with file pattern:**
```json
{
  "tool_name": "search_azure_devops_files",
  "arguments": {
    "file_pattern": "azure-pipelines*",
    "extension": "yml",
    "recursive": true
  }
}
```

**Keyword search in content (requires recursive):**
```json
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

### get_azure_devops_file

**Get file from root:**
```json
{
  "tool_name": "get_azure_devops_file",
  "arguments": {
    "file_path": ".gitignore"
  }
}
```

**Get file from specific path:**
```json
{
  "tool_name": "get_azure_devops_file",
  "arguments": {
    "file_path": "src/MergedComponents/config.json"
  }
}
```

**Get file from specific branch:**
```json
{
  "tool_name": "get_azure_devops_file",
  "arguments": {
    "file_path": "README.md",
    "branch": "main"
  }
}
```

## Filter Pattern Syntax

### Path Patterns
- `src/` - Files in src directory (root level only, non-recursive)
- `src/MergedComponents` - Files in specific subdirectory
- `**/test/**` - Files in any test directory at any depth (requires `recursive: true`)
- `**/Doc**/Framework/**` - Complex glob pattern (requires `recursive: true`)

### File Patterns
- `*.cpp` - All C++ files
- `azure-*` - Files starting with "azure-"
- `*test*` - Files containing "test" in name
- `README.md` - Exact filename match

### Extensions
- `json` - JSON files
- `yml` - YAML files
- `cpp` - C++ files
- `cs` - C# files

### Keywords (requires recursive=true)
- `Azure` - Files containing the word "Azure"
- `connection timeout` - Phrase search
- `Http*Request` - With wildcards

### Combining Filters
All filters work together with AND logic:
```json
{
  "path_pattern": "src/",
  "file_pattern": "*service*",
  "extension": "cs",
  "recursive": true
}
```
Finds: C# files with "service" in the name, located under src/, searching recursively.

## Performance Tips

1. **Use non-recursive search by default** - Much faster for large repos
2. **Be specific with paths** - Narrow down search scope
3. **Use extension filters** - Reduces files to examine
4. **Set reasonable max_results** - Limit results for faster queries
5. **Use file patterns** - More efficient than keyword search
6. **Keyword search is expensive** - Only use when necessary, always with recursive=true

## Command-Line Testing

For quick testing without MCP integration:

```bash
cd azure_devops_mcp_server/tests

# List root files
python test_search.py --filter "ext:txt"

# Search in path
python test_search.py --path /src/MergedComponents --filter "ext:json" --max-results 10

# Get file content
python test_search.py --get-file ".gitignore" --max-lines 20

# Deep search with glob
python test_search.py --path "**/test/**" --filter "ext:cpp" --recursive

# Verbose output
python test_search.py --filter "ext:yml" --verbose

# Different branch
python test_search.py --branch main --filter "ext:md"
```

See `tests/README.md` for complete usage guide.

## Next Steps

- Review `README.md` for comprehensive API documentation
- Check `tests/README.md` for command-line tool examples
- See `IMPLEMENTATION.md` for technical details
- Explore `examples/` for integration patterns
{
  "tool_name": "get_azure_devops_file",
  "arguments": {
    "file_path": "src/kernel/main.cpp",
    "branch": "main"
  }
}
```

## Next Steps

1. Configure for your environment
2. Test authentication
3. Try example searches
4. Integrate with your workflow
5. Check README.md for advanced usage

## Support

- Issues: GitHub Issues
- Documentation: README.md
- Azure DevOps API: https://learn.microsoft.com/en-us/rest/api/azure/devops/

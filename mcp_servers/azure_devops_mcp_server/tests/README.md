# Azure DevOps MCP Server - Tests

This folder contains test utilities for the Azure DevOps MCP Server.

## Test Files

### test_search.py
Command-line tool for searching files and retrieving content from Azure DevOps repositories.

### test_integration.py
Integration test suite for HTTP mode and gateway integration testing.

## Test Search Tool (test_search.py)

`test_search.py` - Command-line tool for searching files and retrieving content from Azure DevOps repositories.

### Prerequisites

Set your Azure DevOps PAT:
```powershell
$env:AZURE_DEVOPS_PAT = "your-pat-token-here"
```

### Usage Examples

#### Search for files

```bash
# Search for JSON files at root level
python test_search.py --filter "ext:json"

# Search for files in specific path
python test_search.py --path /src/MergedComponents --filter "Azure ext:json"

# Search with file pattern
python test_search.py --filter "file:*.cpp"

# Search recursively (slower for large repos)
python test_search.py --path /src --filter "ext:yml" --recursive

# Combine multiple filters
python test_search.py --filter "file:azure-* ext:yml"

# Search with keyword (requires --recursive)
python test_search.py --filter "Azure ext:json" --recursive
```

#### Get file content

```bash
# Get full file content
python test_search.py --get-file ".gitignore"

# Get file content with line limit
python test_search.py --get-file "README.md" --max-lines 50

# Get file from specific path
python test_search.py --get-file "src/MergedComponents/config.json"
```

#### Advanced options

```bash
# Specify different branch
python test_search.py --branch "main" --filter "ext:cs"

# Specify different repository
python test_search.py --repository "os.2024" --filter "ext:yml"

# Verbose output with file details
python test_search.py --filter "ext:json" --verbose

# Limit results
python test_search.py --filter "ext:cpp" --max-results 10 --recursive
```

### Filter Syntax

The `--filter` parameter supports:

- **Extension**: `ext:json`, `ext:yml`, `ext:cpp`
- **File pattern**: `file:azure-*`, `file:*test*`, `file:README.md`
- **Path pattern**: `path:/src/`, `path:**/test/**` (requires `--recursive`)
- **Keyword**: Any word to search in content (requires `--recursive`)

Multiple filters can be combined:
```bash
--filter "Azure ext:json"
--filter "file:*service* ext:cs"
```

### Default Configuration

- **Organization**: microsoft
- **Project**: OS
- **Repository**: os.2020
- **Branch**: official/rs_sparc_ctr_exp
- **Max Results**: 50
- **Recursive**: False (opt-in for safety)

Override with environment variables:
```powershell
$env:AZURE_DEVOPS_ORG = "your-org"
$env:AZURE_DEVOPS_PROJECT = "your-project"
$env:AZURE_DEVOPS_REPO = "your-repo"
$env:AZURE_DEVOPS_BRANCH = "your-branch"
```

Or command-line arguments:
```bash
--organization your-org --project your-project --repository your-repo --branch your-branch
```

## Integration Tests (test_integration.py)

Test suite for HTTP server mode and gateway integration.

### Prerequisites

```powershell
# Set PAT token
$env:AZURE_DEVOPS_PAT = "your-pat-token"

# Optional: Set server URLs
$env:AZURE_DEVOPS_MCP_URL = "http://localhost:8004"
$env:GATEWAY_URL = "http://localhost:8000"
```

### Usage

```bash
# Test HTTP mode (server must be running)
python test_integration.py http

# Test gateway integration
python test_integration.py gateway

# Run all tests
python test_integration.py all

# Show help
python test_integration.py --help
```

### Test Modes

**HTTP Mode** - Tests the HTTP server endpoints:
- Health check endpoint
- Tool discovery endpoint
- Tool invocation (search and file retrieval)

**Gateway Mode** - Tests integration with LLMCrawl gateway:
- Chat API with Azure DevOps tool calls
- End-to-end workflow

### Starting the Server for Tests

```bash
# Start HTTP server
cd azure_devops_mcp_server
python -m azure_devops_client --mode http --auth-mode pat

# In another terminal, run tests
cd tests
python test_integration.py http
```

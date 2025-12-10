# Using Azure DevOps MCP Server with Template Agent

## Overview

The Code Intelligence Agent (template agent) now supports both local files and Azure DevOps repository files. You can use it to understand, inspect, or generate code from either source.

## File Path Prefixes

To tell the agent which MCP server to use, prefix your file paths:

- **Local files**: Use regular paths (e.g., `src/main.py`, `/data/files/readme.md`)
- **Azure DevOps files**: Use `azdo:` prefix with optional project/repo override

### Azure DevOps URI Format

```
azdo://[<project>/<repo>/]<path>[?branch=<branch_name>]
```

**Examples:**

| URI | Description |
|-----|-------------|
| `azdo:/src/main.cpp` | Default project, repo, and branch |
| `azdo:/src/main.cpp?branch=main` | Default project/repo, specific branch |
| `azdo://OS/os.2020/src/main.cpp` | Specific project and repo |
| `azdo://OneCore/WindowsCompositionData/path/file.xml` | Different project/repo |
| `azdo://OneCore/WindowsCompositionData/path?branch=main` | Full override |

**Rules:**
- Project and repo must appear together or both be absent
- Branch is always optional (defaults to configured branch)
- Path must start with `/` after the repo name

## Examples

### 1. Understand Local File

```json
{
  "workflow": "understand",
  "target_paths": [
    "src/service.py",
    "src/utils/helpers.py"
  ],
  "request": "Explain how these services work",
  "model": "gpt-4o"
}
```

### 2. Understand Azure DevOps File

```json
{
  "workflow": "understand",
  "target_paths": [
    "azdo:src/onecore/vm/compute/dll/ComputeServiceModule.cpp",
    "azdo:src/onecore/vm/compute/dll/ComputeService.h"
  ],
  "request": "Explain how the vmcompute service initializes",
  "model": "gpt-4o"
}
```

### 3. Understand Azure DevOps Folder

```json
{
  "workflow": "understand",
  "target_paths": [
    "azdo:src/onecore/vm/compute/dll/"
  ],
  "request": "Document the compute DLL implementation",
  "model": "gpt-4o"
}
```

### 4. Mixed Sources (Local + Azure DevOps)

```json
{
  "workflow": "inspect",
  "target_paths": [
    "azdo:/src/service.cpp",
    "local/tests/test_service.py"
  ],
  "request": "Check for security issues and test coverage gaps",
  "model": "gpt-4o"
}
```

### 5. Multiple Azure DevOps Repositories

```json
{
  "workflow": "understand",
  "target_paths": [
    "azdo:/src/onecore/vm/compute/ComputeService.cpp",
    "azdo://OneCore/WindowsCompositionData/manifests/service.xml"
  ],
  "reference_files": [
    "azdo://OneCore/WindowsCompositionData/docs/README.md"
  ],
  "request": "Explain how the service integrates with composition data",
  "model": "gpt-4o"
}
```

### 6. Generate Code from Azure DevOps Examples

```json
{
  "workflow": "generate",
  "target_paths": [],
  "request": "Create a new service class for handling network requests",
  "reference_files": [
    "azdo:src/services/HttpService.cpp",
    "azdo:src/services/NetworkBase.h"
  ],
  "model": "gpt-4o"
}
```

## Configuration

Ensure the gateway has access to Azure DevOps MCP server:

```bash
# In .env or docker-compose.yml
AZURE_DEVOPS_MCP_URL=http://azure-devops-mcp-server:8004
AZURE_DEVOPS_ORG=microsoft
AZURE_DEVOPS_PROJECT=OS
AZURE_DEVOPS_REPO=os.2020
AZURE_DEVOPS_BRANCH=official/rs_sparc_ctr_exp
AZURE_DEVOPS_PAT=your-pat-token
```

## How It Works

1. **Path Detection**: The agent checks if the path starts with `azdo:` or `azure-devops:`
2. **MCP Selection**:
   - If prefixed → Azure DevOps MCP server
   - Otherwise → Local file MCP server
3. **File Operations**:
   - **Read file**: Uses `get_azure_devops_file` or `read_local_file`
   - **List folder**: Uses `search_azure_devops_files` or `list_files`

## API Endpoints

### Execute Workflow (Template Format)

```bash
POST /agent/execute
```

```json
{
  "workflow": "understand",
  "target_paths": ["azdo:src/main.cpp"],
  "request": "Explain this code",
  "model": "gpt-4o"
}
```

### Detect Workflow (Natural Language)

```bash
POST /agent/detect
```

```json
{
  "query": "Analyze azdo:src/service.cpp and explain how it works"
}
```

The detector will extract:
- Workflow: `understand`
- Files: `["azdo:src/service.cpp"]`
- Request: `"explain how it works"`

## Folder Handling

When you specify a folder path, the agent will:

1. Call `search_azure_devops_files` with the path pattern
2. Get up to 10 files from the folder
3. Read each file's content
4. Include all in the analysis

**Example:**
```json
{
  "target_paths": ["azdo:src/compute/"],
  "request": "Document this folder"
}
```

This will:
1. List files in `src/compute/` (non-recursive by default)
2. Read up to 10 files
3. Send all to LLM for documentation

## Limitations

1. **File Count**: Maximum 10 files per folder (to avoid token limits)
2. **Token Limit**: Total input capped at 100,000 tokens (configurable via `MAX_INPUT_TOKENS`)
3. **Timeout**: Azure DevOps operations have 60s timeout
4. **Authentication**: Requires valid PAT token for Azure DevOps

## Error Handling

### "Failed to read Azure DevOps file"
- Check PAT token is valid
- Verify file path exists in repository
- Check branch is correct

### "Azure DevOps MCP URL not configured"
- Set `AZURE_DEVOPS_MCP_URL` environment variable
- Ensure Azure DevOps MCP server is running

### "'CodeIntelligenceAgent' object has no attribute '_list_files'"
- **Fixed**: This error has been resolved by adding the missing `_list_files` method

## Advanced Usage

### Recursive Folder Search

To search subdirectories in Azure DevOps:

```json
{
  "target_paths": ["azdo:src/compute/**"],
  "request": "Find all service implementations"
}
```

The `**` pattern triggers recursive search.

### Filter by Extension

```json
{
  "target_paths": ["azdo:src/*.cpp"],
  "request": "Analyze all C++ files in src"
}
```

### Combine with Web Crawl

```json
{
  "workflow": "understand",
  "target_paths": ["azdo:src/vm/compute.cpp"],
  "request": "Explain virtualization implementation",
  "seed_urls": ["https://docs.microsoft.com/virtualization"],
  "model": "gpt-4o"
}
```

This will:
1. Read Azure DevOps file
2. Crawl Microsoft docs
3. Combine both contexts
4. Generate comprehensive explanation

## Troubleshooting

### Agent doesn't recognize Azure DevOps prefix

**Solution**: Ensure you're using the correct prefix:
- ✅ `azdo:src/main.cpp`
- ✅ `azure-devops:src/main.cpp`
- ❌ `azure:src/main.cpp` (wrong prefix)
- ❌ `src/main.cpp` (will use local MCP server)

### Files not found

**Solution**: Check the file path format:
- Azure DevOps paths are relative to repository root
- Don't include leading slash: `src/file.cpp` not `/src/file.cpp`
- Use forward slashes: `src/compute/service.cpp`

### Token limit exceeded

**Solution**: Reduce the number of files:
- Target specific files instead of large folders
- Use smaller file sets
- Increase `MAX_INPUT_TOKENS` if needed (default: 100,000)

## See Also

- [MCP Integration Guide](../../mcp_servers/local_access_mcp_server/INTEGRATION_GUIDE.md)
- [Azure DevOps MCP Server README](../../mcp_servers/azure_devops_mcp_server/docs/README.md)
- [Template Agent Examples](./templates.py)

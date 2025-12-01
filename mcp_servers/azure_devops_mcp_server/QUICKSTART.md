# Azure DevOps MCP Server - Quick Start

## 1. Install

```bash
cd mcp_servers/azure_devops_mcp_server
pip install -e .
```

## 2. Set PAT Token

Get a PAT from Azure DevOps with "Code (Read)" scope:
https://dev.azure.com/{organization}/_usersSettings/tokens

```powershell
# PowerShell
$env:AZURE_DEVOPS_PAT = "your_pat_token"
```

```bash
# Bash
export AZURE_DEVOPS_PAT=your_pat_token
```

## 3. Test Command Line

```bash
cd tests

# Search files
python test_search.py --filter "ext:json"

# Get file content
python test_search.py --get-file ".gitignore"

# Search in path
python test_search.py --path /src --filter "HCS ext:md"
```

## 4. Run HTTP Server

```bash
python -m azure_devops_client --mode http --port 8004
```

Test:
```bash
curl http://localhost:8004/health
curl http://localhost:8004/tools
```

## 5. VS Code Configuration

Add to `%APPDATA%\Code\User\mcp.json`:

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

## 6. Docker

```bash
cd deploy
docker-compose up -d azure-devops-mcp-server
```

## Search Syntax

The `search_text` is passed directly to Azure DevOps Code Search API:

| Syntax | Example | Description |
|--------|---------|-------------|
| `ext:` | `ext:xml` | File extension |
| `file:` | `file:*config*` | File name pattern |
| `path:` | `path:Services` | Path contains |
| `class:` | `class:MyClass` | Class name |
| `func:` | `func:Main` | Function name |
| `AND/OR/NOT` | `term1 AND ext:cpp` | Boolean operators |

## HiChat URI Format

```
azdo:/path:searchText
```

Examples:
- `azdo:/:ext:xml` - All XML files
- `azdo:/src:HCS ext:md` - HCS markdown in src folder

## Troubleshooting

- **Auth failed**: Check PAT is valid with "Code (Read)" scope
- **No results**: Verify search syntax, try `ext:json` first
- **Timeout**: Check network connectivity to Azure DevOps

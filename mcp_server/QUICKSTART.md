# MCP Server Quick Start

This guide helps you get started with the MCP (Model Context Protocol) Server for local file operations.

## What is MCP Server?

The MCP Server enables your RAG system to:
- Read local files securely
- Search files by content using semantic similarity
- List files in directories
- Index files for efficient searching

All operations are restricted to a configured root folder for security.

## Quick Setup

### 1. Configure Root Folder

The MCP server reads files from `./data/files/` by default. Create this directory and add some files:

```powershell
# Create directory
New-Item -ItemType Directory -Force -Path .\data\files

# Add some test files
"Hello World" | Out-File .\data\files\test.txt
"{`"key`": `"value`"}" | Out-File .\data\files\config.json
```

### 2. Start Services

The MCP server is included in docker-compose:

```powershell
cd deploy
docker-compose up -d mcp-server
```

Verify it's running:
```powershell
curl http://localhost:8003/health
```

### 3. Test from HiChat

Open HiChat web client at http://localhost:3005 and try:

```
"Please list all files in the root folder"
"Read the content of test.txt"
"Index all files in the directory"
"Search for files containing 'configuration'"
```

## Example Queries

### List Files
```
"Show me all JSON files"
"List files in the config directory"
"What files are in the data folder?"
```

### Read Files
```
"Read the content of settings.json"
"Show me what's in the README file"
"Display the configuration file"
```

### Search Content
```
"Find files mentioning API keys"
"Search for database connection strings"
"Look for files containing error handling"
```

### Index Files
```
"Index all files in the project"
"Index only Python files"
"Reindex the documentation folder"
```

## Configuration

### Environment Variables

In `.env`:
```bash
# Root folder for file access
MCP_ROOT_FOLDER=/data/files

# Vector database storage
MCP_VECTOR_DB_PATH=/data/mcp_vector_db

# MCP server URL (for gateway)
MCP_SERVER_URL=http://mcp-server:8003
```

### Docker Volume Mapping

In `deploy/docker-compose.yml`:
```yaml
mcp-server:
  volumes:
    - ./data/files:/data/files  # Your local files
    - mcp_vector_db:/data/mcp_vector_db  # Vector DB
```

## Security

### Path Validation
All file paths are validated:
- ✅ `/data/files/config.json` - Within root
- ✅ `config/settings.json` - Relative path within root
- ❌ `../../etc/passwd` - Outside root (rejected)
- ❌ `/etc/passwd` - Absolute path outside root (rejected)

### Supported File Types
Text files are automatically detected:
- Documents: `.txt`, `.md`, `.json`, `.yaml`, `.xml`
- Code: `.py`, `.js`, `.go`, `.java`, `.c`, `.cpp`
- Logs: `.log`, `.csv`

Binary files are detected and reported (not indexed).

## Workflow

### First-Time Use
1. **Add Files**: Copy files to `./data/files/`
2. **Start Server**: `docker-compose up -d mcp-server`
3. **Index Files**: Ask LLM to "index all files"
4. **Search**: Ask questions about file content

### Regular Use
1. **Search**: "Find files containing X"
2. **Read**: "Show me the content of file.txt"
3. **List**: "What files are in the logs folder?"

### When Files Change
1. **Reindex**: "Please reindex the project files"
2. **Verify**: "Search for the new configuration"

## Troubleshooting

### Files Not Found
**Problem**: "File not found" error

**Solution**:
- Check file exists in `./data/files/`
- Verify path is relative or within root
- Check docker volume mounting

### Search Returns No Results
**Problem**: Search finds nothing

**Solution**:
- Index files first: "Index all files"
- Check if files contain text (not binary)
- Verify file extensions are supported

### Slow Indexing
**Problem**: Indexing takes a long time

**Solution**:
- Index specific folders instead of all
- Limit to specific file types
- Use non-recursive indexing for large trees

### Permission Errors
**Problem**: Can't read files

**Solution**:
- Check file permissions on host
- Verify docker user has read access
- Check volume mounting in docker-compose.yml

## Advanced Usage

### Custom File Types
Edit `mcp_server/file_indexer.py`:
```python
self.text_extensions = {
    ".txt", ".md", ".json",  # Add your extensions
    ".custom", ".conf"
}
```

### Different Root Folder
Update `.env`:
```bash
MCP_ROOT_FOLDER=/path/to/your/files
```

And update docker-compose.yml volume:
```yaml
volumes:
  - /path/to/your/files:/data/files
```

### API Access
Direct API calls (for testing):
```bash
# Get tools
curl http://localhost:8003/tools

# List files
curl -X POST http://localhost:8003/invoke \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "list_files", "arguments": {"folder_path": "."}}'
```

## Next Steps

- Read [Full Documentation](README.md)
- See [Architecture Details](../README.md#architecture)
- Configure [Custom Settings](README.md#configuration)
- Test with [Test Script](tests/test_mcp_server.py)

## Support

- GitHub Issues: Report bugs or request features
- Documentation: [mcp_server/README.md](README.md)
- Main README: [../README.md](../README.md)

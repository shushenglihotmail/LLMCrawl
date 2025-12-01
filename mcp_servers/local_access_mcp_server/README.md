# MCP Server - Local File Operations

A simple MCP (Model Context Protocol) server for listing and reading local files. This server provides secure file access within a configured root directory.

## Features

- **List Files**: List files and directories in folders with optional filtering
- **Read Files**: Read content of text files
- **Secure Access**: All file operations are restricted to a configured root folder
- **Path Validation**: Prevents directory traversal and access outside root folder

## Available Tools

### 1. `list_files`

List files and directories in a folder. Use this to explore the file system and find files.

**Parameters:**
- `folder_path` (string): Path to the folder to list (default: ".")
- `extension` (string): Filter by file extension (e.g., ".json", ".txt")
- `recursive` (boolean): If true, list files in all subdirectories recursively

**Example queries:**
- "List all files in the config folder"
- "Show me all JSON files"
- "Find all Python files recursively"

### 2. `read_local_file`

Read and return the full content of a file. Use this after `list_files` to read a specific file's content.

**Parameters:**
- `file_path` (string, required): Path to the file to read

**Example queries:**
- "Read the file config.json"
- "Show me the content of README.md"
- "What's in the app.log file?"

## Configuration

Environment variables:

- `MCP_ROOT_FOLDER`: Root folder for file operations (default: `/data/files`)

## Usage

### From HiChat Client

```bash
# In chat:
"List all files in the data directory"
"Read the config.json file"
"Show me all log files recursively"
```

### Direct API Call

```bash
# Get available tools
curl http://localhost:8003/tools

# List files
curl -X POST http://localhost:8003/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "list_files",
    "arguments": {
      "folder_path": ".",
      "recursive": false
    }
  }'

# Read a file
curl -X POST http://localhost:8003/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "read_local_file",
    "arguments": {
      "file_path": "config/app.json"
    }
  }'
```

## Docker Setup

The MCP server is included in docker-compose.yml:

```yaml
mcp-server:
  build:
    context: .
    dockerfile: deploy/Dockerfile.mcp_server
  ports:
    - "8003:8003"
  environment:
    - MCP_ROOT_FOLDER=/data/files
  volumes:
    - ./data/files:/data/files
```

## Security

- **Relative paths** are resolved relative to the root folder
- **Absolute paths** must be within the root folder
- **Directory traversal** attempts (e.g., `../../../etc/passwd`) are rejected
- **Binary files** are detected and reported as such (not read as text)

## Architecture

```
HiChat Client → Gateway (8000) → MCP Server (8003) → Local Files
```

1. User asks about local files via HiChat
2. LLM decides which MCP tool to use
3. Gateway routes tool call to MCP server
4. MCP server executes file operation with security validation
5. Results returned to LLM for response generation

## Integration with Gateway

Add to `.env`:
```
MCP_SERVER_URL=http://mcp-server:8003
```

The gateway will:
1. Fetch available tools from `/tools` endpoint
2. Include them in LLM tool list
3. Route tool invocations to `/invoke` endpoint

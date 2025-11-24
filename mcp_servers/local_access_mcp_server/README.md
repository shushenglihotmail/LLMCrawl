# MCP Server - Local File Operations

The MCP (Model Context Protocol) Server provides tools for reading, searching, and indexing local files. Files are indexed using embeddings for semantic search, allowing the LLM to understand and find relevant content.

## Features

- **Secure File Access**: All file operations are restricted to a configured root folder
- **Path Validation**: Prevents directory traversal and access outside root folder
- **Semantic Search**: Files are chunked and embedded for intelligent content search
- **Multiple File Operations**:
  - Read file content
  - List files in directories
  - Search for files containing specific content
  - Index files for semantic search

## Configuration

Environment variables:

- `MCP_ROOT_FOLDER`: Root folder for file operations (default: `/data/files`)
- `MCP_VECTOR_DB_PATH`: Path to store vector database (default: `/data/mcp_vector_db`)
- `OPENAI_API_KEY`: OpenAI API key for embeddings (required)
- `OPENAI_MODEL`: LLM model for queries (default: `gpt-4o-mini`)
- `OPENAI_EMBEDDING_MODEL`: Embedding model (default: `text-embedding-3-small`)

## Available Tools

### 1. `read_local_file`

Read and return the content of a specific file.

**Parameters:**
- `file_path` (string, required): Path to the file (relative to root folder or absolute within root)

**Example queries:**
- "Read the file config.json"
- "Show me the content of data/logs/app.log"
- "What's in the README.md file?"

### 2. `list_files`

List files in a directory with optional filtering.

**Parameters:**
- `folder_path` (string): Path to folder (default: ".")
- `extension` (string): Filter by extension (e.g., ".json", ".txt")
- `recursive` (boolean): Search subdirectories (default: false)

**Example queries:**
- "List all JSON files in the config folder"
- "Show me all files in the data directory"
- "Find all Python files recursively"

### 3. `search_file_content`

Search for files containing specific text using semantic similarity.

**Parameters:**
- `query` (string, required): Search query
- `folder_path` (string): Limit search to specific folder (default: ".")
- `top_k` (integer): Number of results (default: 5)

**Example queries:**
- "Find files containing database configuration"
- "Search for files with API endpoints under /src"
- "Look for files mentioning authentication"

### 4. `index_files`

Index files in a folder for semantic search.

**Parameters:**
- `folder_path` (string): Path to folder to index (default: ".")
- `recursive` (boolean): Index subdirectories (default: true)
- `extensions` (array of strings): File extensions to index (default: all text files)

**Example queries:**
- "Index all files in the project folder"
- "Index only JSON files in the config directory"
- "Reindex the documentation folder"

## Usage Example

### From HiChat Client

```bash
# Web client
http://localhost:3005

# In chat:
"Please search for files containing API keys under the config folder"
"Read the file at data/secrets.json"
"List all log files in the logs directory"
```

### Direct API Call

```bash
# Get available tools
curl http://localhost:8003/tools

# Invoke a tool
curl -X POST http://localhost:8003/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "read_local_file",
    "arguments": {
      "file_path": "config/app.json"
    }
  }'
```

## Security

### Path Validation

All file paths are validated to ensure they are within the configured root folder:

- **Relative paths** are resolved relative to the root folder
- **Absolute paths** must be within the root folder
- **Directory traversal** attempts (e.g., `../../../etc/passwd`) are rejected
- **Symlinks** are resolved and validated

### Supported File Types

By default, the following text file extensions are indexed:
- Documents: `.txt`, `.md`
- Data: `.json`, `.yaml`, `.yml`, `.xml`, `.csv`
- Logs: `.log`
- Code: `.py`, `.js`, `.ts`, `.go`, `.java`, `.c`, `.cpp`, `.h`, `.sh`, `.ps1`, `.sql`

Binary files are detected and reported as such (not indexed or read as text).

## Docker Setup

The MCP server is included in the docker-compose.yml:

```yaml
mcp-server:
  build:
    context: .
    dockerfile: deploy/Dockerfile.mcp_server
  ports:
    - "8003:8003"
  environment:
    - MCP_ROOT_FOLDER=/data/files
    - MCP_VECTOR_DB_PATH=/data/mcp_vector_db
  volumes:
    - ./data/files:/data/files  # Mount your local files here
    - mcp_vector_db:/data/mcp_vector_db
```

### Mounting Local Files

To make your local files accessible:

1. Create a local directory (e.g., `./data/files`)
2. Place your files in this directory
3. The docker-compose.yml mounts this to `/data/files` in the container

## Architecture

```
┌─────────────────┐
│   HiChat Web    │
│     Client      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│   Gateway       │─────▶│  MCP Server  │
│   (Port 8000)   │      │  (Port 8003) │
└────────┬────────┘      └──────┬───────┘
         │                       │
         ▼                       ▼
┌─────────────────┐      ┌──────────────┐
│  Tool Handler   │      │  File Reader │
└─────────────────┘      │  + Indexer   │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │ Vector Store │
                         │ (LlamaIndex) │
                         └──────────────┘
```

### Flow

1. **User Query**: User asks about local files via HiChat
2. **LLM Decision**: LLM decides which MCP tool to use
3. **Gateway Routing**: Gateway routes tool call to MCP server
4. **Tool Execution**: MCP server executes file operation with security validation
5. **Content Processing**: Files are read, chunked, and embedded
6. **Search**: Semantic search finds relevant content
7. **Response**: Results are returned to LLM for answer generation

## Indexing Strategy

Files are automatically chunked and embedded:

- **Chunk Size**: 512 tokens
- **Chunk Overlap**: 50 tokens
- **Embeddings**: OpenAI text-embedding-3-small
- **Storage**: Persistent vector database

### When to Reindex

- After adding new files
- After modifying existing files
- When search results seem outdated
- Use the `index_files` tool explicitly

## Troubleshooting

### Files Not Found

- Check `MCP_ROOT_FOLDER` configuration
- Verify docker volume mounting
- Ensure file paths are correct (relative to root)

### Search Returns No Results

- Index the files first using `index_files` tool
- Check if files contain searchable text content
- Verify file extensions are supported

### Permission Errors

- Ensure container has read access to mounted volumes
- Check file permissions in host system
- Verify docker user permissions

### Slow Indexing

- Large files take time to chunk and embed
- Consider indexing only specific file types
- Use non-recursive indexing for large directory trees

## Development

### Running Locally

```bash
# Install dependencies
pip install -r requirements/mcp_server.txt

# Set environment variables
export MCP_ROOT_FOLDER=/path/to/local/files
export MCP_VECTOR_DB_PATH=/path/to/vector/db
export OPENAI_API_KEY=your-api-key

# Run server
python -m mcp_server.main
```

### Testing

```bash
# Health check
curl http://localhost:8003/health

# Get tools
curl http://localhost:8003/tools

# Test file reading
curl -X POST http://localhost:8003/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "list_files",
    "arguments": {
      "folder_path": ".",
      "recursive": false
    }
  }'
```

## Integration with Gateway

The gateway automatically loads MCP tools at startup and includes them in the tool list sent to the LLM. When the LLM decides to use an MCP tool, the gateway routes the request to the MCP server.

### Gateway Configuration

Add to `.env`:
```
MCP_SERVER_URL=http://mcp-server:8003
```

The gateway will:
1. Fetch available tools from `/tools` endpoint
2. Include them in LLM tool list
3. Route tool invocations to `/invoke` endpoint
4. Handle errors and return results to LLM

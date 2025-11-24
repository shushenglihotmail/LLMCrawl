# MCP Server Integration with LLMCrawl

This document explains how MCP servers integrate with LLMCrawl and answers common integration questions.

## Architecture Overview

LLMCrawl supports two MCP server integration modes:

### 1. HTTP Mode (Production - Recommended)

```
┌─────────────┐     HTTP      ┌──────────────────┐
│   Gateway   │◄─────────────►│  MCP Server      │
│   (Docker)  │               │  (Docker)        │
└─────────────┘               └──────────────────┘
      │                              │
      │                              │
   ┌──▼──┐                      ┌────▼────┐
   │ LLM │                      │ Data    │
   └─────┘                      │ Source  │
                                └─────────┘
```

**Characteristics:**
- ✅ Microservices architecture (each service in separate container)
- ✅ Horizontal scalability (can run multiple MCP server instances)
- ✅ Independent monitoring, logging, and restart
- ✅ Docker-native (standard container networking)
- ✅ Production-ready
- ⚠️ Small HTTP overhead (negligible for most use cases)

**Usage:**
```yaml
# docker-compose.yml
services:
  gateway:
    environment:
      MCP_SERVER_URL: http://mcp-server:8003
      AZURE_DEVOPS_MCP_URL: http://azure-devops-mcp-server:8004

  mcp-server:
    build: ./mcp_server
    command: python -m mcp_server.main --mode http --port 8003

  azure-devops-mcp-server:
    build: ./azure_devops_mcp_server
    command: python -m azure_devops_client --mode http --port 8004
```

### 2. Stdio Mode (VS Code Integration)

```
┌─────────────┐    stdio      ┌──────────────────┐
│  VS Code    │◄─────────────►│  MCP Server      │
│  Copilot    │  stdin/stdout │  (subprocess)    │
└─────────────┘               └──────────────────┘
```

**Characteristics:**
- ✅ Native VS Code integration
- ✅ No HTTP overhead
- ✅ Simple process-to-process communication
- ⚠️ Single instance per client (no scaling)
- ⚠️ Not suitable for container-to-container communication
- ⚠️ Harder to monitor and debug

**Usage:**
```json
// %APPDATA%\Code\User\mcp.json (Windows)
{
  "inputs": [],
  "servers": {
    "local-files": {
      "command": "C:\\path\\to\\python.exe",
      "args": ["-m", "mcp_server.main", "--mode", "stdio"],
      "type": "stdio"
    }
  }
}
```

## Integration Questions Answered

### Q1: Can LLMCrawl Template Agent Use Azure DevOps MCP Server?

**Answer: YES ✅ - Already Supported**

The gateway (`gateway/routers/tools.py`) already supports Azure DevOps MCP server tools:
- `search_azure_devops_files` - Search/list files with patterns, extensions, keywords
- `search_azure_devops_code` - Search code content
- `get_azure_devops_file` - Get specific file content

**Configuration:**
```bash
# .env or docker-compose.yml
AZURE_DEVOPS_MCP_URL=http://azure-devops-mcp-server:8004
AZURE_DEVOPS_ORG=microsoft
AZURE_DEVOPS_PROJECT=OS
AZURE_DEVOPS_REPO=os.2020
AZURE_DEVOPS_BRANCH=main
AZURE_DEVOPS_PAT=your-pat-token
```

**How it works:**
1. Gateway loads Azure DevOps tools at startup (`chat.py:get_azure_devops_tools()`)
2. Tools are included in LLM function list
3. When LLM calls tool, gateway routes to Azure DevOps MCP server via HTTP
4. Results are returned to LLM

### Q2: Can LLMCrawl Use stdio Like VS Code?

**Answer: Possible, but NOT Recommended**

**Technical Feasibility:**
- ✅ Could spawn MCP server subprocess from gateway
- ✅ Communicate via stdin/stdout using JSON-RPC
- ✅ No network overhead

**Why NOT Recommended:**

1. **Container Architecture Mismatch:**
   ```
   Docker Container = Isolated process space
   Stdio = Parent-child process communication
   Problem: Hard to manage subprocess lifecycle in containers
   ```

2. **Scalability Issues:**
   - Can't run multiple gateway instances with shared MCP server
   - Each gateway needs its own MCP server subprocess
   - No load balancing or failover

3. **Monitoring Challenges:**
   - Subprocess logs mixed with gateway logs
   - Hard to track MCP server health independently
   - Restart requires gateway restart

4. **Docker Best Practices:**
   - Containers should communicate via network (HTTP, gRPC)
   - One process per container (not parent-child subprocesses)
   - Service mesh patterns expect network protocols

**Recommendation:**
- **Production:** Use HTTP mode (current implementation) ✅
- **Local Dev:** Use HTTP mode or run without Docker
- **VS Code:** Use stdio mode (native integration) ✅

### Q3: Can Local File MCP Server Support stdio?

**Answer: YES ✅ - Now Implemented**

The local file MCP server now supports both modes:

**HTTP Mode (for LLMCrawl):**
```bash
python -m mcp_server.main --mode http --port 8003 \
  --root-folder /data/files \
  --vector-db-path /data/mcp_vector_db
```

**Stdio Mode (for VS Code):**
```bash
python -m mcp_server.main --mode stdio \
  --root-folder /data/files \
  --vector-db-path /data/mcp_vector_db
```

**VS Code Configuration:**
```jsonc
// %APPDATA%\Code\User\mcp.json
{
  "inputs": [],
  "servers": {
    "local-files": {
      "command": "C:\\src\\github\\LLMCrawl\\venv\\Scripts\\python.exe",
      "args": [
        "-m", "mcp_server.main",
        "--mode", "stdio",
        "--root-folder", "C:\\data\\files",
        "--vector-db-path", "C:\\data\\mcp_vector_db"
      ],
      "env": {
        "OPENAI_API_KEY": "YOUR_KEY_HERE"
      },
      "type": "stdio"
    }
  }
}
```

## Quick Setup Guide

### For LLMCrawl (HTTP Mode)

1. **Start all services:**
   ```bash
   cd deploy
   docker-compose up -d
   ```

2. **Verify MCP servers:**
   ```bash
   # Test local file MCP server
   curl http://localhost:8003/health

   # Test Azure DevOps MCP server
   curl http://localhost:8004/health

   # List available tools
   curl http://localhost:8003/tools
   curl http://localhost:8004/tools
   ```

3. **Use via chat:**
   ```bash
   curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{
       "message": "List all Python files in the src folder",
       "model": "gpt-4o"
     }'
   ```

### For VS Code (Stdio Mode)

1. **Install MCP servers:**
   ```bash
   cd LLMCrawl
   python -m venv venv
   .\venv\Scripts\Activate.ps1  # Windows

   # Install local file MCP server
   pip install -e mcp_servers/local_access_mcp_server/

   # Install Azure DevOps MCP server
   pip install -e mcp_servers/azure_devops_mcp_server/
   ```

2. **Configure VS Code:**
   - Open `%APPDATA%\Code\User\mcp.json`
   - Add server configurations (see `vscode-mcp-example.jsonc`)
   - Use ABSOLUTE paths to Python executables

3. **Restart VS Code**

4. **Test with Copilot Chat:**
   - "List all JSON files in /data/files"
   - "Search for files containing 'Azure' in the OS repository"
   - "Show me the README.md file"

## Architecture Comparison

| Feature | HTTP Mode | Stdio Mode |
|---------|-----------|------------|
| **Scalability** | ✅ Horizontal scaling | ❌ Single instance |
| **Monitoring** | ✅ Independent logs | ⚠️ Mixed logs |
| **Docker-friendly** | ✅ Native | ❌ Complex |
| **Performance** | ⚠️ HTTP overhead (~1ms) | ✅ Direct IPC |
| **VS Code Native** | ❌ Not supported | ✅ Native |
| **Production Ready** | ✅ Yes | ⚠️ Dev only |
| **Service Mesh** | ✅ Compatible | ❌ Incompatible |

## Common Issues

### Issue 1: MCP Server Not Responding

**Symptoms:**
```
Tool execution error: MCP server unavailable
```

**Solutions:**
```bash
# Check if MCP server is running
docker ps | grep mcp

# Check logs
docker logs mcp-server

# Verify network connectivity
docker exec gateway ping mcp-server

# Restart services
docker-compose restart mcp-server gateway
```

### Issue 2: VS Code Can't Find MCP Server

**Symptoms:**
- Copilot doesn't show MCP tools
- "Server initialization failed" in Output → MCP

**Solutions:**
1. **Verify Python path is absolute:**
   ```powershell
   # Get Python path
   (Get-Command python).Source
   # Use in mcp.json: "C:\\src\\github\\LLMCrawl\\venv\\Scripts\\python.exe"
   ```

2. **Check package is installed:**
   ```bash
   python -c "import mcp_server; print('OK')"
   python -c "import azure_devops_client; print('OK')"
   ```

3. **Test stdio mode manually:**
   ```bash
   python -m mcp_server.main --mode stdio
   # Should wait for JSON-RPC messages
   # Press Ctrl+C to exit
   ```

4. **Check VS Code Output:**
   - View → Output → Select "MCP" from dropdown
   - Look for connection errors

### Issue 3: Authentication Failures

**Azure DevOps PAT:**
```bash
# Test PAT validity
curl -u :YOUR_PAT_TOKEN \
  https://dev.azure.com/microsoft/_apis/projects

# Environment variable
export AZURE_DEVOPS_PAT=your-token

# In mcp.json
"env": {
  "AZURE_DEVOPS_PAT": "your-token"
}
```

**OpenAI API Key (for semantic search):**
```bash
# In mcp.json
"env": {
  "OPENAI_API_KEY": "sk-..."
}
```

## Best Practices

1. **Use HTTP Mode for Production**
   - Better monitoring and debugging
   - Easier to scale
   - Standard microservices pattern

2. **Use Stdio Mode Only for VS Code**
   - Native integration
   - No need for HTTP server
   - Direct subprocess communication

3. **Separate Concerns**
   - Local file MCP server → Read local files
   - Azure DevOps MCP server → Access DevOps repositories
   - Gateway → Orchestrate tools and LLM

4. **Secure Credentials**
   - Never commit PATs or API keys
   - Use environment variables
   - Rotate keys regularly

5. **Monitor Performance**
   - Track tool call latency
   - Monitor MCP server health endpoints
   - Set appropriate timeouts

## References

- [Model Context Protocol Spec](https://spec.modelcontextprotocol.io/)
- [Azure DevOps MCP Server README](../azure_devops_mcp_server/README.md)
- [Local File MCP Server README](README.md)
- [LLMCrawl Architecture](../ARCHITECTURE.md)

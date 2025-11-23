# Azure DevOps MCP Server - Deployment Guide

## ✅ Completed Implementation

The Azure DevOps MCP Server is fully implemented and ready for deployment. All core functionality is complete.

## 📦 What Was Built

### Core Components (100% Complete)

1. **Azure DevOps API Client** (`azure_client.py`)
   - ✅ MSAL OAuth authentication with device code flow
   - ✅ PAT authentication support
   - ✅ Token caching and silent auth
   - ✅ Code search using Azure DevOps Search API
   - ✅ File retrieval using Git Items API
   - ✅ Connection testing and error handling

2. **MCP Server** (`server.py`)
   - ✅ JSON-RPC stdio protocol for VS Code
   - ✅ Tool definitions (OpenAI function format)
   - ✅ Tool execution dispatcher
   - ✅ Message handling loop

3. **HTTP Server** (`http_server.py`)
   - ✅ FastAPI REST API for LLMCrawl
   - ✅ CORS middleware
   - ✅ Health check endpoint
   - ✅ Tools listing endpoint
   - ✅ Tool invocation endpoint
   - ✅ Authentication trigger endpoint

4. **Entry Point** (`__main__.py`)
   - ✅ Command-line argument parsing
   - ✅ Dual mode support (stdio/HTTP)
   - ✅ Environment variable configuration
   - ✅ Startup initialization

### Integration (100% Complete)

5. **Gateway Integration**
   - ✅ Added `get_azure_devops_tools()` to chat.py
   - ✅ Tool loading from Azure DevOps MCP server
   - ✅ Tool routing in tools.py
   - ✅ Error handling and fallbacks

6. **Docker Deployment**
   - ✅ Dockerfile with health checks
   - ✅ Added to docker-compose.yml
   - ✅ Volume for token cache
   - ✅ Environment variable configuration

### Documentation (100% Complete)

7. **Documentation Files**
   - ✅ README.md - Complete feature documentation
   - ✅ QUICKSTART.md - Step-by-step setup guide
   - ✅ IMPLEMENTATION.md - Technical implementation summary
   - ✅ vscode-settings.example.jsonc - VS Code configuration
   - ✅ Updated main README.md with Azure DevOps section

8. **Testing**
   - ✅ HTTP mode test suite
   - ✅ Gateway integration tests
   - ✅ Test script with examples

## 🚀 Quick Deployment Steps

### Option 1: Docker (Recommended for LLMCrawl)

```bash
# 1. Add PAT to .env file
cd LLMCrawl
echo "AZURE_DEVOPS_PAT=your-personal-access-token" >> .env

# 2. Start the service
cd deploy
docker-compose up -d azure-devops-mcp-server

# 3. Verify it's running
curl http://localhost:8004/health

# 4. Test search
curl -X POST http://localhost:8004/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "search_azure_devops_code",
    "arguments": {"query": "authentication", "top": 5}
  }'
```

### Option 2: VS Code (stdio mode)

```bash
# 1. Install package
cd azure_devops_mcp_server
pip install -e .

# 2. Add to VS Code mcp.json
# Copy vscode-settings.example.jsonc content to mcp.json in VS Code user folder

# 3. Restart VS Code
# The server will auto-start and prompt for authentication
```

### Option 3: Standalone

```bash
# Install
cd azure_devops_mcp_server
pip install -e .

# Run with interactive auth
python -m azure_devops_mcp_server \
  --mode stdio \
  --organization microsoft \
  --project OS \
  --repository os.2020 \
  --auth-mode interactive

# Or run HTTP mode with PAT
export AZURE_DEVOPS_PAT=your-pat
python -m azure_devops_mcp_server \
  --mode http \
  --port 8004 \
  --auth-mode pat
```

## 📋 Pre-Deployment Checklist

### Azure DevOps Setup

- [ ] Create Personal Access Token (PAT)
  - Go to Azure DevOps → User Settings → Personal Access Tokens
  - Click "New Token"
  - Select scopes: Code (Read), Project and Team (Read)
  - Copy token for use in deployment

- [ ] Verify repository access
  - Organization: `microsoft`
  - Project: `OS`
  - Repository: `os.2020`
  - URL: https://microsoft.visualstudio.com/OS/_git/os.2020

### Environment Configuration

- [ ] Add to `.env` file:
```bash
# Azure DevOps MCP Server
AZURE_DEVOPS_PAT=your-personal-access-token
AZURE_DEVOPS_ORG=microsoft
AZURE_DEVOPS_PROJECT=OS
AZURE_DEVOPS_REPO=os.2020
AZURE_DEVOPS_MCP_URL=http://azure-devops-mcp-server:8004
```

### Gateway Configuration

- [ ] Verify gateway can reach server
  - Check `AZURE_DEVOPS_MCP_URL` in environment
  - Default: `http://azure-devops-mcp-server:8004`

- [ ] Gateway will automatically:
  - Load Azure DevOps tools at startup
  - Present them to LLM alongside web crawl and MCP tools
  - Route tool calls to Azure DevOps MCP server

## 🧪 Testing After Deployment

### 1. Health Check

```bash
curl http://localhost:8004/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "azure-devops-mcp-server",
  "organization": "microsoft",
  "project": "OS",
  "repository": "os.2020"
}
```

### 2. List Tools

```bash
curl http://localhost:8004/tools
```

Expected: 2 tools (`search_azure_devops_code`, `get_azure_devops_file`)

### 3. Search Code

```bash
curl -X POST http://localhost:8004/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "search_azure_devops_code",
    "arguments": {
      "query": "authentication",
      "top": 5
    }
  }'
```

Expected: Search results with file paths

### 4. Get File

```bash
curl -X POST http://localhost:8004/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "get_azure_devops_file",
    "arguments": {
      "file_path": "README.md"
    }
  }'
```

Expected: File content

### 5. Gateway Integration

```bash
# Send chat message to gateway
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Search for authentication code in the OS repository",
    "model": "gpt-4"
  }'
```

Expected: LLM response with code search results

### 6. Run Test Suite

```bash
cd azure_devops_mcp_server
export AZURE_DEVOPS_PAT=your-pat
python test_azure_devops_mcp.py all
```

## 📊 Monitoring

### Health Endpoint

```bash
# Check every 30 seconds
watch -n 30 'curl -s http://localhost:8004/health | jq'
```

### Docker Logs

```bash
# Follow logs
docker logs -f web-rag-azure-devops-mcp

# Check for errors
docker logs web-rag-azure-devops-mcp | grep ERROR
```

### Gateway Logs

```bash
# Check if gateway loaded Azure DevOps tools
docker logs web-rag-gateway | grep "Azure DevOps"
```

Expected: "Loaded N Azure DevOps MCP tools"

## 🔧 Troubleshooting

### Common Issues

**Problem: "Failed to authenticate"**
```bash
# Check PAT is correct
echo $AZURE_DEVOPS_PAT

# Verify PAT has correct scopes
# Required: Code (Read), Project and Team (Read)

# Test PAT manually
curl -u :$AZURE_DEVOPS_PAT \
  https://dev.azure.com/microsoft/_apis/projects?api-version=7.2
```

**Problem: "Connection timeout"**
```bash
# Check container is running
docker ps | grep azure-devops

# Check network connectivity
docker exec web-rag-azure-devops-mcp curl -I https://dev.azure.com

# Check firewall/proxy settings
```

**Problem: "Gateway can't reach server"**
```bash
# Verify both containers on same network
docker network inspect webrag-network

# Test from gateway container
docker exec web-rag-gateway curl http://azure-devops-mcp-server:8004/health

# Check environment variable
docker exec web-rag-gateway env | grep AZURE_DEVOPS_MCP_URL
```

**Problem: "Search returns 0 results"**
```bash
# Verify repository has Azure DevOps Search enabled
# Check organization/project/repo names are correct
# Try broader search query
```

## 📈 Performance Tuning

### Timeout Configuration

Default timeouts:
- HTTP client: 30 seconds
- Search API: 30 seconds
- File retrieval: 30 seconds

Adjust in code if needed:
```python
# In http_server.py or server.py
timeout = 60.0  # Increase for large repos
```

### Token Cache

Location: `/app/.mcp_cache/azure_devops_token.bin` (Docker)

To clear cache:
```bash
docker exec web-rag-azure-devops-mcp rm /app/.mcp_cache/azure_devops_token.bin
docker restart web-rag-azure-devops-mcp
```

### Rate Limiting

Azure DevOps API has rate limits. If you hit them:
1. Reduce search frequency
2. Cache results
3. Use more specific queries
4. Contact Azure DevOps to increase limits

## 🔐 Security Best Practices

1. **PAT Security**
   - Store PAT in `.env` file (not in code)
   - Never commit PAT to Git
   - Rotate PAT regularly (every 90 days)
   - Use minimum required scopes

2. **Network Security**
   - Run on private network in production
   - Use reverse proxy with HTTPS
   - Restrict access to gateway only
   - Enable firewall rules

3. **Token Storage**
   - Token cache is user-specific
   - Use Docker volumes for persistence
   - Backup cache with encrypted storage
   - Monitor for unauthorized access

## 📚 Additional Resources

- **Azure DevOps REST API**: https://learn.microsoft.com/en-us/rest/api/azure/devops/
- **MSAL Python**: https://msal-python.readthedocs.io/
- **MCP Protocol**: Model Context Protocol specification
- **FastAPI**: https://fastapi.tiangolo.com/

## 🎯 Next Steps

1. **Deploy**: Follow deployment steps above
2. **Test**: Run test suite to verify
3. **Monitor**: Check logs and health endpoint
4. **Use**: Ask LLM to search Azure DevOps
5. **Optimize**: Tune timeouts and caching as needed

## 📞 Support

- Check QUICKSTART.md for setup help
- See README.md for feature documentation
- See IMPLEMENTATION.md for technical details
- Check logs for error messages
- Test endpoints manually with curl

---

**Status**: ✅ Ready for Deployment

All components are implemented, tested, and documented. Follow the deployment steps above to start using the Azure DevOps MCP Server.

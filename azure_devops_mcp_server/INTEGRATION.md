# Integration Guide - Azure DevOps MCP Server

## VS Code Copilot Integration

### Quick Setup

1. **Create VS Code MCP settings file**:

```json
// .vscode/settings.json
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
        "--branch",
        "official/rs_sparc_ctr_exp",
        "--auth-mode",
        "pat"
      ],
      "env": {
        "AZURE_DEVOPS_PAT": "your-personal-access-token-here"
      }
    }
  }
}
```

2. **Or use environment variable** (more secure):

```json
// .vscode/settings.json
{
  "mcpServers": {
    "azure-devops": {
      "command": "python",
      "args": ["-m", "azure_devops_mcp_server", "--mode", "stdio"],
      "env": {}  // Uses environment variables
    }
  }
}
```

Then set environment variables:
```powershell
$env:AZURE_DEVOPS_ORG = "microsoft"
$env:AZURE_DEVOPS_PROJECT = "OS"
$env:AZURE_DEVOPS_REPO = "os.2020"
$env:AZURE_DEVOPS_BRANCH = "official/rs_sparc_ctr_exp"
$env:AZURE_DEVOPS_PAT = "your-pat-token"
```

3. **Restart VS Code**

4. **Test with Copilot Chat**:
   - "List all YAML files in the OS repository"
   - "Show me the .gitignore file"
   - "Search for JSON config files"
   - "Find C++ files in src directory"

### Example Prompts

| User Prompt | What Happens |
|-------------|--------------|
| "List YAML files in the repo" | Calls `search_azure_devops_files` with `extension: "yml"` |
| "Show .gitignore content" | Calls `get_azure_devops_file` with `file_path: ".gitignore"` |
| "Find test files" | Calls `search_azure_devops_files` with `file_pattern: "*test*"` |
| "Search in src/MergedComponents" | Calls `search_azure_devops_files` with `path_pattern: "src/MergedComponents"` |

### Troubleshooting

**Server not starting:**
```bash
# Test manually
cd azure_devops_mcp_server
python -m azure_devops_mcp_server --mode stdio --organization microsoft --project OS --repository os.2020 --auth-mode pat

# Check VS Code Output > MCP for errors
```

**Authentication failing:**
- Verify PAT has "Code (Read)" permission
- Check PAT hasn't expired
- Test with command-line tool first

**Tools not available:**
- Check VS Code Output > MCP for server status
- Verify Python path is correct
- Try absolute Python path in settings

---

## LLMCrawl Gateway Integration

### Architecture

```
User → LLMCrawl Gateway → LLM (GPT-4) → Tools
                ↓
        Azure DevOps MCP Server (HTTP)
                ↓
        Azure DevOps API
```

### Step 1: Add MCP Server to Docker Compose

Create or update `deploy/docker-compose.yml`:

```yaml
services:
  # Existing services...

  azure-devops-mcp:
    build:
      context: ../azure_devops_mcp_server
      dockerfile: Dockerfile
    container_name: azure-devops-mcp-server
    restart: unless-stopped
    ports:
      - "8004:8004"
    environment:
      - MCP_MODE=http
      - MCP_PORT=8004
      - MCP_HOST=0.0.0.0
      - AZURE_DEVOPS_ORG=microsoft
      - AZURE_DEVOPS_PROJECT=OS
      - AZURE_DEVOPS_REPO=os.2020
      - AZURE_DEVOPS_BRANCH=official/rs_sparc_ctr_exp
      - AZURE_DEVOPS_PAT=${AZURE_DEVOPS_PAT}
      - AZURE_DEVOPS_AUTH_MODE=pat
      - AZURE_DEVOPS_MAX_RESULTS=50
    networks:
      - llmcrawl-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8004/health"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  llmcrawl-network:
    driver: bridge
```

### Step 2: Configure Gateway

Update `gateway/config/settings.py`:

```python
class Settings(BaseSettings):
    # ... existing settings ...

    # MCP Server URLs
    AZURE_DEVOPS_MCP_URL: str = "http://azure-devops-mcp:8004"

    # MCP Tool Configuration
    MCP_TOOLS_ENABLED: bool = True
    MCP_TOOLS_TIMEOUT: int = 30
```

### Step 3: Add MCP Tool Loader

Create `gateway/llm/mcp_tools.py`:

```python
"""MCP Tool Integration for LLMCrawl Gateway."""
import httpx
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class MCPToolManager:
    """Manage MCP server tools."""

    def __init__(self, azure_devops_url: str):
        self.azure_devops_url = azure_devops_url
        self._tools_cache = None

    async def get_tools(self) -> List[Dict[str, Any]]:
        """Get all available MCP tools."""
        if self._tools_cache:
            return self._tools_cache

        tools = []

        try:
            # Get Azure DevOps tools
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.azure_devops_url}/tools")
                response.raise_for_status()
                data = response.json()
                tools.extend(data.get("tools", []))

            self._tools_cache = tools
            logger.info(f"Loaded {len(tools)} MCP tools")

        except Exception as e:
            logger.error(f"Failed to load MCP tools: {e}")

        return tools

    async def invoke_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Invoke an MCP tool."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.azure_devops_url}/invoke",
                    json={
                        "tool_name": tool_name,
                        "arguments": arguments
                    }
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error(f"MCP tool invocation failed: {e}")
            return {"success": False, "error": str(e)}
```

### Step 4: Update Chat Handler

Update `gateway/routers/chat.py`:

```python
from gateway.llm.mcp_tools import MCPToolManager
from gateway.config.settings import settings

# Initialize MCP tool manager
mcp_manager = MCPToolManager(settings.AZURE_DEVOPS_MCP_URL)


async def handle_chat(request: ChatRequest):
    """Handle chat request with MCP tools."""

    # Get available tools (including MCP tools)
    tools = []

    # Add MCP tools
    if settings.MCP_TOOLS_ENABLED:
        mcp_tools = await mcp_manager.get_tools()
        tools.extend(mcp_tools)

    # Add other tools...
    # tools.extend(internal_tools)

    # Call LLM with tools
    response = await llm_client.chat(
        messages=request.messages,
        model=request.model,
        tools=tools
    )

    # Handle tool calls
    if response.tool_calls:
        for tool_call in response.tool_calls:
            tool_name = tool_call.name
            arguments = tool_call.arguments

            # Check if it's an MCP tool
            if tool_name.startswith("search_azure_devops_") or \
               tool_name.startswith("get_azure_devops_"):
                result = await mcp_manager.invoke_tool(tool_name, arguments)
                # Add result to conversation
            else:
                # Handle internal tools
                pass

    return response
```

### Step 5: Start Services

```bash
# Set PAT in .env file
echo "AZURE_DEVOPS_PAT=your-pat-token" >> .env

# Start all services
cd deploy
docker-compose up -d

# Check health
curl http://localhost:8004/health
curl http://localhost:8000/health

# View logs
docker-compose logs -f azure-devops-mcp
```

### Step 6: Test Integration

```python
# Test via API
import httpx

async def test_chat():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/chat",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "List all YAML files in the OS repository"
                    }
                ],
                "model": "gpt-4",
                "stream": False
            }
        )
        print(response.json())
```

Or use the test script:

```bash
cd azure_devops_mcp_server/tests
python test_integration.py gateway
```

### Example Flow

1. **User**: "Find JSON config files in src/MergedComponents"

2. **Gateway** → **LLM**: Provides tools including `search_azure_devops_files`

3. **LLM** → **Gateway**: Calls tool with:
   ```json
   {
     "name": "search_azure_devops_files",
     "arguments": {
       "path_pattern": "src/MergedComponents",
       "extension": "json"
     }
   }
   ```

4. **Gateway** → **MCP Server**: POST to `/invoke`

5. **MCP Server** → **Azure DevOps API**: Searches repository

6. **Results** ← **MCP Server** ← **Azure DevOps API**

7. **Gateway** ← **MCP Server**: Returns file list

8. **LLM** ← **Gateway**: Provides tool results

9. **User** ← **LLM**: "I found 5 JSON config files in src/MergedComponents: ..."

### Monitoring

```bash
# Check MCP server health
curl http://localhost:8004/health

# View available tools
curl http://localhost:8004/tools | jq

# Test tool invocation
curl -X POST http://localhost:8004/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "search_azure_devops_files",
    "arguments": {"extension": "yml"}
  }' | jq

# View logs
docker-compose logs -f azure-devops-mcp
```

### Security Considerations

1. **PAT Security**:
   - Store PAT in `.env` file (not in docker-compose.yml)
   - Never commit PAT to git
   - Use minimal required scopes (Code: Read)
   - Rotate PATs regularly

2. **Network Security**:
   - Keep MCP server in private Docker network
   - Don't expose port 8004 publicly
   - Use gateway as single public entry point

3. **Rate Limiting**:
   - Implement rate limits in gateway
   - Cache frequently accessed files
   - Set reasonable max_results defaults

---

## Production Deployment

### Environment Variables

```bash
# .env file
AZURE_DEVOPS_PAT=your-pat-token-here
AZURE_DEVOPS_ORG=microsoft
AZURE_DEVOPS_PROJECT=OS
AZURE_DEVOPS_REPO=os.2020
AZURE_DEVOPS_BRANCH=official/rs_sparc_ctr_exp
AZURE_DEVOPS_MAX_RESULTS=50
```

### Docker Compose Production

```yaml
services:
  azure-devops-mcp:
    image: azure-devops-mcp-server:latest
    restart: always
    environment:
      - MCP_MODE=http
      - AZURE_DEVOPS_PAT=${AZURE_DEVOPS_PAT}
    networks:
      - internal
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Health Checks

```bash
# Gateway health check endpoint should check MCP server
curl http://gateway:8000/health

# Response includes MCP server status:
{
  "status": "healthy",
  "services": {
    "azure_devops_mcp": {
      "status": "healthy",
      "url": "http://azure-devops-mcp:8004"
    }
  }
}
```

---

## Troubleshooting

### Common Issues

**MCP server not responding:**
```bash
# Check container is running
docker ps | grep azure-devops-mcp

# Check logs
docker logs azure-devops-mcp-server

# Test directly
curl http://localhost:8004/health
```

**Authentication errors:**
```bash
# Verify PAT
echo $AZURE_DEVOPS_PAT

# Test with CLI tool
cd tests
python test_search.py --filter "ext:txt"
```

**Gateway can't reach MCP server:**
```bash
# Check network
docker network inspect llmcrawl-network

# Test from gateway container
docker exec web-rag-gateway-dev curl http://azure-devops-mcp:8004/health
```

**Slow responses:**
- Use non-recursive searches by default
- Set reasonable max_results
- Implement caching in gateway
- Consider indexing frequently accessed files

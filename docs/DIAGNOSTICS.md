# Diagnostics and Troubleshooting Guide

This guide helps you debug issues with LLMCrawl after deployment. It covers viewing logs, diagnosing common problems, and step-by-step troubleshooting.

## Table of Contents

- [Viewing Logs](#viewing-logs)
- [Service Status](#service-status)
- [Visual Diagnostics with Monitoring](#visual-diagnostics-with-monitoring)
- [Debugging Specific Issues](#debugging-specific-issues)
  - [Crawling Not Working](#1-crawling-not-working)
  - [What URLs Does LLM Crawl](#2-what-urls-does-llm-crawl)
  - [Agent Behavior](#3-agent-behavior)
  - [Embedding Issues](#4-embedding-issues)
  - [Tool Calls](#5-tool-calls)
- [Common Errors and Solutions](#common-errors-and-solutions)
- [Quick Debugging Checklist](#quick-debugging-checklist)
- [Advanced Diagnostics](#advanced-diagnostics)

---

## Viewing Logs

### View All Service Logs

```powershell
# Follow all logs in real-time (Ctrl+C to exit)
llmcrawl deploy --logs

# View logs without following (snapshot)
llmcrawl deploy --logs --no-follow
```

### View Specific Service Logs

```powershell
# Gateway (LLM agent, tool calls, orchestration)
llmcrawl deploy --logs gateway

# Crawler (web crawling, authentication)
llmcrawl deploy --logs crawler

# Indexer (embedding, vector storage)
llmcrawl deploy --logs indexer

# MCP Server (Azure DevOps, local file access)
llmcrawl deploy --logs mcp-server

# Qdrant vector database
llmcrawl deploy --logs qdrant
```

### Docker Compose Direct Access

```powershell
cd llmcrawl-deploy

# Follow specific service logs
docker compose logs -f gateway

# Last N lines
docker compose logs --tail=100 crawler

# Multiple services
docker compose logs -f gateway crawler

# With timestamps
docker compose logs -f --timestamps gateway
```

### Filter Logs with PowerShell

```powershell
# Search for errors
llmcrawl deploy --logs --no-follow | Select-String -Pattern "error|Error|ERROR"

# Search for specific URL
docker compose logs crawler | Select-String -Pattern "osgwiki"

# Search for tool calls
docker compose logs gateway | Select-String -Pattern "tool|Tool"
```

---

## Service Status

### Check All Services

```powershell
llmcrawl deploy --status
```

Expected output:
```
📊 LLMCrawl Service Status
============================================================
NAME                  STATUS    PORTS
gateway               Up        0.0.0.0:8000->8000/tcp
crawler               Up        0.0.0.0:8001->8001/tcp
indexer               Up        0.0.0.0:8002->8002/tcp
mcp-server            Up        0.0.0.0:8003->8003/tcp
qdrant                Up        0.0.0.0:6333->6333/tcp
hichat                Up        0.0.0.0:8080->8080/tcp
```

### Health Check APIs

```powershell
# Gateway health
Invoke-RestMethod -Uri "http://localhost:8000/health"

# Crawler health
Invoke-RestMethod -Uri "http://localhost:8001/health"

# Indexer health
Invoke-RestMethod -Uri "http://localhost:8002/health"

# Qdrant health
Invoke-RestMethod -Uri "http://localhost:6333/health"
```

---

## Visual Diagnostics with Monitoring

For visual health monitoring without reading logs, use the Prometheus/Grafana monitoring stack.

### Starting the Monitoring Stack

The monitoring services (Prometheus + Grafana) are optional and require a separate startup:

```powershell
cd llmcrawl-deploy

# Start monitoring alongside existing services
docker compose --profile monitoring up -d
```

This starts:
- **Prometheus** (http://localhost:9090) - Metrics collection
- **Grafana** (http://localhost:3001) - Visual dashboards

### Quick Health Check with Prometheus

Open http://localhost:9090 and use these queries:

| What to Check | Prometheus Query | Meaning |
|---------------|------------------|---------|
| **All services up?** | `up` | 1 = running, 0 = down |
| **Error rate** | `rate(http_requests_total{status=~"5.."}[5m])` | 5xx errors per second |
| **Request latency (P95)** | `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))` | 95th percentile response time |
| **Request rate** | `rate(http_requests_total[5m])` | Requests per second per service |

**How to use:**
1. Open http://localhost:9090
2. Paste a query in the search box
3. Click **Execute**
4. Switch to **Graph** tab for visualization

### Grafana Dashboard

1. Open http://localhost:3001
2. Login with `admin` / `admin`
3. Go to **Dashboards** → **New** → **Import**
4. Create panels using Prometheus queries above

### Quick Visual Checks

**Is everything running?**
```
Query: up
Result: All values should be 1
```

**Any errors happening?**
```
Query: rate(http_requests_total{status=~"5.."}[5m])
Result: Should be 0 or very low
```

**Is the system slow?**
```
Query: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
Result: < 2s for chat, < 30s for crawl operations
```

### Qdrant Dashboard

For vector database health, use the built-in Qdrant dashboard:

1. Open http://localhost:6333/dashboard
2. Check:
   - Collections exist (should see `llmcrawl_docs` or similar)
   - Point count > 0 (documents have been indexed)
   - No error messages

### Stopping Monitoring

```powershell
cd llmcrawl-deploy
docker compose --profile monitoring down
```

> **Note:** Stopping monitoring doesn't affect the main LLMCrawl services.

For complete monitoring documentation, see [MONITORING.md](MONITORING.md).

---

## Debugging Specific Issues

### 1. Crawling Not Working

**Symptoms:**
- "Could not fetch content from URL"
- Empty results from web searches
- Timeout errors

**Check crawler logs:**
```powershell
llmcrawl deploy --logs crawler
```

**What to look for:**
```
❌ Error crawling URL: https://...
🔒 Authentication required for: https://...
⏱️ Timeout fetching: https://...
🚫 Blocked by robots.txt: https://...
```

**Test crawler directly:**
```powershell
$body = @{
    query = "test"
    seed_urls = @("https://example.com")
    max_results = 1
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8001/crawl" -Method POST -ContentType "application/json" -Body $body
```

**Common fixes:**

| Problem | Solution |
|---------|----------|
| Authentication required | Run `llmcrawl auth <url>` to capture cookies |
| Connection timeout | Check network, increase timeout in `.env` |
| Robots.txt blocked | Site doesn't allow crawling |
| SSL certificate error | Check system certificates |
| FireCrawl unavailable | Check FireCrawl container, API key |

**Check authentication cookies:**
```powershell
# View loaded cookies in crawler logs
docker compose logs crawler | Select-String -Pattern "cookie|Cookie|auth"
```

---

### 2. What URLs Does LLM Crawl

**Gateway logs show crawl decisions:**
```powershell
docker compose logs gateway | Select-String -Pattern "crawl|seed_urls|Crawling"
```

**Look for:**
```
🔍 Tool call: web_search with URLs: ['https://...', 'https://...']
📄 Crawled 3 documents from seed URLs
✅ Indexed 3 documents for query: ...
```

**Crawler logs show actual fetches:**
```powershell
docker compose logs crawler | Select-String -Pattern "Fetching|Retrieved|Processing"
```

**Look for:**
```
📥 Fetching: https://www.example.com/page1
✅ Retrieved 15,432 bytes from https://...
📝 Extracted 2,341 chars of content
```

---

### 3. Agent Behavior

**View agent workflow:**
```powershell
llmcrawl deploy --logs gateway
```

**Look for the agent flow:**
```
🤖 Agent starting workflow for query: "..."
💭 LLM analyzing query...
🔧 LLM decided to call tool: web_search
📤 Tool input: {"query": "...", "urls": [...]}
📥 Tool output: {"success": true, "docs": [...]}
💬 LLM generating response with citations...
✅ Agent completed successfully
```

**Enable DEBUG logging for more detail:**

Edit `llmcrawl-deploy/.env`:
```bash
LOG_LEVEL=DEBUG
```

Restart services:
```powershell
llmcrawl deploy --down
llmcrawl deploy --up
```

**Debug prompts and LLM responses:**
With `LOG_LEVEL=DEBUG`, you'll see:
- Full system prompts sent to LLM
- LLM's raw response including reasoning
- Tool call arguments
- Context retrieved from vector DB

---

### 4. Embedding Issues

**Symptoms:**
- "No relevant documents found"
- Search returns wrong results
- Indexer errors

**Check indexer logs:**
```powershell
llmcrawl deploy --logs indexer
```

**Look for:**
```
📥 Indexing document: "Page Title"
🔢 Generated embedding (1536 dimensions)
✅ Stored in Qdrant collection: llmcrawl_docs
❌ Embedding failed: Invalid API key
❌ Qdrant connection refused
```

**Check Qdrant dashboard:**
```powershell
Start-Process "http://localhost:6333/dashboard"
```

In the dashboard:
- Check if collections exist
- View point count (should be > 0 after indexing)
- Verify vector dimensions (1536 for OpenAI, 768 for some Azure models)

**Test indexer API:**
```powershell
# Health check
Invoke-RestMethod -Uri "http://localhost:8002/health"

# Search test
$body = @{
    query = "test query"
    top_k = 5
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8002/search" -Method POST -ContentType "application/json" -Body $body
```

**Common embedding issues:**

| Problem | Solution |
|---------|----------|
| Invalid API key | Check `OPENAI_API_KEY` or `AZURE_OPENAI_*` in `.env` |
| Model not found | Verify `EMBEDDING_MODEL` deployment name |
| Qdrant connection refused | Check if Qdrant container is running |
| Wrong dimensions | Model mismatch between indexing and search |
| Collection not found | Documents haven't been indexed yet |

---

### 5. Tool Calls

**View all tool calls:**
```powershell
docker compose logs gateway | Select-String -Pattern "tool|Tool"
```

**Detailed tool call flow:**
```
🔧 Available tools: ['web_search', 'read_local_file', 'search_code', ...]
🔧 LLM requested tool: web_search
📤 Tool call input: {"query": "latest news", "urls": ["https://..."]}
⏱️ Tool execution started...
📥 Tool result: {"success": true, "documents": [...]}
✅ Tool call completed in 2.3s
```

**Tool errors:**
```
❌ Tool call failed: web_search - Connection refused to crawler
⚠️ Tool timeout after 30s: azure_devops_search
❌ Tool error: read_local_file - File not found: /data/files/missing.txt
```

**Check MCP server for file/Azure DevOps tools:**
```powershell
llmcrawl deploy --logs mcp-server
```

**Test tools directly:**
```powershell
# List available tools
Invoke-RestMethod -Uri "http://localhost:8000/tools"

# Test MCP file listing
Invoke-RestMethod -Uri "http://localhost:8003/list" -Method POST -ContentType "application/json" -Body '{"path": "/"}'
```

---

## Common Errors and Solutions

### Service Startup Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `port already in use` | Another service using the port | Stop conflicting service or change port in `.env` |
| `network webrag-network not found` | Docker network missing | Run `llmcrawl deploy --up` (auto-creates network) |
| `image not found` | Images not built | Run `llmcrawl deploy --up` to build |
| `permission denied` | Docker permissions | Run Docker Desktop as admin, or add user to docker group |

### LLM/API Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Invalid API key` | Wrong or missing API key | Check `OPENAI_API_KEY` or `AZURE_OPENAI_API_KEY` in `.env` |
| `Model not found` | Wrong deployment name | Verify `LLM_MODELS` configuration matches Azure deployment |
| `Rate limit exceeded` | Too many API calls | Reduce request rate, upgrade API tier |
| `Context length exceeded` | Too much text sent to LLM | Reduce `MAX_CONTEXT_TOKENS` in `.env` |
| `Connection refused` | LLM service unreachable | Check network, API endpoint URL |

### Crawler Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Authentication required` | Site needs login | Run `llmcrawl auth <url>` |
| `Cookie expired` | Auth cookies too old | Re-run `llmcrawl auth <url>` |
| `SSL certificate verify failed` | Certificate issues | Check system time, install CA certs |
| `Timeout` | Slow site or network | Increase `CRAWL_TIMEOUT` in `.env` |
| `Playwright error` | Browser issues | Restart crawler container |

### Indexer/Vector DB Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Qdrant connection refused` | Qdrant not running | Check `llmcrawl deploy --status` |
| `Collection not found` | No documents indexed | Crawl some content first |
| `Dimension mismatch` | Wrong embedding model | Ensure consistent model across index/search |
| `Out of memory` | Too many vectors | Increase Qdrant memory, or use disk storage |

### MCP Server Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `File not found` | Wrong path or not mounted | Check `MCP_HOST_FOLDER` in `.env` |
| `Permission denied` | Container can't read files | Check file permissions on host |
| `Azure DevOps 401` | PAT expired or invalid | Generate new PAT, update `.env` |
| `Azure DevOps 404` | Wrong org/project/repo | Verify `AZURE_DEVOPS_*` settings |

### Docker Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Cannot connect to Docker daemon` | Docker not running | Start Docker Desktop |
| `no space left on device` | Disk full | Run `docker system prune` |
| `container unhealthy` | Service failing health checks | Check service logs |
| `OOM killed` | Out of memory | Increase Docker memory limit |

---

## Quick Debugging Checklist

```
□ Services running?          llmcrawl deploy --status
□ Check service logs         llmcrawl deploy --logs <service>
□ API keys configured?       Check .env file
□ Docker running?            docker info
□ Network exists?            docker network ls | grep webrag
□ Qdrant has data?           http://localhost:6333/dashboard
□ Can reach LLM?             Check gateway logs for API errors
□ Auth cookies valid?        Check crawler logs for auth errors
```

---

## Advanced Diagnostics

### Container Resource Usage

```powershell
# Real-time stats
docker stats

# Specific containers
docker stats llmcrawl-gateway llmcrawl-crawler
```

### Enter Container Shell

```powershell
# Gateway container
docker compose exec gateway /bin/bash

# Crawler container
docker compose exec crawler /bin/bash

# Run Python in container
docker compose exec gateway python -c "import httpx; print(httpx.get('http://crawler:8001/health').json())"
```

### Check Container Environment

```powershell
# View environment variables
docker compose exec gateway env | Sort-Object

# Check if API key is set (masked)
docker compose exec gateway env | Select-String "API_KEY"
```

### Network Diagnostics

```powershell
# Check container network
docker network inspect webrag-network

# Test inter-container connectivity
docker compose exec gateway curl http://crawler:8001/health
docker compose exec gateway curl http://indexer:8002/health
```

### Reset Everything

If all else fails:

```powershell
# Stop and remove everything
llmcrawl deploy --down

# Remove volumes (WARNING: deletes indexed data)
docker compose down -v

# Rebuild from scratch
llmcrawl deploy --up
```

---

## Related Documentation

- **[Monitoring Guide](MONITORING.md)** - Prometheus metrics, Grafana dashboards, alerting
- **[Configuration Guide](CONFIGURATION.md)** - All environment variables and settings
- **[Installation Guide](../INSTALL.md)** - Installation and deployment instructions
- **[Architecture Overview](ARCHITECTURE.md)** - System design and components

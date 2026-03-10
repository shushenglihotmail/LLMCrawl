# Diagnostics, Monitoring & Troubleshooting Guide

This guide covers health monitoring, logging, metrics collection, and troubleshooting for the LLMCrawl system.

## Table of Contents

- [Quick Health Check](#quick-health-check)
- [Viewing Logs](#viewing-logs)
- [Service Status](#service-status)
- [Monitoring Stack](#monitoring-stack)
  - [Starting Monitoring](#starting-monitoring)
  - [Prometheus Metrics](#prometheus-metrics)
  - [Grafana Dashboards](#grafana-dashboards)
  - [Alerting](#alerting)
- [Debugging Specific Issues](#debugging-specific-issues)
- [Common Errors and Solutions](#common-errors-and-solutions)
- [Advanced Diagnostics](#advanced-diagnostics)

---

## Quick Health Check

### Using CLI

```bash
llmcrawl deploy --status
llmcrawl deploy --health
```

### Using Make

```bash
make health
```

### Using curl

```bash
curl http://localhost:8000/health  # Gateway
curl http://localhost:8001/health  # Crawler
curl http://localhost:8002/health  # Indexer
curl http://localhost:8003/health  # MCP Server
curl http://localhost:6333/health  # Qdrant
```

### Health Response Format

```json
{
  "status": "healthy",
  "service": "gateway",
  "timestamp": "2025-11-15T10:30:00.123456",
  "version": "1.0.0",
  "components": {
    "crawler": "healthy",
    "indexer": "healthy",
    "llm": "healthy"
  }
}
```

**Status Values:**
- `healthy`: All components operational
- `degraded`: Service running but some components failing
- `unhealthy`: Service not functional

---

## Viewing Logs

### All Service Logs

```powershell
# Follow all logs in real-time
llmcrawl deploy --logs

# Snapshot (no follow)
llmcrawl deploy --logs --no-follow
```

### Specific Service Logs

```powershell
llmcrawl deploy --logs gateway    # LLM agent, tool calls
llmcrawl deploy --logs crawler    # Web crawling, auth
llmcrawl deploy --logs indexer    # Embedding, vector storage
llmcrawl deploy --logs azure-devops-mcp-server # Azure DevOps code search
llmcrawl deploy --logs qdrant     # Vector database
```

### Docker Compose Direct Access

```powershell
cd llmcrawl-deploy

# Follow specific service
docker compose logs -f gateway

# Last N lines
docker compose logs --tail=100 crawler

# With timestamps
docker compose logs -f --timestamps gateway
```

### Filter Logs

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
azure-devops-mcp      Up        0.0.0.0:8004->8004/tcp
qdrant                Up        0.0.0.0:6333->6333/tcp
hichat                Up        0.0.0.0:8080->8080/tcp
```

### Health Check APIs

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health"
Invoke-RestMethod -Uri "http://localhost:8001/health"
Invoke-RestMethod -Uri "http://localhost:8002/health"
Invoke-RestMethod -Uri "http://localhost:6333/health"
```

---

## Monitoring Stack

### Starting Monitoring

The Prometheus + Grafana monitoring stack is optional:

```bash
# Start with monitoring profile
llmcrawl deploy --up --profile monitoring

# Or using docker compose
cd llmcrawl-deploy
docker compose --profile monitoring up -d
```

This starts:
- **Prometheus** (http://localhost:9090): Metrics collection
- **Grafana** (http://localhost:3001): Visual dashboards (admin/admin)

### Prometheus Metrics

#### Metrics Endpoints

All services expose Prometheus-compatible metrics:

```bash
curl http://localhost:8000/metrics  # Gateway
curl http://localhost:8001/metrics  # Crawler
curl http://localhost:8002/metrics  # Indexer
```

#### Available Metrics

**HTTP Request Metrics:**
```promql
# Total requests by handler, method, and status
http_requests_total{handler="/agent/chat", method="POST", status="2xx"}

# Request duration histogram
http_request_duration_seconds_bucket{handler="/agent/chat", le="1.0"}
```

**System Metrics:**
```promql
# CPU usage
process_cpu_seconds_total

# Memory usage
process_resident_memory_bytes
process_virtual_memory_bytes
```

#### Useful Prometheus Queries

**Service Availability:**
```promql
# Check which services are up
up{job=~"gateway|crawler|indexer"}

# Service uptime in hours
(time() - process_start_time_seconds) / 3600
```

**Performance Monitoring:**
```promql
# Request rate per service
sum(rate(http_requests_total[5m])) by (job)

# 95th percentile latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Error rate
sum(rate(http_requests_total{status=~"5.."}[5m])) by (job)

# Error percentage
sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100
```

**Resource Usage:**
```promql
# Memory usage in MB
process_resident_memory_bytes / 1024 / 1024

# CPU usage percentage (approximate)
rate(process_cpu_seconds_total[5m]) * 100
```

#### Quick Visual Checks via Prometheus

Open http://localhost:9090 and use these queries:

| What to Check | Query | Expected |
|---------------|-------|----------|
| All services up? | `up` | All values = 1 |
| Error rate | `rate(http_requests_total{status=~"5.."}[5m])` | 0 or very low |
| Is system slow? | `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))` | < 2s chat, < 30s crawl |

### Grafana Dashboards

#### Initial Setup

1. Access Grafana: http://localhost:3001
2. Login: admin / admin
3. Datasource: Prometheus auto-configured at http://prometheus:9090

#### Create Dashboard Panels

**Service Health Panel:**
- Panel Type: Stat
- Query: `up{job="gateway"}`
- Thresholds: Red < 1, Green >= 1

**Request Rate Panel:**
- Panel Type: Time series
- Query: `sum(rate(http_requests_total[5m])) by (job)`
- Legend: `{{job}}`

**Response Time (P95) Panel:**
- Panel Type: Time series
- Query: `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, job))`

**Memory Usage Panel:**
- Panel Type: Time series
- Query: `process_resident_memory_bytes{job=~"gateway|crawler|indexer"} / 1024 / 1024`
- Unit: MB

### Alerting

#### Prometheus Alert Rules

Create alert rules in `deploy/prometheus-alerts.yml`:

```yaml
groups:
  - name: llmcrawl_alerts
    rules:
      - alert: ServiceDown
        expr: up{job=~"gateway|crawler|indexer"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.job }} is down"

      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m])) by (job)
          / sum(rate(http_requests_total[5m])) by (job) > 0.05
        for: 2m
        labels:
          severity: warning

      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 5
        for: 5m
        labels:
          severity: warning

      - alert: HighMemoryUsage
        expr: process_resident_memory_bytes > 1073741824
        for: 5m
        labels:
          severity: warning
```

### Stopping Monitoring

```powershell
cd llmcrawl-deploy
docker compose --profile monitoring down
```

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

**Look for:**
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

**Solutions:**

| Problem | Solution |
|---------|----------|
| Authentication required | Run `llmcrawl auth <url>` |
| Connection timeout | Check network, increase timeout |
| Robots.txt blocked | Site doesn't allow crawling |
| SSL certificate error | Check system certificates |

### 2. What URLs Does LLM Crawl

**Gateway logs show crawl decisions:**
```powershell
docker compose logs gateway | Select-String -Pattern "crawl|seed_urls|Crawling"
```

**Crawler logs show actual fetches:**
```powershell
docker compose logs crawler | Select-String -Pattern "Fetching|Retrieved|Processing"
```

### 3. Agent Behavior

**View agent workflow:**
```powershell
llmcrawl deploy --logs gateway
```

**Look for:**
```
🤖 Agent starting workflow for query: "..."
💭 LLM analyzing query...
🔧 LLM decided to call tool: web_search
📤 Tool input: {"query": "...", "urls": [...]}
📥 Tool output: {"success": true, "docs": [...]}
✅ Agent completed successfully
```

**Enable DEBUG logging:**
Edit `llmcrawl-deploy/.env`:
```bash
LOG_LEVEL=DEBUG
```

Restart:
```powershell
llmcrawl deploy --down && llmcrawl deploy --up
```

### 4. Embedding/Indexer Issues

**Symptoms:**
- "No relevant documents found"
- Search returns wrong results

**Check indexer logs:**
```powershell
llmcrawl deploy --logs indexer
```

**Check Qdrant dashboard:**
Open http://localhost:6333/dashboard
- Check if collections exist
- View point count (should be > 0)

**Test indexer:**
```powershell
Invoke-RestMethod -Uri "http://localhost:8002/health"
```

### 5. Tool Calls

**View all tool calls:**
```powershell
docker compose logs gateway | Select-String -Pattern "tool|Tool"
```

**Check Azure DevOps MCP server:**
```powershell
llmcrawl deploy --logs azure-devops-mcp-server
```

---

## Common Errors and Solutions

### Service Startup Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `port already in use` | Port conflict | Stop conflicting service or change port in `.env` |
| `network not found` | Network missing | Run `llmcrawl deploy --up` |
| `image not found` | Images not built | Run `llmcrawl deploy --up` |
| `permission denied` | Docker permissions | Run Docker Desktop as admin |

### LLM/API Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Invalid API key` | Wrong/missing key | Check `.env` file |
| `Model not found` | Wrong deployment | Verify `LLM_MODELS` matches Azure deployment |
| `Rate limit exceeded` | Too many calls | Reduce rate, upgrade API tier |
| `Context length exceeded` | Too much text | Reduce `MAX_CONTEXT_TOKENS` |

### Crawler Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Authentication required` | Site needs login | Run `llmcrawl auth <url>` |
| `Cookie expired` | Old auth cookies | Re-run `llmcrawl auth <url>` |
| `SSL verify failed` | Certificate issues | Check system time, install CA certs |
| `Timeout` | Slow network | Increase `CRAWL_TIMEOUT` |

### Indexer/Vector DB Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Qdrant connection refused` | Qdrant not running | Check `llmcrawl deploy --status` |
| `Collection not found` | No documents indexed | Crawl some content first |
| `Dimension mismatch` | Wrong embedding model | Ensure consistent model |

### Azure DevOps MCP Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Azure DevOps 401` | PAT expired | Generate new PAT |
| `Azure DevOps 403` | Insufficient permissions | Check PAT scopes |
| `Repository not found` | Wrong repo/project | Verify AZURE_DEVOPS_* settings |

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
docker stats
docker stats llmcrawl-gateway llmcrawl-crawler
```

### Enter Container Shell

```powershell
docker compose exec gateway /bin/bash
docker compose exec crawler /bin/bash
```

### Check Container Environment

```powershell
docker compose exec gateway env | Sort-Object
docker compose exec gateway env | Select-String "API_KEY"
```

### Network Diagnostics

```powershell
docker network inspect webrag-network
docker compose exec gateway curl http://crawler:8001/health
docker compose exec gateway curl http://indexer:8002/health
```

### Reset Everything

```powershell
# Stop and remove everything
llmcrawl deploy --down

# Remove volumes (WARNING: deletes indexed data)
docker compose down -v

# Rebuild from scratch
llmcrawl deploy --up
```

---

## Performance Baselines

Establish normal operating ranges:

| Metric | Normal Range |
|--------|--------------|
| Request rate | Varies by traffic |
| Response time (P95) | < 2s chat, < 30s crawl |
| Error rate | < 1% |
| Memory: Gateway | ~200MB |
| Memory: Crawler | ~500MB |
| Memory: Indexer | ~400MB |
| CPU usage | < 50% average |

---

## Related Documentation

- **[CONFIGURATION.md](CONFIGURATION.md)** - Environment variables and settings
- **[INSTALL.md](INSTALL.md)** - Installation and deployment
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design and components
- **[AUTHENTICATION.md](AUTHENTICATION.md)** - Authentication setup

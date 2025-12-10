# Monitoring and Health Checks

This guide covers health monitoring, metrics collection, and observability for the LLMCrawl system.

## Table of Contents

- [Quick Start](#quick-start)
- [Health Checks](#health-checks)
- [Prometheus Metrics](#prometheus-metrics)
- [Application Metrics Reference](#application-metrics-reference)
- [Grafana Dashboards](#grafana-dashboards)
- [Setting Up Grafana](#setting-up-grafana)
- [Alerting](#alerting)
- [Troubleshooting](#troubleshooting)

## Quick Start

### Start Monitoring Stack

```bash
# Start all services with monitoring
docker-compose --profile monitoring up -d

# Or use Make command
make monitoring-up
```

This starts:
- **Prometheus** (Port 9090): Metrics collection and queries
- **Grafana** (Port 3001): Visual dashboards and alerts
- **All service metrics endpoints** (Port :8000-8002/metrics)

### Access Dashboards

- **Prometheus UI**: http://localhost:9090
- **Grafana**: http://localhost:3001 (default: admin/admin)
- **Qdrant Dashboard**: http://localhost:6333/dashboard

## Health Checks

### Using Make Commands

```bash
# Check all services
make health

# Check individual services
make health-gateway
make health-crawler
make health-indexer
```

### Using curl Commands

```bash
# Gateway service
curl http://localhost:8000/health

# Crawler service
curl http://localhost:8001/health

# Indexer service
curl http://localhost:8002/health

# Qdrant vector database
curl http://localhost:6333/health
```

### Health Check Response Format

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

### Component-Level Health

Each service reports health of its dependencies:

**Gateway Service:**
- LLM connection (OpenAI/Azure)
- Crawler service connectivity
- Indexer service connectivity
- Redis conversation store

**Crawler Service:**
- FireCrawl API availability
- Playwright browser pool
- Trafilatura extractor
- Robots.txt checker

**Indexer Service:**
- Embedding model (OpenAI/Azure)
- Vector database (Qdrant/pgvector)
- LlamaIndex pipeline

## Prometheus Metrics

### Metrics Endpoints

All services expose Prometheus-compatible metrics:

```bash
# Gateway metrics
curl http://localhost:8000/metrics

# Crawler metrics
curl http://localhost:8001/metrics

# Indexer metrics
curl http://localhost:8002/metrics

# Or use Make commands
make metrics-gateway
make metrics-crawler
make metrics-indexer
make metrics-all
```

### Available Metrics

#### HTTP Request Metrics

```promql
# Total requests by handler, method, and status
http_requests_total{handler="/agent/chat", method="POST", status="2xx"}

# Request duration histogram
http_request_duration_seconds_bucket{handler="/agent/chat", le="1.0"}

# Request size
http_request_size_bytes_sum{handler="/agent/chat"}

# Response size
http_response_size_bytes_sum{handler="/agent/chat"}
```

#### System Metrics

```promql
# CPU usage
process_cpu_seconds_total

# Memory usage
process_resident_memory_bytes
process_virtual_memory_bytes

# File descriptors
process_open_fds
process_max_fds

# Python garbage collection
python_gc_collections_total{generation="0"}
```

#### Application Metrics

```promql
# Service uptime
up{job="gateway"}
up{job="crawler"}
up{job="indexer"}

# HTTP error rate
rate(http_requests_total{status=~"5.."}[5m])

# Request rate (requests per second)
rate(http_requests_total[5m])

# 95th percentile latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

### Prometheus Configuration

Scrape targets are configured in `deploy/prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'gateway'
    static_configs:
      - targets: ['gateway:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s

  - job_name: 'crawler'
    static_configs:
      - targets: ['crawler:8001']
    metrics_path: '/metrics'
    scrape_interval: 15s

  - job_name: 'indexer'
    static_configs:
      - targets: ['indexer:8002']
    metrics_path: '/metrics'
    scrape_interval: 15s

  - job_name: 'qdrant'
    static_configs:
      - targets: ['qdrant:6333']
    metrics_path: '/metrics'
    scrape_interval: 30s

  # Note: FireCrawl doesn't expose Prometheus metrics
  # Monitor FireCrawl health via crawler service health checks instead
```

**Monitored Services:**
- Gateway (port 8000)
- Crawler (port 8001)
- Indexer (port 8002)
- Qdrant (port 6333)

**Note:** FireCrawl is not directly monitored by Prometheus as it doesn't expose a `/metrics` endpoint. Monitor FireCrawl availability through the crawler service health checks instead.

### Useful Prometheus Queries

#### Service Availability

```promql
# Check which services are up
up{job=~"gateway|crawler|indexer"}

# Service uptime in hours
(time() - process_start_time_seconds) / 3600
```

#### Performance Monitoring

```promql
# Request rate per service
sum(rate(http_requests_total[5m])) by (job)

# Average response time
rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])

# Error rate (requests per second)
sum(rate(http_requests_total{status=~"5.."}[5m])) by (job)

# Error percentage
sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100
```

#### Resource Usage

```promql
# Memory usage in MB
process_resident_memory_bytes / 1024 / 1024

# CPU usage percentage (approximate)
rate(process_cpu_seconds_total[5m]) * 100

# File descriptor usage
process_open_fds / process_max_fds * 100
```

## Application Metrics Reference

LLMCrawl exposes comprehensive application-level metrics for monitoring all aspects of the system.

### Service Health Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `service_up` | Gauge | service | Whether the service is up (1) or down (0). Services: gateway, crawler, indexer |
| `service_errors_total` | Counter | service, error_type | Total service-level errors |
| `crawler_service_up` | Gauge | - | Crawler service health |
| `indexer_service_up` | Gauge | - | Indexer service health |

**Example Queries:**
```promql
# Check all services are up
service_up{service=~"gateway|crawler|indexer"}

# Service error rate by type
sum(rate(service_errors_total[5m])) by (service, error_type)
```

### Agent Client Request Metrics

Track all client requests to the agent `/agent/chat` endpoint.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `agent_requests_total` | Counter | workflow, status | Total requests by workflow type |
| `agent_request_duration_seconds` | Histogram | workflow | Request duration |
| `agent_request_errors_total` | Counter | workflow, error_type | Request errors |
| `agent_request_last` | Info | - | Last request details |

**Workflow Types:**
- `general_chat` - Casual conversation
- `code_analysis` - Code review and analysis
- `build_system_analysis` - Build/manifest analysis
- `file_explorer` - File browsing and search

**Example Queries:**
```promql
# Requests per workflow (last hour)
sum(increase(agent_requests_total[1h])) by (workflow)

# Request duration p95 by workflow
histogram_quantile(0.95, sum(rate(agent_request_duration_seconds_bucket[5m])) by (le, workflow))

# Error rate by workflow
sum(rate(agent_request_errors_total[5m])) by (workflow, error_type)

# Success vs error distribution
sum(agent_requests_total) by (status)
```

### Agent Activity Metrics

Track internal agent activities like prefetching, crawling, and LLM interactions.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `agent_activity_total` | Counter | activity, status | Activity count by type |
| `agent_activity_duration_seconds` | Histogram | activity | Activity duration |
| `agent_activity_errors_total` | Counter | activity, error_type | Activity errors |
| `agent_activity_in_progress` | Gauge | activity | Currently running activities |
| `agent_activity_items_total` | Counter | activity | Items processed (files, urls, docs) |

**Activity Types:**
- `expand_paths` - Expanding path patterns to file lists
- `prefetch_azdo` - Fetching Azure DevOps target files
- `prefetch_local` - Fetching local reference files
- `crawl` - Crawling seed URLs
- `llm_loop` - LLM tool calling loop

**Example Queries:**
```promql
# Activities by type (last hour)
sum(increase(agent_activity_total[1h])) by (activity)

# Activity duration p95
histogram_quantile(0.95, sum(rate(agent_activity_duration_seconds_bucket[5m])) by (le, activity))

# Items processed per activity
sum(increase(agent_activity_items_total[1h])) by (activity)

# Activity errors
sum(rate(agent_activity_errors_total[5m])) by (activity, error_type)

# Currently running activities
agent_activity_in_progress
```

### Tool Call Metrics

Track all tool invocations (crawl_and_refresh, read_local_file, etc.).

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `tool_calls_total` | Counter | tool_name, status | Total tool calls |
| `tool_call_duration_seconds` | Histogram | tool_name | Duration per tool |
| `tool_call_errors_total` | Counter | tool_name, error_type | Tool errors |
| `tool_calls_in_progress` | Gauge | tool_name | Active tool calls |
| `tool_call_last` | Info | - | Last tool call details (parameters) |

**Tool Names:**
- `crawl_and_refresh` - Web crawling
- `read_local_file` - Local file access
- `list_files` - Directory listing
- `search_file_content` - Content search
- `get_azure_devops_file` - Azure DevOps file fetch
- `search_azure_devops_code` - Azure DevOps code search

**Example Queries:**
```promql
# Tool calls by name (last hour)
sum(increase(tool_calls_total[1h])) by (tool_name)

# Tool call duration p95
histogram_quantile(0.95, sum(rate(tool_call_duration_seconds_bucket[5m])) by (le, tool_name))

# Tool call errors
sum(rate(tool_call_errors_total[5m])) by (tool_name, error_type)

# Success vs error rate per tool
sum(tool_calls_total) by (tool_name, status)
```

### Crawl Metrics

Track web crawling operations.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `crawl_requests_total` | Counter | status, domain, source | Crawl requests |
| `crawl_duration_seconds` | Histogram | domain, source | Crawl duration |
| `crawl_pages_processed_total` | Counter | domain, source | Pages processed |
| `crawl_bytes_downloaded_total` | Counter | domain, source | Bytes downloaded |

**Source Types:**
- `firecrawl` - FireCrawl API
- `playwright` - Playwright browser rendering

**Example Queries:**
```promql
# Crawl requests by source (Firecrawl vs Playwright)
sum(increase(crawl_requests_total[1h])) by (source)

# Crawl duration p95 by source
histogram_quantile(0.95, sum(rate(crawl_duration_seconds_bucket[5m])) by (le, source))

# Pages processed by domain
sum(increase(crawl_pages_processed_total[1h])) by (domain)

# Crawl success/error rate
sum(crawl_requests_total) by (status)
```

### LLM Request Metrics

Track LLM API calls.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `llm_requests_total` | Counter | provider, model, status | Total LLM requests |
| `llm_request_duration_seconds` | Histogram | provider, model | Request duration |
| `llm_tokens_total` | Counter | provider, model, token_type | Token usage |
| `llm_request_size_bytes` | Histogram | provider, model | Request payload size |
| `llm_response_size_bytes` | Histogram | provider, model | Response payload size |
| `llm_errors_total` | Counter | provider, model, error_type | LLM errors |

**Providers:**
- `openai` - OpenAI API
- `azure` - Azure OpenAI
- `anthropic` - Anthropic Claude

**Token Types:**
- `input` - Prompt tokens
- `output` - Completion tokens

**Example Queries:**
```promql
# LLM requests by provider and model
sum(increase(llm_requests_total[1h])) by (provider, model)

# LLM request duration p95
histogram_quantile(0.95, sum(rate(llm_request_duration_seconds_bucket[5m])) by (le, provider, model))

# Token usage (input vs output)
sum(increase(llm_tokens_total[1h])) by (provider, model, token_type)

# LLM errors
sum(rate(llm_errors_total[5m])) by (provider, model, error_type)

# Success rate
sum(llm_requests_total{status="success"}) / sum(llm_requests_total) * 100
```

### Indexer Metrics

Track document indexing and retrieval.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `indexer_index_requests_total` | Counter | status | Index requests |
| `indexer_index_duration_seconds` | Histogram | - | Indexing duration |
| `indexer_documents_indexed_total` | Counter | - | Documents indexed |
| `indexer_chunks_created_total` | Counter | - | Chunks created |
| `indexer_retrieve_requests_total` | Counter | status | Retrieve requests |
| `indexer_retrieve_duration_seconds` | Histogram | - | Retrieval duration |

**Example Queries:**
```promql
# Documents indexed (last hour)
sum(increase(indexer_documents_indexed_total[1h]))

# Index/retrieve duration p95
histogram_quantile(0.95, sum(rate(indexer_index_duration_seconds_bucket[5m])) by (le))
histogram_quantile(0.95, sum(rate(indexer_retrieve_duration_seconds_bucket[5m])) by (le))

# Chunks per document ratio
sum(increase(indexer_chunks_created_total[1h])) / sum(increase(indexer_documents_indexed_total[1h]))
```

## Grafana Dashboards

### Pre-built Dashboard

LLMCrawl includes a pre-built Grafana dashboard with all the key metrics. The dashboard is automatically provisioned when you start the monitoring stack.

**Dashboard File:** `deploy/grafana-provisioning/dashboards/llmcrawl-overview.json`

**Dashboard Sections:**
1. **Service Health** - Gateway, Crawler, Indexer status
2. **Tool Calls** - Tool usage, duration, errors
3. **Crawling** - Firecrawl vs Playwright, pages by domain
4. **LLM Requests** - Provider/model usage, tokens, duration
5. **Indexing** - Documents indexed, retrieval performance
6. **Agent Requests** - Workflow usage, duration, errors
7. **Agent Activities** - Activity breakdown, items processed

## Setting Up Grafana

### Step 1: Start the Monitoring Stack

```bash
# Start all services with monitoring profile
docker-compose --profile monitoring up -d

# Or use Make command
make monitoring-up
```

This starts Prometheus (port 9090) and Grafana (port 3001).

### Step 2: Access Grafana

1. Open your browser to: **http://localhost:3001**
2. Login with default credentials:
   - Username: `admin`
   - Password: `admin`
3. Change password when prompted (or skip for development)

### Step 3: Verify Prometheus Datasource

The Prometheus datasource is auto-configured, but you can verify:

1. Go to **⚙️ Configuration** → **Data sources**
2. You should see **Prometheus** listed
3. Click it and verify:
   - URL: `http://prometheus:9090`
   - Access: `Server (default)`
4. Click **Save & test** to verify connection

**If Prometheus is not listed:**
1. Click **Add data source**
2. Select **Prometheus**
3. Set URL to `http://prometheus:9090`
4. Click **Save & test**

### Step 4: Access the Pre-built Dashboard

1. Go to **📊 Dashboards** → **Browse**
2. Look for **LLMCrawl Overview** dashboard
3. Click to open

**If the dashboard is not visible:**
1. Go to **📊 Dashboards** → **Import**
2. Click **Upload JSON file**
3. Select `deploy/grafana-provisioning/dashboards/llmcrawl-overview.json`
4. Select **Prometheus** as the datasource
5. Click **Import**

### Step 5: Create Custom Queries

To explore metrics interactively:

1. Go to **🔍 Explore** (compass icon in sidebar)
2. Select **Prometheus** datasource
3. Enter a query in the **Metrics browser** or type directly

**Quick Query Examples:**

```promql
# Agent requests by workflow
sum(increase(agent_requests_total[1h])) by (workflow)

# Agent activity duration p95
histogram_quantile(0.95, sum(rate(agent_activity_duration_seconds_bucket[5m])) by (le, activity))

# Tool call errors
sum(rate(tool_call_errors_total[5m])) by (tool_name, error_type)

# LLM token usage
sum(increase(llm_tokens_total[1h])) by (token_type)
```

### Step 6: Create a Custom Dashboard

1. Go to **📊 Dashboards** → **New** → **New Dashboard**
2. Click **Add visualization**
3. Select **Prometheus** datasource

**Example: Agent Request Rate Panel**
1. Query: `sum(rate(agent_requests_total[5m])) by (workflow)`
2. Legend: `{{workflow}}`
3. Title: "Agent Request Rate by Workflow"
4. Panel type: Time series
5. Click **Apply**

**Example: Activity Duration Heatmap**
1. Query: `histogram_quantile(0.95, sum(rate(agent_activity_duration_seconds_bucket[5m])) by (le, activity))`
2. Legend: `{{activity}} p95`
3. Title: "Activity Duration p95"
4. Unit: seconds
5. Click **Apply**

**Example: Success Rate Gauge**
1. Query: `sum(agent_requests_total{status="success"}) / sum(agent_requests_total) * 100`
2. Title: "Agent Success Rate"
3. Panel type: Gauge
4. Unit: percent (0-100)
5. Thresholds: Red < 90, Yellow < 95, Green >= 95
6. Click **Apply**

### Dashboard Tips

- **Time Range**: Use the time picker (top right) to adjust the view window
- **Auto-refresh**: Set refresh interval (e.g., 30s) for live monitoring
- **Variables**: Create template variables for filtering by workflow, activity, etc.
- **Annotations**: Add event annotations for deployments or incidents

### Additional Dashboard Panels

#### Request Rate Panel

**Panel Type:** Time series
**Query:**
```promql
sum(rate(http_requests_total[5m])) by (job)
```
**Legend:** `{{job}}`

#### Response Time (P95) Panel

**Panel Type:** Time series
**Query:**
```promql
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le, job)
)
```

#### Memory Usage Panel

**Panel Type:** Time series
**Query:**
```promql
process_resident_memory_bytes{job=~"gateway|crawler|indexer"} / 1024 / 1024
```
**Unit:** MB

#### Error Rate Panel

**Panel Type:** Time series
**Query:**
```promql
sum(rate(http_requests_total{status=~"5.."}[5m])) by (job, handler)
```

### Pre-built Dashboard (Coming Soon)

We'll provide a ready-to-import JSON dashboard in `deploy/grafana-dashboards/`.

## Alerting

### Prometheus Alert Rules

Create `deploy/prometheus-alerts.yml`:

```yaml
groups:
  - name: llmcrawl_alerts
    interval: 30s
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
        annotations:
          summary: "High error rate on {{ $labels.job }}"

      - alert: HighLatency
        expr: |
          histogram_quantile(0.95,
            rate(http_request_duration_seconds_bucket[5m])
          ) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High latency detected"

      - alert: HighMemoryUsage
        expr: process_resident_memory_bytes > 1073741824
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Memory usage above 1GB on {{ $labels.job }}"
```

### Grafana Alerts

Configure alerts in Grafana:

1. Go to **Alerting** → **Alert rules**
2. Click **New alert rule**
3. Set query and threshold
4. Configure notification channels (email, Slack, etc.)

## Troubleshooting

### No Metrics in Prometheus

**Check if services expose metrics:**
```bash
curl http://localhost:8000/metrics
```

**If 404 error:**
- Services may not have prometheus instrumentation
- Check if containers were rebuilt after adding instrumentation

**Verify Prometheus targets:**
- Open http://localhost:9090/targets
- All targets should show "UP" status

### Grafana Can't Connect to Prometheus

**Check datasource config:**
```bash
# Verify config file exists
ls deploy/grafana-provisioning/datasources/

# Restart Grafana to reload
docker-compose restart grafana
```

**Manual configuration:**
1. Go to **Configuration** → **Data sources**
2. Add Prometheus datasource
3. URL: `http://prometheus:9090`
4. Click **Save & test**

### High Memory Usage

**Check container stats:**
```bash
docker stats

# Or specific service
docker stats web-rag-gateway
```

**View detailed metrics:**
```bash
curl http://localhost:8000/metrics | grep memory
```

**Solutions:**
- Increase container memory limits in `docker-compose.yml`
- Reduce batch sizes for crawling/indexing
- Enable LRU caching with limits

### Service Shows Degraded Status

**Check detailed health:**
```bash
curl http://localhost:8000/health | jq .
```

**Common causes:**
- **Gateway degraded**: LLM API issue, crawler/indexer unreachable
- **Crawler degraded**: FireCrawl API down, Playwright issues
- **Indexer degraded**: Embedding model deployment missing, vector DB unreachable

**Check service logs:**
```bash
docker-compose logs -f gateway
docker-compose logs -f crawler
docker-compose logs -f indexer
```

## Best Practices

### Production Monitoring

1. **Set up alerts** for critical metrics (service down, high error rate)
2. **Monitor resource usage** to prevent OOM kills
3. **Track response times** to detect performance degradation
4. **Monitor error rates** to catch issues early
5. **Set up log aggregation** (ELK, Loki) for troubleshooting

### Performance Baselines

Establish normal operating ranges:

- **Request rate**: Varies by traffic
- **Response time (P95)**: < 2s for chat, < 30s for crawl
- **Error rate**: < 1%
- **Memory usage**: Gateway ~200MB, Crawler ~500MB, Indexer ~400MB
- **CPU usage**: < 50% average

### Regular Checks

```bash
# Daily health check
make health

# Weekly metrics review
make metrics-all

# Monthly capacity planning
docker stats
```

## Additional Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [FastAPI Prometheus Instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator)
- [Qdrant Monitoring](https://qdrant.tech/documentation/guides/monitoring/)

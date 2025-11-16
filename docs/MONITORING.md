# Monitoring and Health Checks

This guide covers health monitoring, metrics collection, and observability for the LLMCrawl system.

## Table of Contents

- [Quick Start](#quick-start)
- [Health Checks](#health-checks)
- [Prometheus Metrics](#prometheus-metrics)
- [Grafana Dashboards](#grafana-dashboards)
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
http_requests_total{handler="/api/v1/chat", method="POST", status="2xx"}

# Request duration histogram
http_request_duration_seconds_bucket{handler="/api/v1/chat", le="1.0"}

# Request size
http_request_size_bytes_sum{handler="/api/v1/chat"}

# Response size
http_response_size_bytes_sum{handler="/api/v1/chat"}
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

## Grafana Dashboards

### Initial Setup

1. **Access Grafana**: http://localhost:3001
2. **Login**: admin / admin (change on first login)
3. **Datasource**: Prometheus is auto-configured at http://prometheus:9090

### Create a Dashboard

1. Go to **Dashboards** → **New** → **New Dashboard**
2. Click **Add visualization**
3. Select **Prometheus** datasource
4. Enter a query (see examples below)
5. Configure visualization type (Time series, Gauge, Stat, etc.)
6. Save dashboard

### Example Dashboard Panels

#### Service Health Panel

**Panel Type:** Stat
**Query:**
```promql
up{job="gateway"}
```
**Thresholds:**
- Red: < 1 (down)
- Green: >= 1 (up)

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

# LLMCrawl Deployment Guide

Complete step-by-step guide for deploying LLMCrawl in development and production environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Development Deployment](#development-deployment)
- [Production Deployment](#production-deployment)
- [MCP Server Configuration](#mcp-server-configuration)
- [Network Configuration](#network-configuration)
- [Service Configuration](#service-configuration)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## Prerequisites

### System Requirements

**Minimum:**
- CPU: 2 cores
- RAM: 4 GB
- Disk: 10 GB free space
- Docker: 20.10+
- Docker Compose: 2.0+

**Recommended:**
- CPU: 4+ cores
- RAM: 8 GB
- Disk: 20 GB free space (SSD preferred)
- Docker: Latest stable
- Docker Compose: Latest stable

### Required API Keys

1. **OpenAI API Key** (Required)
   - Sign up at: https://platform.openai.com
   - Required for LLM responses and embeddings
   - Alternative: Azure OpenAI

2. **FireCrawl API Key** (Optional but recommended)
   - Sign up at: https://firecrawl.dev
   - Improves web crawling quality
   - Free tier available

### Software Dependencies

- **Docker Desktop** (Windows/Mac) or **Docker Engine** (Linux)
- **Git** for cloning repository
- **Text editor** for configuration files
- **curl** or **Postman** for testing

---

## Development Deployment

Development mode enables hot-reload for rapid iteration without rebuilding containers.

### Step 1: Clone Repository

```bash
git clone <repository-url>
cd LLMCrawl
```

### Step 2: Create Environment File

```bash
# Copy template
cd deploy
cp .env.example .env

# Edit with your preferred editor
nano .env  # or vim, code, notepad, etc.
```

**Minimum Required Configuration:**

```bash
# OpenAI Configuration
OPENAI_API_KEY=sk-your-key-here

# Vector Database
VECTOR_DB=qdrant

# Optional: FireCrawl
FIRECRAWL_API_KEY=your-firecrawl-key
```

**Development-Specific Settings:**

```bash
# Enable debug logging
LOG_LEVEL=DEBUG

# Development ports (default)
GATEWAY_PORT=8000
CRAWLER_PORT=8001
INDEXER_PORT=8002
MCP_SERVER_PORT=8003

# Hot-reload enabled by default
```

### Step 3: Configure MCP Server (Local Files)

Edit `docker-compose.yml` to specify which local folder to mount:

```yaml
services:
  mcp-server:
    volumes:
      # Choose your local folder:

      # Windows example:
      - C:/Users/YourName/Documents:/data/files

      # Linux example:
      # - /home/username/projects:/data/files

      # Mac example:
      # - /Users/username/Documents:/data/files

      # Hot-reload for development
      - ./mcp_server:/app/mcp_server:rw
```

**Windows Users:** Ensure Docker Desktop has access to the drive:
1. Open Docker Desktop
2. Settings → Resources → File Sharing
3. Add the drive containing your folder (e.g., C:\)
4. Apply & Restart

### Step 4: Start Development Environment

**Option A: Using Makefile (Recommended)**

```bash
# Start all development services
make dev-up

# View logs
make dev-logs

# Stop services
make dev-down

# Rebuild and restart
make dev-rebuild
```

**Option B: Using Scripts**

```powershell
# Windows PowerShell
.\scripts\setup_dev.ps1   # First time setup
.\scripts\start_dev.ps1   # Start services
```

```bash
# Linux/Mac
python scripts/setup_dev.py  # First time setup
./scripts/start_dev.sh       # Start services
```

**Option C: Manual Docker Compose**

```bash
# Build images
cd deploy && docker-compose build

# Start services
cd deploy && docker-compose up -d

# View logs
cd deploy && docker-compose logs -f
```

### Step 5: Verify Development Setup

```bash
# Check all services are running
docker-compose ps

# Test health endpoints
curl http://localhost:8000/health  # Gateway
curl http://localhost:8001/health  # Crawler
curl http://localhost:8002/health  # Indexer
curl http://localhost:8003/health  # MCP Server

# Test MCP file operations
curl -X POST http://localhost:8003/invoke \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "list_files", "arguments": {"folder_path": "."}}'
```

### Step 6: Development Workflow

**Making Code Changes:**

1. Edit code in your local IDE
2. Changes automatically reload in container (no rebuild needed)
3. Check logs: `docker-compose logs -f gateway`

**Rebuilding After Dependency Changes:**

```bash
# If you modify requirements.txt or Dockerfile
docker-compose build gateway
docker-compose up -d gateway
```

**Stopping Services:**

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

---

## Production Deployment

Production deployment uses optimized images without hot-reload.

### Step 1: Environment Configuration

Create production `.env` file:

```bash
# LLM Configuration
OPENAI_API_KEY=sk-prod-key-here
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4

# Vector Database
VECTOR_DB=qdrant
QDRANT_URL=http://qdrant:6333

# Security
LOG_LEVEL=INFO
ALLOWED_DOMAINS=yourdomain.com,trusteddomain.com
RESPECT_ROBOTS=true

# Performance
MAX_CONCURRENCY=5
CRAWLER_TIMEOUT=25
GATEWAY_TIMEOUT=45

# FireCrawl (Production)
FIRECRAWL_API_KEY=prod-key-here
FIRECRAWL_API_URL=https://api.firecrawl.dev

# MCP Server
MCP_ROOT_FOLDER=/data/files
MCP_SERVER_URL=http://mcp-server:8003
```

### Step 2: Configure Production Services

Edit `deploy/docker-compose.yml`:

**MCP Server Volume (Important):**

```yaml
services:
  mcp-server:
    volumes:
      # Production folder mount
      - /path/to/production/files:/data/files:ro  # :ro for read-only
```

**Network Configuration:**

```yaml
networks:
  webrag-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

### Step 3: Build Production Images

**Option A: Using Makefile (Recommended)**

```bash
# Build all images
make build

# Start production services
make up

# View logs
make logs

# Stop services
make down
```

**Option B: Manual Docker Compose**

```bash
cd deploy/

# Build all images
docker-compose build

# Or build specific services
docker-compose build gateway
docker-compose build crawler
docker-compose build indexer
docker-compose build mcp-server
```

**Production Dockerfile Verification:**

Each Dockerfile should:
- Use multi-stage builds for smaller images
- Run as non-root user
- Include health checks
- Set proper working directory

### Step 4: Deploy Services

**Option A: Using Makefile (Recommended)**

```bash
# Start all services
make up

# View logs
make logs

# Check service health
make health
```

**Option B: Manual Docker Compose**

```bash
# Start all services in background
docker-compose up -d

# View logs
docker-compose logs -f

# Check service status
docker-compose ps
```

**Deployment Order (if starting manually):**

```bash
# 1. Start databases
docker-compose up -d qdrant postgres redis

# 2. Wait for databases to be ready (30 seconds)
sleep 30

# 3. Start application services
docker-compose up -d firecrawl indexer crawler mcp-server

# 4. Wait for services to initialize (15 seconds)
sleep 15

# 5. Start gateway (orchestrator)
docker-compose up -d gateway
```

### Step 5: Production Verification

```bash
# Health checks
curl http://your-domain:8000/health
curl http://your-domain:8001/health
curl http://your-domain:8002/health
curl http://your-domain:8003/health

# Functional test (web RAG)
curl -X POST http://your-domain:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the latest tech news?"}'

# Functional test (MCP file operations)
curl -X POST http://your-domain:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "List files in the documents folder"}'
```

### Step 6: Enable Monitoring (Optional)

```bash
# Start Prometheus and Grafana
docker-compose --profile monitoring up -d

# Access dashboards
# Grafana: http://your-domain:3001 (admin/admin)
# Prometheus: http://your-domain:9090
```

---

## MCP Server Configuration

### Basic Configuration

**Environment Variables:**

```bash
# Container path (inside Docker)
MCP_ROOT_FOLDER=/data/files

# Gateway connection URL
MCP_SERVER_URL=http://mcp-server:8003

# Optional: OpenAI for semantic search
OPENAI_API_KEY=sk-your-key
```

**Volume Mounting Examples:**

```yaml
# Development: Read-write for testing
volumes:
  - C:/Users/Dev/TestFolder:/data/files

# Production: Read-only for security
volumes:
  - /opt/company/documents:/data/files:ro

# Multiple folders (if needed)
volumes:
  - /opt/documents:/data/files
  - /opt/configs:/data/configs:ro
```

### Security Configuration

**Path Validation:**

The MCP server enforces strict path validation:

```python
# Valid paths (relative to root):
"/data/files/subfolder/file.txt"        ✓
"/data/files/../files/file.txt"         ✓ (normalized)
"subfolder/file.txt"                    ✓ (relative)

# Invalid paths (rejected):
"/etc/passwd"                           ✗ (outside root)
"/data/files/../../etc/passwd"          ✗ (traversal attempt)
"C:/Windows/System32/config"            ✗ (absolute outside root)
```

**Read-Only Mount:**

For production, mount volumes as read-only:

```yaml
volumes:
  - /path/to/data:/data/files:ro
```

### Advanced Configuration

**Custom Root Folder:**

```yaml
services:
  mcp-server:
    environment:
      - MCP_ROOT_FOLDER=/custom/path
    volumes:
      - /host/path:/custom/path
```

**Semantic Search Setup:**

```yaml
services:
  mcp-server:
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - MCP_VECTOR_DB_PATH=/data/mcp_vector_db  # Persistent storage
    volumes:
      - /host/files:/data/files
      - mcp_vector_data:/data/mcp_vector_db  # Named volume

volumes:
  mcp_vector_data:
    driver: local
```

**Performance Tuning:**

```yaml
services:
  mcp-server:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 1G
        reservations:
          cpus: '1.0'
          memory: 512M
```

---

## Network Configuration

### Development Network Setup

Development uses `webrag-network` defined in `docker-compose.yml`:

```yaml
networks:
  webrag-network:
    name: webrag-network
    driver: bridge
```

**Connecting Additional Containers:**

```bash
# If a container starts on a different network
docker network connect webrag-network container-name

# Example: Connect manually started MCP server
docker network connect webrag-network web-rag-mcp-server
```

### Production Network Setup

Production uses `deploy_webrag-network`:

```yaml
networks:
  webrag-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

**Network Isolation:**

- All services communicate on internal Docker network
- Only gateway exposes external port (8000)
- Databases not exposed externally

**External Access:**

```yaml
services:
  gateway:
    ports:
      - "8000:8000"  # External access

  # Internal services - no external ports
  crawler:
    expose:
      - "8001"
```

### Reverse Proxy Setup (Production)

**Nginx Example:**

```nginx
upstream llmcrawl_gateway {
    server localhost:8000;
}

server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://llmcrawl_gateway;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support for streaming
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

**Traefik Example:**

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.llmcrawl.rule=Host(`your-domain.com`)"
  - "traefik.http.services.llmcrawl.loadbalancer.server.port=8000"
```

---

## Service Configuration

### Gateway Service

**Key Environment Variables:**

```bash
# LLM Provider
LLM_PROVIDER=openai          # or azure
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-4

# Azure (alternative)
AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com
AZURE_OPENAI_API_KEY=xxx
AZURE_DEPLOYMENT_NAME=gpt-4

# Service URLs
CRAWLER_URL=http://crawler:8001
INDEXER_URL=http://indexer:8002
MCP_SERVER_URL=http://mcp-server:8003

# Timeouts
GATEWAY_TIMEOUT=45
```

### Crawler Service

**Key Environment Variables:**

```bash
# Crawler behavior
RESPECT_ROBOTS=true
ALLOWED_DOMAINS=domain1.com,domain2.com
CRAWLER_TIMEOUT=25

# Playwright
PLAYWRIGHT_HEADLESS=true
PLAYWRIGHT_BROWSER=chromium

# FireCrawl
FIRECRAWL_API_URL=https://api.firecrawl.dev
FIRECRAWL_API_KEY=xxx
```

### Indexer Service

**Key Environment Variables:**

```bash
# Vector Database
VECTOR_DB=qdrant              # or pgvector
QDRANT_URL=http://qdrant:6333

# Embeddings
OPENAI_API_KEY=sk-xxx
EMBEDDING_MODEL=text-embedding-3-large

# Chunking
CHUNK_SIZE=512
CHUNK_OVERLAP=50
```

### MCP Server

**Key Environment Variables:**

```bash
# File access
MCP_ROOT_FOLDER=/data/files

# Semantic search (optional)
OPENAI_API_KEY=sk-xxx
MCP_VECTOR_DB_PATH=/data/mcp_vector_db
```

---

## Troubleshooting

### Service Won't Start

**Check Logs:**

```bash
# All services
docker-compose logs

# Specific service
docker-compose logs mcp-server

# Follow logs in real-time
docker-compose logs -f gateway
```

**Common Issues:**

1. **Port already in use:**
   ```bash
   # Find what's using the port
   netstat -tulpn | grep :8000

   # Change port in docker-compose.yml
   ports:
     - "8080:8000"  # Use 8080 instead
   ```

2. **Out of memory:**
   ```bash
   # Check Docker memory limit
   docker info | grep -i memory

   # Increase in Docker Desktop settings
   # Or reduce concurrency in .env
   MAX_CONCURRENCY=2
   ```

3. **Container exits immediately:**
   ```bash
   # Check exit code
   docker-compose ps

   # View full logs
   docker-compose logs mcp-server

   # Inspect container
   docker inspect mcp-server
   ```

### MCP Server Troubleshooting

**Problem: Gateway can't reach MCP server**

```bash
# 1. Check MCP server is running
docker ps | grep mcp

# 2. Check health
curl http://localhost:8003/health

# 3. Test from gateway container
docker-compose exec gateway curl http://mcp-server:8003/health

# 4. Check network connectivity
docker network inspect webrag-network

# 5. Verify environment variable
docker-compose exec gateway env | grep MCP_SERVER_URL
```

**Problem: "Path not found"**

```bash
# 1. Verify volume is mounted
docker-compose exec mcp-server ls -la /data/files

# 2. Check mount in docker-compose.yml
docker-compose config | grep -A 5 mcp-server

# 3. Windows: Ensure drive sharing in Docker Desktop
# Settings → Resources → File Sharing → Add drive
```

**Problem: Semantic search returns no results**

```bash
# 1. Check if files are indexed
curl -X POST http://localhost:8003/invoke \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "index_files", "arguments": {"folder_path": "."}}'

# 2. Verify OpenAI API key
docker-compose exec mcp-server env | grep OPENAI_API_KEY

# 3. Check vector database
docker-compose exec mcp-server ls -la /data/mcp_vector_db
```

### Network Issues

**Service can't connect to another service:**

```bash
# 1. List networks
docker network ls

# 2. Inspect network
docker network inspect webrag-network

# 3. Check service is on correct network
docker inspect mcp-server | grep -i network

# 4. Connect to correct network if needed
docker network connect webrag-network mcp-server
```

### Performance Issues

**Slow response times:**

```bash
# 1. Check resource usage
docker stats

# 2. Check service logs for bottlenecks
docker-compose logs -f gateway

# 3. Increase timeouts
# Edit .env:
GATEWAY_TIMEOUT=60
CRAWLER_TIMEOUT=40

# 4. Scale services (if using Docker Swarm)
docker-compose up -d --scale crawler=3
```

---

## Best Practices

### Security

1. **Use Environment Variables**: Never hardcode API keys
2. **Read-Only Mounts**: Use `:ro` for production volumes
3. **Minimal Access**: Grant least privilege to MCP server
4. **Network Isolation**: Use Docker networks, don't expose internal ports
5. **Regular Updates**: Keep Docker images updated

### Performance

1. **Resource Limits**: Set CPU/memory limits in production
2. **Persistent Volumes**: Use named volumes for databases
3. **Connection Pooling**: Enabled by default in services
4. **Caching**: Redis caching reduces API calls
5. **Concurrent Requests**: Tune `MAX_CONCURRENCY` for your load

### Monitoring

1. **Health Checks**: Use built-in `/health` endpoints
2. **Logging**: Centralize logs with ELK or similar
3. **Metrics**: Enable Prometheus/Grafana in production
4. **Alerts**: Set up alerts for service failures
5. **Dashboards**: Monitor key metrics (latency, error rate, throughput)

### Maintenance

1. **Backups**: Regular backups of vector database and MCP index
2. **Log Rotation**: Configure log rotation to prevent disk fill
3. **Updates**: Test updates in staging before production
4. **Rollback Plan**: Keep previous Docker images for quick rollback
5. **Documentation**: Document any customizations

---

## Additional Resources

- **[Architecture Guide](ARCHITECTURE.md)** - System design and data flows
- **[MCP Servers Documentation](../mcp_servers/)** - Local access and Azure DevOps MCP servers
- **[Monitoring Setup](MONITORING.md)** - Observability configuration
- **[Authentication Guide](AUTHENTICATION_SETUP.md)** - Crawl authenticated sites
- **[Main README](../README.md)** - Quick start and overview

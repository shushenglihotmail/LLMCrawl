# Development Environment Setup Guide

This guide will help you set up a complete development environment for the LLMCrawl project.

## Prerequisites

- **Python 3.10+** - Required for all services
- **Docker & Docker Compose** - For containerized services
- **Git** - For version control
- **PowerShell** (Windows) - For setup scripts

## Quick Setup

### Option 1: Automated Setup (Recommended)

**Windows (PowerShell):**
```powershell
.\scripts\setup_dev.ps1
```

**Unix/Linux/macOS:**
```bash
python scripts/setup_dev.py
```

### Option 2: Manual Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd LLMCrawl
   ```

2. **Create and activate Python virtual environment:**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # Unix/Linux/macOS
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements/gateway.txt
   pip install -r requirements/crawler.txt
   pip install -r requirements/indexer.txt
   pip install -r requirements/test.txt
   pip install -r requirements/dev.txt
   ```

4. **Install Playwright browsers:**
   ```bash
   playwright install
   playwright install-deps
   ```

5. **Install LLMLingua-2 for prompt compression (Optional but Recommended):**
   ```bash
   # Enables intelligent prompt compression for large contexts
   # Requires ~2GB disk space for model weights
   pip install llmlingua torch transformers accelerate
   ```

6. **Setup pre-commit hooks:**
   ```bash
   pre-commit install
   ```

7. **Configure environment:**
   ```bash
   cd deploy
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

## Configuration

### 1. Environment Variables

Edit the `.env` file with your configuration:

```bash
# Required: OpenAI API Key
OPENAI_API_KEY=your_openai_key_here

# Optional: Azure OpenAI (alternative to OpenAI)
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your_azure_key_here

# Optional: Firecrawl API Key (for better crawling)
FIRECRAWL_API_KEY=your_firecrawl_key_here

# Vector Database (qdrant recommended for development)
VECTOR_DB=qdrant

# Crawling domains (customize as needed)
ALLOWED_DOMAINS=sec.gov,ft.com,wsj.com,nvidia.com,reuters.com,bloomberg.com
```

### 2. API Keys Required

- **OpenAI API Key**: Get from [OpenAI Platform](https://platform.openai.com/api-keys)
- **Firecrawl API Key** (optional): Get from [Firecrawl](https://firecrawl.dev/)
- **Azure OpenAI** (alternative): Configure if using Azure instead of OpenAI

## Docker Compose Files

The project has two Docker Compose files for different use cases:

| File | Purpose | Paths |
|------|---------|-------|
| `docker-compose.dev.yml` | Local development | Uses `../` paths (source from repo root) |
| `docker-compose.yml` | Wheel/production deployment | Uses `./` paths (source copied into deploy folder) |

**For local development**, all scripts and the Makefile use `docker-compose.dev.yml` which:
- References source code from the repository root (`../gateway`, `../crawler`, etc.)
- Mounts source directories for hot reload
- Suitable when running from a git clone

**For wheel installations** (`pip install llmcrawl`), the `docker-compose.yml` file:
- Uses relative paths (`./gateway`, `./crawler`, etc.)
- Works when `llmcrawl deploy` copies source to `llmcrawl-deploy/`
- Suitable for production deployments

## Development Workflow

### 1. Start Development Environment

**Windows (PowerShell):**
```powershell
# Start all services (Docker containers + local Python services)
.\scripts\start-services.ps1
```

**Linux/Mac:**
```bash
# Start Docker containers only
make dev-up

# Start local services manually
python -m uvicorn gateway.main:app --host 0.0.0.0 --port 8000 &
python -m uvicorn services.memory_service.main:app --host 0.0.0.0 --port 8007 &
```

This starts:
- **Docker containers**: Crawler, Indexer, MCP servers, Milvus, Qdrant, Redis, PostgreSQL
- **Local Python services**: Gateway (8000), Memory Service (8007)
- Debug logging and health checks

### 2. Verify Services

```bash
make health
```

Check that all services are responding:
- Gateway (local): http://localhost:8000
- Memory Service (local): http://localhost:8007
- Crawler (Docker): http://localhost:8001
- Indexer (Docker): http://localhost:8002
- Milvus (Docker): http://localhost:19530
- Qdrant Dashboard: http://localhost:6333/dashboard

### 3. Development Commands

```bash
# Start development environment
make dev-up

# View logs
make dev-logs

# Stop development environment
make dev-down

# Rebuild and restart
make dev-rebuild

# Run tests locally
make test-dev

# Run code quality checks
make pre-commit

# Format code
black .
isort .

# Type checking
mypy .
```

### 4. Testing

**Run all tests:**
```bash
make test-dev
```

**Run specific service tests:**
```bash
pytest gateway/tests/ -v
pytest crawler/tests/ -v
pytest indexer/tests/ -v
```

**Run integration tests:**
```bash
make test-integration
```

**Test with coverage:**
```bash
pytest --cov=. --cov-report=html
```

### 5. Code Quality

The project uses pre-commit hooks for code quality:

```bash
# Run all checks
make pre-commit

# Individual tools
black --check .          # Code formatting
isort --check-only .      # Import sorting
flake8 .                  # Linting
mypy .                    # Type checking
```

## Architecture Overview

### Hybrid Architecture

LLMCrawl uses a **hybrid architecture** with local Python services and Docker containers:

**Local Python Services** (for direct filesystem access):
- Gateway (8000) - Main API orchestrator
- Memory Service (8007) - Long-term memory with memsearch

**Docker Containers** (for isolated services):
- Crawler (8001), Indexer (8002), MCP servers
- Milvus (19530), Qdrant (6333), PostgreSQL, Redis

### Services

1. **Gateway Service** (Port 8000) - **LOCAL**
   - FastAPI app handling chat requests
   - OpenAI/Azure/Anthropic/Claude Bridge integration
   - Tool calling orchestration
   - Memory integration for auto-logging and distillation

2. **Memory Service** (Port 8007) - **LOCAL**
   - OpenClaw-style auto-memory with memsearch
   - Semantic search across conversation history
   - Requires Milvus container for vector storage

3. **Crawler Service** (Port 8001) - **DOCKER**
   - Web crawling with Firecrawl + Playwright
   - Content extraction with Trafilatura
   - Respects robots.txt

4. **Indexer Service** (Port 8002) - **DOCKER**
   - Document indexing with LlamaIndex
   - Vector storage (Qdrant/pgvector)
   - Semantic search and retrieval

5. **Supporting Services** - **DOCKER**
   - **Milvus** (Port 19530) - Vector database for memory service
   - **Qdrant** (Port 6333) - Vector database for RAG
   - **PostgreSQL** (Port 5432) - Alternative vector storage
   - **Redis** (Port 6379) - Caching
   - **Firecrawl** (Port 3002) - Web crawling API

### Development Features

- **Hot Reload**: Code changes automatically restart services
- **Debug Logging**: Detailed logs for development
- **Volume Mounts**: Live code editing without rebuilds
- **Isolated Environment**: All services in Docker containers
- **Health Checks**: Service availability monitoring

## Troubleshooting

### Common Issues

1. **Port conflicts**: Ensure ports 8000-8002, 6333, 5432, 6379 are free
2. **Docker issues**: Try `docker system prune -f` to clean up
3. **Permission issues**: Run setup script as administrator on Windows
4. **Network issues**: Check Docker network with `docker network ls`

### Reset Environment

**Windows (PowerShell):**
```powershell
# Stop all services (local + Docker)
.\scripts\stop-services.ps1

# Clean up Docker volumes and networks
make clean

# Restart fresh
.\scripts\start-services.ps1
```

**Linux/Mac:**
```bash
# Stop and remove all containers
make dev-down

# Clean up volumes and networks
make clean

# Restart fresh
make dev-up
```

### View Logs

```bash
# Docker service logs
make dev-logs

# Specific Docker service
docker-compose logs -f crawler
docker-compose logs -f indexer

# Local service logs (Windows)
cat deploy/logs/gateway.log
cat deploy/logs/memory.log
```

### Service Management Scripts (Windows)

```powershell
# Start all services
.\scripts\start-services.ps1

# Stop all services
.\scripts\stop-services.ps1

# Stop specific service
.\scripts\stop-services.ps1 -Service gateway
.\scripts\stop-services.ps1 -Service memory

# Restart all services
.\scripts\restart-services.ps1

# Restart specific service
.\scripts\restart-services.ps1 -Service gateway
```

## API Testing

### Example Requests

**Basic chat:**
```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, what can you help me with?"}'
```

**Web search query:**
```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the latest NVIDIA earnings?"}'
```

**Streaming response:**
```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Latest Tesla news?", "stream": true}'
```

## IDE Setup

### VS Code

Recommended extensions:
- Python
- Black Formatter
- isort
- Pylance
- Docker
- YAML

Settings for `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.formatting.provider": "black",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    }
}
```

### PyCharm

1. Open project in PyCharm
2. Configure Python interpreter to use `venv/bin/python`
3. Enable Black formatting in Tools > External Tools
4. Configure run configurations for each service

## Contributing

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes and test: `make test-dev`
3. Run quality checks: `make pre-commit`
4. Commit changes: `git commit -m "Add feature"`
5. Push branch: `git push origin feature/my-feature`
6. Create pull request

## Support

If you encounter issues:

1. Check this guide for common solutions
2. Review service logs: `make dev-logs`
3. Verify configuration in `.env` file
4. Test individual services with health checks
5. Reset environment if needed: `make clean && make dev-up`

---

## Docker Deployment (Developer Reference)

This section covers service-by-service deployment for developers. For user installation, see [INSTALL.md](INSTALL.md).

### Service-by-Service Deployment

#### 1. Vector Database Setup

**Option A: Qdrant (Recommended)**
```bash
# Qdrant will start automatically with docker-compose
# Accessible at http://localhost:6333
# Web UI at http://localhost:6333/dashboard
```

**Option B: PostgreSQL with pgvector**
```bash
# Set in .env
VECTOR_DB=pgvector
PG_DSN=postgresql://postgres:password@postgres:5432/rag_db
```

#### 2. Supporting Services

```bash
# Redis (for caching and Firecrawl)
docker-compose up -d redis

# Firecrawl (web crawling service)
docker-compose up -d firecrawl

# Check Firecrawl health
curl http://localhost:3002/health
```

#### 3. Core Application Services

```bash
# Start in dependency order
docker-compose up -d qdrant postgres redis
docker-compose up -d firecrawl
docker-compose up -d indexer
docker-compose up -d crawler
docker-compose up -d azure-devops-mcp-server
docker-compose up -d gateway

# Verify all services
docker-compose ps
```

---

## End-to-End Testing

### Automated Test Suite

```bash
# Run all unit tests
make test

# Run integration tests (requires services to be running)
make test-integration

# Or run tests manually
docker-compose exec gateway python -m pytest tests/ -v
docker-compose exec crawler python -m pytest tests/ -v
docker-compose exec indexer python -m pytest tests/ -v
```

### Manual End-to-End Test

```bash
# 1. Start all services
docker-compose up -d

# 2. Wait for services to be ready (30-60 seconds)
sleep 60

# 3. Run the comprehensive integration test
python tests/integration/test_end_to_end.py
```

### Step-by-Step Verification

#### Test 1: Service Health Checks
```bash
# All should return {"status": "healthy"}
curl http://localhost:8000/health  # Gateway
curl http://localhost:8001/health  # Crawler
curl http://localhost:8002/health  # Indexer
curl http://localhost:8003/health  # MCP Server
curl http://localhost:6333/health  # Qdrant
```

#### Test 2: Manual Crawling
```bash
curl -X POST http://localhost:8001/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Tesla earnings Q3 2024",
    "seed_urls": ["https://ir.tesla.com"],
    "freshness_days": 30,
    "max_results": 3
  }' | jq .
```

#### Test 3: Manual Indexing
```bash
curl -X POST http://localhost:8002/index \
  -H "Content-Type: application/json" \
  -d '{
    "docs": [{
      "url": "https://example.com/test",
      "title": "Test Document",
      "markdown": "This is test content about AI.",
      "published_at": "2024-01-15T10:00:00Z"
    }]
  }' | jq .
```

#### Test 4: Manual Retrieval
```bash
curl -X POST http://localhost:8002/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "artificial intelligence",
    "k": 5
  }' | jq .
```

#### Test 5: End-to-End Chat
```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are the latest NVIDIA earnings?",
    "stream": false
  }' | jq .
```

### Performance Testing

```bash
# Test concurrent requests
for i in {1..5}; do
  curl -X POST http://localhost:8000/agent/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "What is machine learning?"}' &
done
wait

# Monitor response times
time curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Latest AI news?"}'
```

---

## Developer API Examples

These curl examples are for testing and development. See the HiChat client for user-friendly access.

### Direct Crawl API
```bash
curl -X POST http://localhost:8001/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Tesla earnings Q3 2024",
    "seed_urls": ["https://ir.tesla.com"],
    "freshness_days": 7,
    "depth": 2
  }'
```

### Direct Index API
```bash
curl -X POST http://localhost:8002/index \
  -H "Content-Type: application/json" \
  -d '{
    "docs": [{
      "url": "https://example.com/article",
      "title": "Example Article",
      "markdown": "# Article Content...",
      "published_at": "2024-01-15"
    }]
  }'
```

### Chat with Skip Embedding
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Summarize this page",
    "seed_urls": ["https://example.com/article"],
    "skip_embedding": true
  }'
```

### Export to Markdown
```bash
curl -X POST http://localhost:8000/api/v1/export/markdown \
  -H "Content-Type: application/json" \
  -d '{
    "seed_urls": ["https://example.com/article"],
    "depth": 2,
    "freshness_days": 30
  }'
```

### MCP Server Direct API
```bash
# List available tools
curl http://localhost:8003/tools

# List files
curl -X POST http://localhost:8003/invoke \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "list_files", "arguments": {"folder_path": "."}}'
```

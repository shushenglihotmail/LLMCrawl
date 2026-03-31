# Technology Stack

**Analysis Date:** 2026-03-31

## Languages

**Primary:**
- Python 3.10+ - All services (gateway, crawler, indexer, memory, MCP servers, CLI, bridges)

**Secondary:**
- JavaScript/HTML/CSS - HiChat web client (`clients/hichat/static/app.js`, `clients/hichat/static/index.html`, `clients/hichat/static/styles.css`)
- SQL - Database initialization (`deploy/nuq.sql`)

## Runtime

**Environment:**
- Python 3.10, 3.11, 3.12 (all supported; Docker images use 3.11-slim; CI builds on 3.12)
- Node.js - Used by Firecrawl and Playwright containers (not directly by project code)

**Package Manager:**
- pip with setuptools (build backend)
- Lockfile: Not present (uses version ranges in `pyproject.toml` and `requirements/*.txt`)

## Frameworks

**Core:**
- FastAPI >=0.104.0 - All HTTP services (gateway, crawler, indexer, memory, MCP servers, bridges)
- Pydantic >=2.0.0 - Data validation and serialization across all services
- Uvicorn >=0.24.0 - ASGI server for all FastAPI services

**Testing:**
- pytest >=7.0.0 - Test runner
- pytest-asyncio >=0.21.0 - Async test support
- pytest-cov >=4.0.0 - Coverage reporting

**Build/Dev:**
- setuptools >=61.0 - Build backend (`pyproject.toml`)
- wheel - Wheel packaging
- pre-commit >=3.0.0 - Git hooks for code quality

## Key Dependencies

**Critical (Gateway - `requirements/gateway.txt`):**
- `openai` >=1.0.0 - OpenAI/Azure OpenAI SDK (AsyncOpenAI, AsyncAzureOpenAI)
- `httpx` >=0.25.0 - Async HTTP client for Anthropic, bridge, and inter-service calls
- `tiktoken` >=0.5.0 - Token counting and prompt compression
- `prometheus-fastapi-instrumentator` >=6.1.0 - Metrics collection
- `python-multipart` >=0.0.6 - File upload support
- `asyncio-throttle` >=1.0.2 - Rate limiting
- `PyJWT` >=2.8.0 - Entra ID JWT token validation
- `cryptography` >=41.0.0 - RS256 signature verification for JWT

**Critical (Crawler - `requirements/crawler.txt`):**
- `playwright` >=1.40.0 - Browser automation for JS-heavy pages
- `trafilatura` >=1.6.0 - Content extraction from HTML
- `beautifulsoup4` >=4.12.0 - HTML parsing
- `lxml` >=4.9.0 - Fast XML/HTML processing
- `msal` >=1.26.0 - Microsoft Authentication Library (optional Azure AD auth)

**Critical (Indexer - `requirements/indexer.txt`):**
- `llama-index` >=0.9.0 - RAG indexing framework
- `llama-index-embeddings-openai` >=0.1.0 - OpenAI embeddings
- `llama-index-embeddings-azure-openai` >=0.1.0 - Azure OpenAI embeddings
- `qdrant-client` >=1.6.0 - Qdrant vector DB client
- `asyncpg` >=0.28.0 - PostgreSQL async driver
- `pgvector` >=0.2.0 - pgvector support
- `numpy` >=1.24.0 - Numerical operations
- `azure-identity` >=1.15.0 - Azure credential management

**Critical (Memory Service - `requirements/memory_service.txt`):**
- `memsearch[local]` >=0.1.15 - Markdown-first memory with semantic search (sentence-transformers embeddings)
- `tiktoken` >=0.5.0 - Token counting

**Critical (Azure DevOps MCP - `mcp_servers/azure_devops_mcp_server/pyproject.toml`):**
- `azure-devops` >=7.1.0b3 - Azure DevOps SDK
- `msal` >=1.24.0 - Microsoft Authentication Library
- `aiofiles` >=23.0.0 - Async file I/O

**Infrastructure:**
- `python-dotenv` >=1.0.0 - Environment configuration loading

**Optional (Gateway - commented out in `requirements/gateway.txt`):**
- `llmlingua` >=0.2.0 - BERT-based intelligent prompt compression (~2GB total with torch)
- `torch` >=2.0.0 - Required by LLMLingua
- `transformers` >=4.30.0 - Required by LLMLingua
- `accelerate` >=0.20.0 - Required by LLMLingua

## Configuration

**Environment:**
- Environment variables loaded from `deploy/.env`
- `LLM_PROVIDER`: azure | openai - Primary LLM provider selection
- `LLM_MODELS`: JSON array configuring model routing (name, deployment_name, provider_type, max_output_tokens)
- `VECTOR_DB`: qdrant | pgvector - Vector store selection
- Configuration parsed at runtime in `gateway/llm/client.py`

**Build:**
- `pyproject.toml` - Main project config (build, dependencies, tool settings)
- `mcp_servers/azure_devops_mcp_server/pyproject.toml` - MCP server separate package
- `.pre-commit-config.yaml` - Pre-commit hooks (black 23.1.0, isort 5.12.0, flake8 6.0.0, mypy v1.0.1)

## Code Quality Tools

**Formatter:** black (line-length 88, target py310) - configured in `pyproject.toml`
**Import Sorter:** isort (black profile) - configured in `pyproject.toml`
**Linter:** flake8 (max-line-length 88, extend-ignore E203,E221,E231,E713)
**Type Checker:** mypy (strict mode, python 3.10, ignore_missing_imports=true) - configured in `pyproject.toml`

## Infrastructure

**Container Orchestration:**
- Docker Compose - Two compose files:
  - `deploy/docker-compose.dev.yml` - Local development (source mounts from parent directories)
  - `deploy/docker-compose.yml` - Wheel-based deployment (source from `./` paths)
- Docker network: `webrag-network` (external bridge, must be created manually)

**Container Images (custom Dockerfiles):**
- `deploy/Dockerfile.gateway` - Gateway service (python:3.11-slim)
- `deploy/Dockerfile.crawler` - Crawler service (python:3.11-slim + Playwright/Chromium)
- `deploy/Dockerfile.indexer` - Indexer service (python:3.11-slim)
- `deploy/Dockerfile.mcp_server` - Azure DevOps MCP server
- `deploy/Dockerfile.demo` - Demo web client
- `services/memory_service/Dockerfile` - Memory service (python:3.11-slim, built and pushed to GHCR via CI)

**Databases:**
- PostgreSQL 16 with pgvector (`pgvector/pgvector:pg16`) - Port 5432
- Qdrant v1.7.0 (`qdrant/qdrant:v1.7.0`) - Ports 6333 (HTTP), 6334 (gRPC)
- Redis 7 Alpine (`redis:7-alpine`) - Port 6379 (caching for Firecrawl)
- Milvus v2.5.5 (`milvusdb/milvus:v2.5.5`) - Port 19530 (vector DB for memory service)

**External Services (Containers):**
- Firecrawl (`ghcr.io/firecrawl/firecrawl:latest`) - Web scraping, port 3002
- Playwright Service (`ghcr.io/firecrawl/playwright-service:latest`) - Browser automation, port 3003

**Monitoring (optional, Docker compose profile "monitoring"):**
- Prometheus (`prom/prometheus:latest`) - Metrics, port 9090, config at `deploy/prometheus.yml`
- Grafana (`grafana/grafana:latest`) - Dashboards, port 3001, provisioning at `deploy/grafana-provisioning/`

## CI/CD

**Pipeline:** GitHub Actions (`.github/workflows/build-wheel.yml`)
- Trigger: GitHub Release creation or manual workflow_dispatch
- **build-wheels** job: Python 3.12 on ubuntu-latest, builds main wheel + MCP server wheels, uploads to GitHub Releases
- **build-memory-service** job: Builds memory service Docker image, pushes to GHCR

## CLI Entry Points

Defined in `pyproject.toml` `[project.scripts]`:
- `hichat` -> `clients.hichat.main:main` - Web client launcher (port 8080)
- `llmcrawl` -> `llmcrawl_cli.main:main` - Main CLI (deploy, bridge management, auth, status)

## Platform Requirements

**Development:**
- Python 3.10+ with pip
- Docker Desktop (for containerized services)
- Windows recommended (PowerShell scripts: `scripts/start-services.ps1`, `scripts/stop-services.ps1`)
- Cross-platform setup: `python scripts/setup_dev.py`

**Production:**
- Docker with compose support
- External `webrag-network` Docker bridge network
- Gateway and Memory Service run on host (not containerized) for filesystem and CLI access

## Known Dependency Conflicts

- `setuptools` version conflict: memsearch requires `<75`, llama-index (indexer) requires `>=80.9`. Run indexer in Docker or separate venv. Documented in `pyproject.toml` line 51.

---

*Stack analysis: 2026-03-31*

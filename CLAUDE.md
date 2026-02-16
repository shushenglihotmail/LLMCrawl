# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LLMCrawl is a containerized Python Web RAG system that enables LLMs to trigger web crawling, index results, and answer questions with citations. It features conversation memory, intelligent tool calling, and multi-source web scraping.

## Architecture

Five containerized services plus two host-side bridges:

- **Gateway (8000)**: FastAPI orchestrator with multi-provider LLM support (OpenAI, Azure OpenAI, Anthropic, Claude Bridge)
- **Crawler (8001)**: FireCrawl + Playwright fallback + Trafilatura content extraction
- **Indexer (8002)**: LlamaIndex + Vector DB (Qdrant/pgvector) for RAG
- **Local Access MCP (8003)**: File operations with semantic search
- **Azure DevOps MCP (8004)**: Code search with MSAL/PAT authentication
- **WCD Bridge (8005)**: Windows Composition Database query bridge (host-side)
- **Claude Bridge (8006)**: Claude Code CLI HTTP bridge (host-side)

Data stores: PostgreSQL (5432), Qdrant (6333), Redis (6379)

## Common Commands

### Development Environment
```bash
# Windows setup
.\scripts\setup_dev.ps1

# Cross-platform setup
python scripts/setup_dev.py

# Install dev dependencies
make install-dev
```

### Docker Services
```bash
make dev-up          # Start all services
make dev-down        # Stop all services
make dev-logs        # View logs
make rebuild         # Rebuild with latest code
make clean           # Full cleanup including volumes
```

### Testing
```bash
make test-dev                  # Local pytest with coverage
make test                      # Run tests in containers
make test-integration          # End-to-end tests
pytest tests/ -v -k "test_name"  # Run single test
```

### Code Quality
```bash
make pre-commit      # Run all pre-commit hooks (black, isort, flake8, mypy)
make lint            # Check code style
make format          # Auto-format with black/isort
```

### Health & Monitoring
```bash
make health          # Check all service health
llmcrawl deploy --status  # CLI status check
make monitoring-up   # Start Prometheus/Grafana
```

### CLI Tools
```bash
llmcrawl deploy --init    # Initialize deployment folder
llmcrawl deploy --up      # Start services
llmcrawl claude-bridge    # Start Claude Bridge (port 8006)
llmcrawl wcd-bridge       # Start WCD Bridge (port 8005)
hichat                    # Start web client (port 8080)
```

## Key Directory Structure

- `gateway/` - Main API gateway with agents, LLM clients, and routers
- `crawler/` - Web crawling with FireCrawl/Playwright clients and content extraction
- `indexer/` - Vector DB adapters (Qdrant, pgvector) and document processing
- `mcp_servers/` - MCP servers (local_access, azure_devops, wcd_bridge)
- `clients/hichat/` - Flask web client with static frontend
- `llmcrawl_cli/` - CLI for deployment, auth, and bridge services
- `tools/` - Host-side utilities (claude_bridge, wcd_bridge, msauth)
- `deploy/` - Docker Compose files, Dockerfiles, and requirements per service

## Configuration

Environment variables in `deploy/.env` (copy from `.env.example`):

- `LLM_PROVIDER`: azure, openai, or anthropic
- `AZURE_OPENAI_ENDPOINT`: Azure OpenAI resource URL
- `CHAT_MODEL` / `EMBED_MODEL`: Model names
- `ENTRA_CLIENT_ID` / `ENTRA_TENANT_ID`: Azure authentication
- `VECTOR_DB`: qdrant or pgvector
- `ALLOWED_DOMAINS`: Crawl whitelist
- `CLAUDE_BRIDGE_URL`: http://host.docker.internal:8006 (optional)

## Code Style

- Python 3.10+
- Formatting: black (line-length 88), isort (black profile)
- Linting: flake8, mypy (strict typing)
- Pre-commit hooks enforce style on commit

## Test Paths

Tests are located in:
- `tests/` - Integration tests
- `gateway/tests/`
- `crawler/tests/`
- `indexer/tests/`

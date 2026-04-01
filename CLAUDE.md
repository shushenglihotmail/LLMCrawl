# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LLMCrawl is a containerized Python Web RAG system that enables LLMs to trigger web crawling, index results, and answer questions with citations. Features conversation memory, intelligent tool calling, and multi-source web scraping.

## Architecture

### Local Services (run on host, not in Docker)
- **Gateway (8000)**: FastAPI orchestrator - routes to OpenAI/Azure/Anthropic/Claude Bridge based on `LLM_MODELS` config. Runs locally for filesystem access.
- **Memory Service (8007)**: OpenClaw-style auto-memory with hybrid search (memsearch + Milvus)

### Containerized Services (Docker)
- **Crawler (8001)**: FireCrawl + Playwright fallback + Trafilatura extraction
- **Indexer (8002)**: LlamaIndex + Vector DB (Qdrant/pgvector)
- **Azure DevOps MCP (8004)**: Code search with MSAL/PAT auth

### Host-side Bridges (optional, not containerized)
- **WCD Bridge (8005)**: Windows Composition Database queries (gateway starts on demand; MCP server standalone for IDE use)
- **Claude Bridge (8006)**: Claude Code CLI HTTP wrapper (optional — gateway calls CLI directly)
- **Copilot Bridge (8009)**: GitHub Copilot CLI HTTP wrapper (optional — gateway calls CLI directly)

### Data Stores
PostgreSQL (5432), Qdrant (6333), Redis (6379), Milvus (19530)

### Docker Network
All services communicate via `webrag-network` (external bridge). Create with: `docker network create webrag-network`

## Key Architectural Patterns

### LLM Client Routing (`gateway/llm/client.py`)
The `LLMClient` routes requests based on `provider_type` from `LLM_MODELS` JSON config:
- `openai` → AsyncAzureOpenAI/AsyncOpenAI
- `anthropic` → Direct HTTP to Azure Anthropic endpoint
- `claude` → Direct CLI subprocess (`claude.exe`) or HTTP bridge fallback
- `copilot` → Direct CLI subprocess (`copilot.exe`) or HTTP bridge fallback

CLI providers (`gateway/llm/cli_providers.py`) spawn CLIs directly as subprocesses — no manual bridge startup needed. HTTP bridges (`tools/claude_bridge.py`, `tools/copilot_bridge.py`) remain as optional fallbacks.

Model resolution: `get_model_config(model_name)` → `(deployment_name, provider_type, max_output_tokens)`

### Unified Workflow System (`gateway/agents/unified_workflow.py`)
Four workflow types with different system prompts and tool availability:
- `GENERAL_CHAT`: Casual conversation, no file tools
- `CODE_ANALYSIS`: Technical architect role, all tools
- `BUILD_SYSTEM_ANALYSIS`: Build engineer role, all tools
- `FILE_EXPLORER`: DevOps role, path tree display

### Path Expansion Conventions (`gateway/routers/agent.py`)
Azure DevOps paths use `azdo:` URI scheme:
- `azdo:/path:searchText` - Code search API (colon separates path and search)
- `azdo:/path/to/file.cpp` - Direct file fetch (no colon = exact file)

Local paths: `*.cpp` (wildcard), `folder/` (non-recursive), `folder/**` (recursive)

### Tool Calling Pattern
Tools defined in `gateway/utils/tool_constants.py`. Gateway fetches MCP tool schemas at startup via `/tools` endpoint, converts to OpenAI format with `convert_mcp_tool_to_openai()`.

### Memory Service Architecture
Standalone containerized service using [memsearch](https://github.com/zilliztech/memsearch) library.
Gateway is a pure HTTP client - all memory operations via REST API.

**All operations via HTTP:**
| Operation | HTTP Endpoint | Description |
|-----------|---------------|-------------|
| Write daily log | `POST /write_daily` | Log conversation messages |
| Write facts | `POST /write_memory` | Save durable facts to MEMORY.md |
| Search | `POST /search` | Semantic search memories |
| Get context | `GET /context` | Load memory for conversation start |
| Reindex | `POST /reindex` | Rebuild vector index |

**Architecture:**
```
Gateway ──HTTP──> Memory Service ──> Storage (MEMORY_DATA_PATH)
                       │
                       └──> Milvus (vector DB)
```

**Storage layout (managed by memory service):**
```
{MEMORY_DATA_PATH}/
├── daily/YYYY-MM-DD.md   # Daily conversation logs
└── MEMORY.md             # Durable long-term facts
```

**Key features:** Markdown as source of truth, semantic search, all apps share same format

## Docker Compose Files

| File | Use Case | Source Paths |
|------|----------|--------------|
| `docker-compose.dev.yml` | Local dev (git clone) | `../gateway`, `../crawler`, etc. |
| `docker-compose.yml` | Wheel deployment | `./gateway`, `./crawler`, etc. |

Always use `make dev-*` commands for development - they use the dev compose file.

## Common Commands

```bash
# Setup
.\scripts\setup_dev.ps1           # Windows
python scripts/setup_dev.py       # Cross-platform

# Starting services (Windows - preferred, starts Docker + local services)
.\scripts\start-services.ps1      # Start all (Docker containers + Gateway + Memory)
.\scripts\stop-services.ps1       # Stop all

# Docker only (Linux/Mac, or containers-only on Windows)
make dev-up / dev-down / dev-logs # Start/stop/logs
make rebuild                      # Rebuild containers
make clean                        # Full cleanup with volumes

# Testing
make test-dev                     # Local pytest with coverage
pytest tests/ -v -k "test_name"   # Single test
make test-integration             # End-to-end tests

# Test paths: tests/, gateway/tests/, crawler/tests/, indexer/tests/

# Code quality
make pre-commit                   # black, isort, flake8, mypy

# CLI tools
llmcrawl deploy --up              # Start services
llmcrawl deploy --status          # Health check all services
llmcrawl claude-bridge            # Start Claude Bridge (optional, port 8006)
llmcrawl copilot-bridge           # Start Copilot Bridge (optional, port 8009)
hichat                            # Start web client (http://localhost:8080)
```

## Code Style

- Python 3.10+, black (88 chars), isort (black profile), flake8, mypy (strict)
- Pre-commit hooks enforce on commit (trailing-whitespace, end-of-file-fixer, check-yaml, check-merge-conflict + linters)
- Config in `pyproject.toml`

## CI/CD

GitHub Actions (`build-wheel.yml`):
- **build-wheels**: Builds main wheel + all MCP server wheels, uploads to GitHub Releases on release events
- **build-memory-service**: Builds Docker image from `services/memory_service/`, pushes to GHCR

## Important Gotchas

- **setuptools conflict**: memsearch requires `setuptools<75`, but llama-index (indexer) requires `setuptools>=80.9`. Run indexer in Docker or a separate venv — don't install both locally.
- **Entra ID auth**: Azure OpenAI and Anthropic endpoints support Entra ID token auth (via `ENTRA_CLIENT_ID` / `ENTRA_TENANT_ID`), not just API keys.

## Key Files by Component

**Gateway**: `main.py` (FastAPI app), `routers/agent.py` (chat endpoint + file viewer), `llm/client.py` (LLM routing), `llm/cli_providers.py` (Claude/Copilot CLI subprocess providers), `llm/prompts.py` (system prompts), `utils/conversation_store.py` (in-memory 24h TTL)

**Crawler**: `clients/firecrawl_client.py`, `clients/playwright_client.py`, `extractors/trafilatura_extractor.py`

**Indexer**: `adapters/qdrant_adapter.py`, `adapters/pgvector_adapter.py`

**Memory Service**: `services/memory_service/main.py` (FastAPI wrapper around memsearch library)

## Configuration

Environment in `deploy/.env`:
- `LLM_PROVIDER`: azure | openai | anthropic
- `LLM_MODELS`: JSON array with `name`, `deployment_name`, `provider_type`, `max_output_tokens`
- `VECTOR_DB`: qdrant | pgvector
- `CLAUDE_BRIDGE_URL`: http://localhost:8006 (optional — only needed if using HTTP bridge instead of direct CLI)
- `COPILOT_BRIDGE_URL`: http://localhost:8009 (optional — only needed if using HTTP bridge instead of direct CLI)
- `MEMORY_SERVICE_URL`: http://localhost:8007 (required for memory features)
- `MEMORY_AUTO_LOG`: true | false (auto-append to daily logs via HTTP)
- `MEMORY_AUTO_FLUSH`: true | false (80% context flush trigger)
- `MEMORY_FLUSH_THRESHOLD`: 0.8 (context % to trigger flush)

**Memory Service config** (in memory-service/.env):
- `MEMORY_DATA_PATH`: /path/to/logs (where markdown files are stored)
- `PORT`: 8007 (HTTP listening port)
- `MILVUS_URI`: milvus:19530 (vector database)

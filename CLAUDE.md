# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LLMCrawl is a containerized Python Web RAG system that enables LLMs to trigger web crawling, index results, and answer questions with citations. Features conversation memory, intelligent tool calling, and multi-source web scraping.

## Architecture

### Services (Docker)
- **Gateway (8000)**: FastAPI orchestrator - routes to OpenAI/Azure/Anthropic/Claude Bridge based on `LLM_MODELS` config
- **Crawler (8001)**: FireCrawl + Playwright fallback + Trafilatura extraction
- **Indexer (8002)**: LlamaIndex + Vector DB (Qdrant/pgvector)
- **Local Access MCP (8003)**: File operations with semantic search
- **Azure DevOps MCP (8004)**: Code search with MSAL/PAT auth
- **Memory Service (8007)**: OpenClaw-style auto-memory with hybrid search

### Host-side Bridges (not containerized)
- **WCD Bridge (8005)**: Windows Composition Database queries
- **Claude Bridge (8006)**: Claude Code CLI HTTP wrapper

### Data Stores
PostgreSQL (5432), Qdrant (6333), Redis (6379)

## Key Architectural Patterns

### LLM Client Routing (`gateway/llm/client.py`)
The `LLMClient` routes requests based on `provider_type` from `LLM_MODELS` JSON config:
- `openai` → AsyncAzureOpenAI/AsyncOpenAI
- `anthropic` → Direct HTTP to Azure Anthropic endpoint
- `claude` → HTTP to Claude Bridge (host-side CLI wrapper)

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
OpenClaw-style auto-memory using [memsearch](https://github.com/zilliztech/memsearch) library:

**Division of labor:**
| Task | Who | How |
|------|-----|-----|
| Search | LLM (via `memory_search` tool) | Calls memory service when needed |
| Daily logging | Gateway (automatic) | Auto-append messages to `memory/YYYY-MM-DD.md` |
| 80% flush | Gateway triggers → LLM writes | Hidden prompt → LLM summarizes to `MEMORY.md` |
| Indexing | Memory Service (memsearch) | Milvus 2.5+ container + sentence-transformers |

**Storage layout:**
```
deploy/memory/
├── daily/            # Daily logs (YYYY-MM-DD.md)
├── MEMORY.md         # Distilled long-term facts (LLM writes)
```
Note: Vector index stored in Milvus container volume (milvus-lite doesn't support Windows)

**Key features:** Markdown as source of truth, semantic search, SHA-256 deduplication

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

# Docker
make dev-up / dev-down / dev-logs # Start/stop/logs
make rebuild                      # Rebuild containers
make clean                        # Full cleanup with volumes

# Testing
make test-dev                     # Local pytest with coverage
pytest tests/ -v -k "test_name"   # Single test
make test-integration             # End-to-end tests

# Code quality
make pre-commit                   # black, isort, flake8, mypy

# CLI tools
llmcrawl deploy --up              # Start services
llmcrawl claude-bridge            # Start Claude Bridge
hichat                            # Start web client
```

## Code Style

- Python 3.10+, black (88 chars), isort (black profile), flake8, mypy (strict)
- Pre-commit hooks enforce on commit
- Config in `pyproject.toml`

## Key Files by Component

**Gateway**: `main.py` (FastAPI app), `routers/agent.py` (chat endpoint), `llm/client.py` (LLM routing), `llm/prompts.py` (system prompts), `utils/conversation_store.py` (in-memory 24h TTL)

**Crawler**: `clients/firecrawl_client.py`, `clients/playwright_client.py`, `extractors/trafilatura_extractor.py`

**Indexer**: `adapters/qdrant_adapter.py`, `adapters/pgvector_adapter.py`

**Memory Service**: `services/memory_service/main.py` (FastAPI wrapper around memsearch library)

## Configuration

Environment in `deploy/.env`:
- `LLM_PROVIDER`: azure | openai | anthropic
- `LLM_MODELS`: JSON array with `name`, `deployment_name`, `provider_type`, `max_output_tokens`
- `VECTOR_DB`: qdrant | pgvector
- `CLAUDE_BRIDGE_URL`: http://host.docker.internal:8006 (optional)
- `MEMORY_SERVICE_URL`: http://memory-service:8007 (auto-memory)
- `MEMORY_AUTO_LOG`: true | false (auto-append to daily logs)
- `MEMORY_AUTO_FLUSH`: true | false (80% context flush trigger)
- `MEMORY_FLUSH_THRESHOLD`: 0.8 (context % to trigger flush)

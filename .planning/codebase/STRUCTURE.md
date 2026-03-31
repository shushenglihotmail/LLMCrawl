# Codebase Structure

**Analysis Date:** 2026-03-31

## Directory Layout

```
LLMCrawl/
├── gateway/                # FastAPI gateway - main orchestrator (runs on host)
│   ├── main.py             # FastAPI app, lifespan, middleware
│   ├── agents/             # Workflow definitions, agent config
│   ├── llm/                # LLM client, CLI providers, prompts
│   ├── routers/            # API endpoints (agent, models, export, tools)
│   ├── utils/              # Shared utilities (auth, logging, metrics, memory)
│   └── tests/              # Gateway unit tests
├── crawler/                # Web crawler service (Docker)
│   ├── main.py             # FastAPI app for crawl endpoints
│   ├── clients/            # FireCrawl client
│   ├── extract/            # Trafilatura text extraction
│   ├── render/             # Playwright rendering
│   ├── utils/              # Crawler utilities (metrics, robots.txt)
│   └── tests/              # Crawler tests
├── indexer/                # Vector indexing service (Docker)
│   ├── main.py             # FastAPI app for index/retrieve endpoints
│   ├── adapters/           # LlamaIndex store adapter
│   ├── vector/             # Vector DB implementations (Qdrant, pgvector)
│   ├── utils/              # Indexer utilities (metrics, token context)
│   └── tests/              # Indexer tests
├── clients/                # Client applications
│   ├── hichat/             # Web chat UI (FastAPI + static HTML/JS/CSS)
│   │   ├── main.py         # HiChat FastAPI app, gateway proxy
│   │   ├── msal_auth.py    # MSAL authentication client
│   │   └── static/         # Frontend assets (index.html, app.js, styles.css)
│   └── demo/               # Demo scripts
├── services/               # Standalone services
│   └── memory_service/     # Memory service (runs on host or Docker)
│       ├── main.py         # FastAPI wrapper around memsearch
│       ├── client.py       # Memory service client library
│       ├── Dockerfile      # Container build
│       └── requirements.txt
├── mcp_servers/            # MCP (Model Context Protocol) servers
│   ├── azure_devops_mcp_server/  # Azure DevOps code search + file access (Docker)
│   │   ├── azure_devops_client/  # AzDO REST API client
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   └── crawler_mcp_server/       # Crawler MCP wrapper (separate package)
│       ├── crawler_mcp_server/   # MCP server implementation
│       └── pyproject.toml
├── tools/                  # Host-side bridge tools and CLI wrappers
│   ├── claude_bridge.py    # Claude CLI HTTP bridge (optional fallback)
│   ├── copilot_bridge.py   # Copilot CLI HTTP bridge (optional fallback)
│   ├── windows_composition_bridge.py  # WCD bridge
│   └── msauth/             # MSAL authentication utilities
├── llmcrawl_cli/           # CLI entry point (`llmcrawl` command)
│   ├── main.py             # CLI dispatcher (deploy, auth, bridges)
│   ├── deploy.py           # Docker compose management
│   ├── auth.py             # CLI auth helpers
│   ├── claude_bridge.py    # Claude bridge CLI launcher
│   ├── copilot_bridge.py   # Copilot bridge CLI launcher
│   └── wcd_bridge.py       # WCD bridge CLI launcher
├── deploy/                 # Deployment configuration
│   ├── docker-compose.yml      # Production compose (wheel paths)
│   ├── docker-compose.dev.yml  # Dev compose (local source mounts)
│   ├── .env                    # Environment config (secrets - DO NOT READ)
│   ├── prometheus.yml          # Prometheus scrape config
│   ├── grafana-provisioning/   # Grafana dashboards and datasources
│   ├── requirements/           # Per-service pip requirements
│   ├── logs/                   # Runtime logs directory
│   └── memory/                 # Memory service data (daily/, MEMORY.md)
├── tests/                  # Top-level tests
│   ├── integration/        # End-to-end integration tests
│   ├── test_expand_paths.py    # Path expansion unit tests
│   └── test_gateway.py         # Gateway unit tests
├── scripts/                # Setup and management scripts (PowerShell + Bash)
│   ├── start-services.ps1  # Start all services (Docker + host)
│   ├── stop-services.ps1   # Stop all services
│   ├── setup_dev.ps1       # Windows dev setup
│   ├── setup_dev.py        # Cross-platform dev setup
│   └── health_check.ps1    # Health check all services
├── docs/                   # Documentation
├── data/                   # Runtime data directory
│   └── files/              # Saved files from tool calls
├── memory-service/         # Memory service Docker Compose override
│   └── docker-compose.yml
├── .github/                # CI/CD
│   └── workflows/
│       └── build-wheel.yml # GitHub Actions: build wheels + Docker image
├── pyproject.toml          # Python project config (build, linting, CLI entry points)
├── Makefile                # Build/dev commands (make dev-up, test-dev, pre-commit)
├── MANIFEST.in             # Source distribution manifest
└── CLAUDE.md               # AI assistant instructions
```

## Directory Purposes

**`gateway/`:**
- Purpose: Central orchestrator for all chat requests
- Contains: FastAPI app, LLM routing, tool calling loop, memory integration
- Key files:
  - `main.py`: App creation, lifespan (CLI bridge probing), middleware (auth, CORS), router mounting
  - `routers/agent.py` (1920 lines): Main `/agent/chat` endpoint, context gathering, system prompt building, tool loop, memory integration
  - `routers/tools.py` (679 lines): `ToolHandler` class dispatching tool calls to backend services
  - `routers/models.py`: `GET /api/models/available` endpoint -- exposes model list from config + discovered CLI models
  - `routers/export.py`: `POST /api/v1/export/markdown` -- crawl URLs and export as markdown file
  - `llm/client.py` (1505 lines): `LLMClient` with 4-tier model resolution and 5 provider backends
  - `llm/cli_providers.py`: `ClaudeCLIProvider` and `CopilotCLIProvider` subprocess wrappers
  - `llm/prompts.py` (286 lines): Pydantic tool schemas (`CrawlAndRefreshInput`), `ToolSchemaConverter`
  - `agents/unified_workflow.py` (145 lines): `WorkflowType` enum, `UnifiedWorkflowRequest`/`Response` models
  - `agents/agent_config.py`: `AgentConfig` dataclass, `convert_mcp_tool_to_openai()` helper
  - `utils/memory_integration.py` (379 lines): Memory service HTTP client (auto-log, flush, context injection)
  - `utils/conversation_store.py`: In-memory conversation history with 24h TTL, 50 msg cap
  - `utils/prompt_compressor.py` (300 lines): Token estimation (tiktoken) + LLMLingua-2 compression
  - `utils/tool_constants.py`: All tool name constants and default per-tool round limits
  - `utils/claude_bridge_manager.py`: Claude CLI/Bridge startup discovery and model caching
  - `utils/copilot_bridge_manager.py`: Copilot CLI/Bridge startup discovery and model caching
  - `utils/auth.py`: Bearer token extraction, Entra ID helpers
  - `utils/metrics.py`: Prometheus custom metrics (LLM requests, tool calls, crawl, agent timing)
  - `utils/logging.py`: Structured logging setup with `log_request()`, `log_response()`, etc.
  - `utils/azdo_uri.py`: Azure DevOps URI parser (`azdo:` scheme with path + search)
  - `utils/token_context.py`: Context variable for bearer token propagation across async calls

**`crawler/`:**
- Purpose: Fetches web content via multiple strategies (Docker service)
- Contains: HTTP clients, content extraction, browser rendering
- Key files:
  - `main.py` (568 lines): FastAPI app with `/crawl`, `/render`, `/extract` endpoints
  - `clients/firecrawl.py`: FireCrawl API client for fast scraping with auth cookie support
  - `extract/trafilatura_wrap.py`: Trafilatura-based content extraction (HTML to markdown/text)
  - `render/playwright_runner.py`: Playwright browser rendering for JS-heavy pages
  - `utils/robots.py`: robots.txt checking
  - `utils/metrics.py`: Crawler Prometheus metrics

**`indexer/`:**
- Purpose: Indexes documents into vector database for RAG retrieval (Docker service)
- Contains: LlamaIndex integration, vector DB adapters
- Key files:
  - `main.py` (319 lines): FastAPI app with `/index`, `/retrieve`, `/collection/info`, `/documents` endpoints
  - `adapters/llamaindex_store.py`: LlamaIndex chunking + embedding + vector store integration
  - `vector/qdrant_store.py`: Qdrant vector DB adapter
  - `vector/pgvector_store.py`: pgvector (PostgreSQL) adapter

**`clients/hichat/`:**
- Purpose: Browser-based chat UI
- Contains: FastAPI proxy server + static frontend
- Key files:
  - `main.py`: FastAPI app serving static files, proxying to Gateway, MSAL auth
  - `msal_auth.py`: MSAL token acquisition for Entra ID auth
  - `static/index.html`: Main HTML page
  - `static/app.js`: Chat UI logic, model selection, file browser/viewer
  - `static/styles.css`: UI styling

**`services/memory_service/`:**
- Purpose: Persistent conversation memory with semantic search
- Contains: memsearch library wrapper, daily log management
- Key files:
  - `main.py` (520 lines): FastAPI app wrapping memsearch (`POST /write_daily`, `/write_memory`, `/search`, `GET /context`, `POST /reindex`)
  - `client.py`: Python client library for the memory service HTTP API

**`mcp_servers/`:**
- Purpose: Model Context Protocol servers exposing tool schemas via `GET /tools` and `POST /invoke`
- Contains: Separate Python packages, each with its own `pyproject.toml`
- Key subdirectories:
  - `azure_devops_mcp_server/`: Code search, file access, commit diff via Azure DevOps REST API (runs in Docker)
  - `crawler_mcp_server/`: MCP wrapper around crawler service

**`tools/`:**
- Purpose: Host-side HTTP bridge servers (optional fallbacks for direct CLI providers)
- Contains: FastAPI apps wrapping CLI executables
- Key files:
  - `claude_bridge.py`: HTTP wrapper around `claude.exe` CLI
  - `copilot_bridge.py`: HTTP wrapper around `copilot.exe` CLI
  - `windows_composition_bridge.py`: WCD bridge server
  - `msauth/`: MSAL authentication utilities for internal site access

**`llmcrawl_cli/`:**
- Purpose: Main CLI entry point for the `llmcrawl` command
- Contains: Subcommand modules
- Key files:
  - `main.py`: CLI dispatcher -- `deploy`, `auth`, `wcd-bridge`, `claude-bridge`, `copilot-bridge` subcommands
  - `deploy.py`: Docker compose up/down/status management

**`deploy/`:**
- Purpose: All deployment artifacts (Docker, env, monitoring)
- Contains: Compose files, Dockerfiles, requirements, Grafana provisioning
- Key files:
  - `docker-compose.dev.yml`: Dev compose with local source volume mounts
  - `docker-compose.yml`: Production compose with wheel-installed paths
  - `.env`: Environment configuration (secrets -- DO NOT READ)
  - `prometheus.yml`: Prometheus scrape targets for all services
  - `requirements/`: Per-service pip requirements files

## Key File Locations

**Entry Points:**
- `gateway/main.py`: Gateway FastAPI app (primary service, port 8000)
- `crawler/main.py`: Crawler FastAPI app (port 8001)
- `indexer/main.py`: Indexer FastAPI app (port 8002)
- `clients/hichat/main.py`: HiChat web client (port 8080)
- `services/memory_service/main.py`: Memory service (port 8007)
- `llmcrawl_cli/main.py`: CLI tool (`llmcrawl` command)

**Configuration:**
- `pyproject.toml`: Python project config (build, linting, formatting, CLI scripts)
- `Makefile`: Dev commands (`make dev-up`, `make test-dev`, `make pre-commit`)
- `deploy/.env`: Environment variables (DO NOT READ -- contains secrets)
- `deploy/docker-compose.dev.yml`: Docker service definitions for development

**Core Logic (by line count):**
- `gateway/routers/agent.py` (1920 lines): Chat endpoint + tool calling loop
- `gateway/llm/client.py` (1505 lines): LLM provider routing
- `gateway/routers/tools.py` (679 lines): Tool dispatch to backend services
- `crawler/main.py` (568 lines): Crawl pipeline
- `services/memory_service/main.py` (520 lines): Memory service
- `gateway/utils/memory_integration.py` (379 lines): Memory integration client
- `indexer/main.py` (319 lines): Index/retrieve pipeline
- `gateway/utils/prompt_compressor.py` (300 lines): Prompt compression

**Testing:**
- `tests/`: Top-level tests (integration, path expansion, gateway tests)
- `gateway/tests/`: Gateway unit tests
- `crawler/tests/`: Crawler unit tests
- `indexer/tests/`: Indexer unit tests

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (e.g., `cli_providers.py`, `conversation_store.py`)
- Static assets: `snake_case` or `camelCase` (e.g., `app.js`, `index.html`)
- Dockerfiles: `Dockerfile.{service}` in deploy dir

**Directories:**
- All lowercase with underscores: `memory_service`, `azure_devops_mcp_server`
- Service directories match their service name

**Classes:**
- PascalCase: `LLMClient`, `ToolHandler`, `ClaudeCLIProvider`, `UnifiedWorkflowRequest`
- Pydantic models: PascalCase with descriptive suffixes (`Request`, `Response`, `Info`)

**Functions:**
- snake_case: `get_model_config()`, `handle_tool_call()`, `build_prompt_from_messages()`
- Private helpers prefixed with underscore: `_execute_llm_with_tools()`, `_parse_stream_json()`

**Constants:**
- UPPER_SNAKE_CASE: `TOOL_CRAWL_AND_REFRESH`, `DEFAULT_MAX_RESPONSE_TOKENS`, `MAX_AGENT_ELAPSED_SECONDS`

## Where to Add New Code

**New LLM Provider:**
1. Add provider-specific completion method in `gateway/llm/client.py` (follow `_anthropic_chat_completion` pattern)
2. If CLI-based, add a provider class in `gateway/llm/cli_providers.py` (follow `CopilotCLIProvider` pattern)
3. Add bridge manager in `gateway/utils/` (follow `copilot_bridge_manager.py` pattern)
4. Register in `get_model_config()` resolution chain in `gateway/llm/client.py`
5. Add startup probe in `gateway/main.py` lifespan

**New Tool:**
1. Add tool name constant in `gateway/utils/tool_constants.py`
2. Add handler method in `gateway/routers/tools.py` `ToolHandler` class
3. Add dispatch case in `handle_tool_call()` in `gateway/routers/tools.py`
4. Add tool definition to `_load_tools()` in `gateway/routers/agent.py`
5. Set default limit in `DEFAULT_TOOL_LIMITS` in `gateway/utils/tool_constants.py`

**New Workflow Type:**
1. Add enum value in `gateway/agents/unified_workflow.py` `WorkflowType`
2. Add system prompt builder function `_build_system_prompt_{name}()` in `gateway/routers/agent.py`
3. Add routing case in `_build_system_prompt()` in `gateway/routers/agent.py`

**New MCP Server:**
1. Create directory under `mcp_servers/` with its own `pyproject.toml`
2. Implement MCP tool schemas with `GET /tools` and `POST /invoke` endpoints
3. Add Docker service in `deploy/docker-compose.dev.yml`
4. Add tool integration in `gateway/routers/tools.py` and `gateway/routers/agent.py`

**New API Endpoint on Gateway:**
1. Create router file in `gateway/routers/`
2. Mount in `gateway/main.py` with `app.include_router()`

**New Frontend Feature:**
1. Modify `clients/hichat/static/app.js` for UI logic
2. Modify `clients/hichat/static/index.html` for layout
3. Add proxy route in `clients/hichat/main.py` if new gateway endpoint needed

**Utilities:**
- Gateway shared helpers: `gateway/utils/`
- CLI helpers: `llmcrawl_cli/`
- Auth utilities: `tools/msauth/`

## Special Directories

**`deploy/`:**
- Purpose: All deployment artifacts (Docker, env, Grafana dashboards)
- Generated: No (manually maintained)
- Committed: Yes (except `.env` which is gitignored)

**`data/`:**
- Purpose: Runtime data (saved files from tool calls)
- Generated: Yes (at runtime)
- Committed: Structure only (`data/files/` exists as placeholder)

**`deploy/memory/`:**
- Purpose: Memory service storage (daily logs, MEMORY.md)
- Generated: Yes (at runtime by memory service)
- Committed: No (runtime data)

**`deploy/logs/`:**
- Purpose: Runtime log files from services
- Generated: Yes (at runtime)
- Committed: No

**`dist/` and `build/`:**
- Purpose: Python wheel build artifacts
- Generated: Yes (by `python -m build`)
- Committed: No

**`.planning/`:**
- Purpose: Planning and analysis documents for AI-assisted development
- Generated: Yes (by mapping tools)
- Committed: Yes

---

*Structure analysis: 2026-03-31*

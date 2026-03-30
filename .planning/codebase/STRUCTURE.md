# Codebase Structure

**Analysis Date:** 2026-03-29

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
│   ├── utils/              # Crawler utilities
│   └── tests/              # Crawler tests
├── indexer/                # Vector indexing service (Docker)
│   ├── main.py             # FastAPI app for index/query endpoints
│   ├── adapters/           # LlamaIndex store adapter
│   ├── vector/             # Vector DB abstractions
│   ├── utils/              # Indexer utilities
│   └── tests/              # Indexer tests
├── clients/                # Client applications
│   ├── hichat/             # Web chat UI (FastAPI + static HTML/JS/CSS)
│   │   ├── main.py         # HiChat FastAPI app, gateway proxy
│   │   ├── msal_auth.py    # MSAL authentication client
│   │   └── static/         # Frontend assets (index.html, app.js, styles.css)
│   └── demo/               # Demo scripts
├── services/               # Standalone services
│   └── memory_service/     # Memory service (Docker)
│       ├── main.py         # FastAPI wrapper around memsearch
│       ├── client.py       # Memory service client library
│       ├── Dockerfile       # Container build
│       └── requirements.txt
├── mcp_servers/            # MCP (Model Context Protocol) servers
│   ├── azure_devops_mcp_server/  # Azure DevOps code search + file access
│   ├── crawler_mcp_server/       # Crawler MCP wrapper
│   ├── local_access_mcp_server/  # Local filesystem access
│   └── wcd_bridge_mcp_server/    # Windows Composition Database bridge
├── tools/                  # Host-side bridge tools and CLI wrappers
│   ├── claude_bridge.py    # Claude CLI HTTP bridge (optional)
│   ├── copilot_bridge.py   # Copilot CLI HTTP bridge (optional)
│   ├── windows_composition_bridge.py  # WCD bridge
│   └── msauth/             # MSAL authentication utilities
├── llmcrawl_cli/           # CLI entry point (`llmcrawl` command)
│   ├── main.py             # CLI commands (deploy, bridges, hichat)
│   ├── deploy.py           # Docker compose management
│   ├── auth.py             # CLI auth helpers
│   ├── claude_bridge.py    # Claude bridge CLI launcher
│   └── copilot_bridge.py   # Copilot bridge CLI launcher
├── deploy/                 # Deployment configuration
│   ├── docker-compose.yml      # Production compose (wheel paths)
│   ├── docker-compose.dev.yml  # Dev compose (local source paths)
│   ├── .env                    # Environment config (DO NOT READ)
│   ├── crawler/            # Crawler Dockerfile
│   ├── gateway/            # Gateway Dockerfile
│   ├── indexer/            # Indexer Dockerfile
│   └── requirements/       # Per-service pip requirements
├── tests/                  # Integration tests
│   └── integration/        # End-to-end tests
├── scripts/                # Setup and management scripts
├── docs/                   # Documentation
├── data/                   # Local data directory
│   └── files/              # Saved files from tool calls
├── .github/                # CI/CD
│   └── workflows/          # GitHub Actions (build-wheel.yml)
├── pyproject.toml          # Python project config (black, isort, mypy, flake8)
├── Makefile                # Build/dev commands
└── CLAUDE.md               # AI assistant instructions
```

## Directory Purposes

**`gateway/`:**
- Purpose: Central orchestrator for all chat requests
- Contains: FastAPI app, LLM routing, tool calling loop, memory integration
- Key files:
  - `main.py`: App creation, lifespan, middleware, router mounting
  - `routers/agent.py`: Main `/agent/chat` endpoint, tool loop, context gathering
  - `routers/tools.py`: `ToolHandler` class dispatching tool calls to services
  - `routers/models.py`: `GET /api/models/available` endpoint
  - `routers/export.py`: Markdown export endpoint
  - `llm/client.py`: `LLMClient` with 4-tier model resolution and 5 provider backends
  - `llm/cli_providers.py`: `ClaudeCLIProvider` and `CopilotCLIProvider` subprocess wrappers
  - `llm/prompts.py`: Pydantic tool schemas, schema converters
  - `agents/unified_workflow.py`: `WorkflowType` enum, `UnifiedWorkflowRequest`/`Response` models
  - `agents/agent_config.py`: `AgentConfig` dataclass, `convert_mcp_tool_to_openai()`
  - `utils/memory_integration.py`: Memory service HTTP client (auto-log, flush, context injection)
  - `utils/conversation_store.py`: In-memory conversation history with TTL
  - `utils/prompt_compressor.py`: Token estimation + LLMLingua-2 compression
  - `utils/tool_constants.py`: All tool name constants and default per-tool limits
  - `utils/claude_bridge_manager.py`: Claude CLI/Bridge startup discovery
  - `utils/copilot_bridge_manager.py`: Copilot CLI/Bridge startup discovery
  - `utils/file_store.py`: File save logic for `save_file_for_download` tool
  - `utils/auth.py`: Bearer token extraction, Entra ID helpers
  - `utils/metrics.py`: Prometheus custom metrics
  - `utils/logging.py`: Structured logging setup
  - `utils/azdo_uri.py`: Azure DevOps URI parser (`azdo:` scheme)
  - `utils/token_context.py`: Context variable for bearer token propagation

**`crawler/`:**
- Purpose: Fetches web content via multiple strategies
- Contains: HTTP clients, content extraction, browser rendering
- Key files:
  - `main.py`: FastAPI app with `/crawl` endpoint
  - `clients/firecrawl.py`: FireCrawl API client with fallback logic
  - `extract/`: Trafilatura-based content extraction
  - `render/`: Playwright browser rendering for JS-heavy pages

**`indexer/`:**
- Purpose: Indexes documents into vector database for RAG retrieval
- Contains: LlamaIndex integration, vector DB adapters
- Key files:
  - `main.py`: FastAPI app with `/index` and `/query` endpoints
  - `adapters/llamaindex_store.py`: LlamaIndex + Qdrant/pgvector adapter

**`clients/hichat/`:**
- Purpose: Browser-based chat UI
- Contains: FastAPI proxy server + static frontend
- Key files:
  - `main.py`: FastAPI app serving static files, proxying to Gateway
  - `msal_auth.py`: MSAL token acquisition for Entra ID auth
  - `static/index.html`: Main HTML page
  - `static/app.js`: Chat UI logic, model selection, file viewer
  - `static/styles.css`: UI styling

**`services/memory_service/`:**
- Purpose: Persistent conversation memory with semantic search
- Contains: memsearch library wrapper, daily log management
- Key files:
  - `main.py`: FastAPI app wrapping memsearch (POST /write_daily, /write_memory, /search, GET /context)
  - `client.py`: Python client library for the memory service HTTP API
  - `Dockerfile`: Container build with Milvus dependency

**`mcp_servers/`:**
- Purpose: Model Context Protocol servers exposing tool schemas
- Contains: Separate Python packages, each with its own `pyproject.toml`
- Key subdirectories:
  - `azure_devops_mcp_server/`: Code search, file access, commit diff via Azure DevOps REST API
  - `crawler_mcp_server/`: MCP wrapper around crawler
  - `local_access_mcp_server/`: Local filesystem read/list/search
  - `wcd_bridge_mcp_server/`: Windows Composition Database queries

**`tools/`:**
- Purpose: Host-side HTTP bridge servers (optional fallbacks for CLI providers)
- Contains: FastAPI apps wrapping CLI executables
- Key files:
  - `claude_bridge.py`: HTTP wrapper around `claude.exe` CLI
  - `copilot_bridge.py`: HTTP wrapper around `copilot.exe` CLI
  - `windows_composition_bridge.py`: WCD bridge server
  - `msauth/`: MSAL authentication utilities

**`llmcrawl_cli/`:**
- Purpose: Main CLI entry point for the `llmcrawl` command
- Contains: Click/argparse commands for deployment, bridge management
- Key files:
  - `main.py`: CLI command definitions
  - `deploy.py`: Docker compose up/down/status management

**`deploy/`:**
- Purpose: Docker Compose files and deployment config
- Contains: Compose files, Dockerfiles, requirements, Grafana provisioning
- Key files:
  - `docker-compose.dev.yml`: Dev compose with local source mounts
  - `docker-compose.yml`: Production compose with wheel paths
  - `.env`: Environment configuration (secrets -- DO NOT READ)
  - `requirements/`: Per-service pip requirements files

## Key File Locations

**Entry Points:**
- `gateway/main.py`: Gateway FastAPI app (primary service)
- `crawler/main.py`: Crawler FastAPI app
- `indexer/main.py`: Indexer FastAPI app
- `clients/hichat/main.py`: HiChat web client
- `services/memory_service/main.py`: Memory service
- `llmcrawl_cli/main.py`: CLI tool

**Configuration:**
- `pyproject.toml`: Python project config (linting, formatting, build)
- `Makefile`: Dev commands (`make dev-up`, `make test-dev`, etc.)
- `deploy/.env`: Environment variables (DO NOT READ -- contains secrets)
- `deploy/docker-compose.dev.yml`: Docker service definitions for development

**Core Logic:**
- `gateway/routers/agent.py`: Chat endpoint + tool calling loop (largest file, ~1700 lines)
- `gateway/llm/client.py`: LLM provider routing (~600 lines)
- `gateway/llm/cli_providers.py`: Claude/Copilot subprocess providers (~650 lines)
- `gateway/routers/tools.py`: Tool dispatch to backend services
- `gateway/utils/memory_integration.py`: Memory service integration

**Testing:**
- `tests/integration/`: End-to-end integration tests
- `gateway/tests/`: Gateway unit tests
- `crawler/tests/`: Crawler unit tests
- `indexer/tests/`: Indexer unit tests

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (e.g., `cli_providers.py`, `conversation_store.py`)
- Static assets: `snake_case` or `camelCase` (e.g., `app.js`, `index.html`)

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
4. Add tool integration in `gateway/routers/tools.py` and `agent.py`

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

**`dist/` and `build/`:**
- Purpose: Python wheel build artifacts
- Generated: Yes (by `python -m build`)
- Committed: No

**`.planning/`:**
- Purpose: Planning and analysis documents for AI-assisted development
- Generated: Yes (by mapping tools)
- Committed: Yes

---

*Structure analysis: 2026-03-29*

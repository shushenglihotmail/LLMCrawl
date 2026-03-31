# External Integrations

**Analysis Date:** 2026-03-31

## LLM Provider Integrations

The gateway routes LLM requests based on `provider_type` resolved in `gateway/llm/client.py` via `get_model_config()`. Four provider paths exist:

**OpenAI / Azure OpenAI (`provider_type: "openai"`):**
- SDK: `openai` package (`AsyncOpenAI`, `AsyncAzureOpenAI`)
- Client initialized in `gateway/llm/client.py` lines 38-52
- Auth: `AZURE_OPENAI_API_KEY` or Entra ID bearer token (passed via `extra_headers`)
- Config: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION` (default "2024-02-01")
- Supports tool calling, streaming, temperature, max_tokens/max_completion_tokens
- Model-aware parameter handling: GPT-5.x and o-series use `max_completion_tokens` and fixed temperature

**Anthropic via Azure (`provider_type: "anthropic"`):**
- Direct HTTP calls via `httpx` (no Anthropic SDK)
- Endpoint: `AZURE_ANTHROPIC_ENDPOINT` env var
- Auth: `AZURE_OPENAI_API_KEY` or Entra ID bearer token
- Implementation: `gateway/llm/client.py` method `_anthropic_chat_completion()`
- Converts OpenAI-format messages to Anthropic format
- Context limit: 200,000 tokens (defined in `gateway/utils/prompt_compressor.py`)

**Claude Code CLI (`provider_type: "claude"`):**
- Direct subprocess execution of `claude.exe` CLI
- Implementation: `gateway/llm/cli_providers.py` class `ClaudeCLIProvider`
- CLI discovery: `CLAUDE_CLI_PATH` env var > PATH > Windows default locations
- Output format: `--output-format stream-json` parsed by `_parse_stream_json()`
- Models: `sonnet`, `sonnet[1m]`, `opus`, `opus[1m]`, `haiku` (defined in `CLAUDE_KNOWN_MODELS`)
- Effort levels: low, medium, high, max (maps `xhigh` -> `max`)
- Timeout: 1800s per request
- Flags: `--no-session-persistence`, `--tools ""` (disables built-in tools)
- Fallback: HTTP bridge at `CLAUDE_BRIDGE_URL` (port 8006) via `tools/claude_bridge.py`

**GitHub Copilot CLI (`provider_type: "copilot"`):**
- Direct subprocess execution of `copilot.exe` CLI
- Implementation: `gateway/llm/cli_providers.py` class `CopilotCLIProvider`
- CLI discovery: `COPILOT_CLI_PATH` env var > PATH (skip .bat wrappers) > Windows default locations
- Output format: `--output-format json` (JSONL) parsed by `_parse_copilot_jsonl()`
- Models: Claude variants + GPT-5.x + GPT-4.1 (defined in `COPILOT_KNOWN_MODELS`)
- Effort levels: low, medium, high, xhigh (maps `max` -> `xhigh`)
- Tools disabled via `--available-tools=` flag to act as pure LLM endpoint
- Flags: `-s` (silent), `--no-custom-instructions`
- Timeout: 1800s per request
- Fallback: HTTP bridge at `COPILOT_BRIDGE_URL` (port 8009) via `tools/copilot_bridge.py`

## Bridge Services

**Claude Bridge (`tools/claude_bridge.py`):**
- FastAPI HTTP wrapper around Claude Code CLI
- Port: 8006 (configurable via `CLAUDE_BRIDGE_PORT`)
- Endpoints: `POST /chat`, `GET /models`, `GET /health`
- Purpose: Optional HTTP fallback when direct CLI subprocess is not available
- Managed by: `gateway/utils/claude_bridge_manager.py`

**Copilot Bridge (`tools/copilot_bridge.py`):**
- FastAPI HTTP wrapper around GitHub Copilot CLI
- Port: 8009 (configurable via `COPILOT_BRIDGE_PORT`)
- Endpoints: `POST /chat`, `GET /models`, `GET /health`
- Purpose: Optional HTTP fallback when direct CLI subprocess is not available
- Managed by: `gateway/utils/copilot_bridge_manager.py`

**Windows Composition Database Bridge (`tools/windows_composition_bridge.py`):**
- Port: 8005
- Purpose: Windows Composition Database queries (Windows-only, runs on host)
- Tool constant: `TOOL_QUERY_COMPOSITION_DB` in `gateway/utils/tool_constants.py`
- Config: `WIN_COMP_BRIDGE_URL=http://host.docker.internal:8005`

## Data Storage

**PostgreSQL 16 with pgvector:**
- Image: `pgvector/pgvector:pg16`
- Port: 5432
- Used by: Firecrawl (crawl metadata), Indexer (pgvector embeddings)
- Connection: `PG_DSN=postgresql://postgres:password@postgres:5432/rag_db` (indexer)
- Init script: `deploy/nuq.sql`
- Adapter: `indexer/adapters/pgvector_adapter.py`

**Qdrant v1.7.0:**
- Image: `qdrant/qdrant:v1.7.0`
- Ports: 6333 (HTTP), 6334 (gRPC)
- Client: `qdrant-client` >=1.6.0
- Used by: Indexer for vector similarity search
- Adapter: `indexer/adapters/qdrant_adapter.py`
- Connection: `QDRANT_URL=http://qdrant:6333`

**Milvus v2.5.5:**
- Image: `milvusdb/milvus:v2.5.5`
- Port: 19530
- Client: `pymilvus` (pulled by memsearch)
- Used by: Memory service for semantic search vectors
- Connection: `MILVUS_URI` env var (default `./milvus.db` for Milvus Lite, or `milvus:19530` for container)

**Redis 7:**
- Image: `redis:7-alpine`
- Port: 6379
- Used by: Firecrawl for caching and rate limiting
- Connection: `redis://redis:6379`

**File Storage:**
- Memory service markdown files at `MEMORY_DATA_PATH` (default `/data/memory` in Docker, `./memory` locally)
- Layout: `{MEMORY_DATA_PATH}/daily/YYYY-MM-DD.md` (daily logs), `{MEMORY_DATA_PATH}/MEMORY.md` (durable facts)
- Gateway conversation store: in-memory with 24h TTL (`gateway/utils/conversation_store.py`)

## Web Crawling Pipeline

**Firecrawl:**
- Image: `ghcr.io/firecrawl/firecrawl:latest`
- Port: 3002
- Client: `crawler/clients/firecrawl_client.py`
- Dependencies: PostgreSQL + Redis + Playwright
- Config: `FIRECRAWL_URL`, `FIRECRAWL_AUTH_TYPE` (none|cookies|headers|basic|bearer)

**Playwright Service:**
- Image: `ghcr.io/firecrawl/playwright-service:latest`
- Port: 3003
- Purpose: JS-heavy page rendering fallback
- Client: `crawler/clients/playwright_client.py`
- Config: `CONCURRENT=5`, `TIMEOUT=300000`

**Trafilatura:**
- Library: `trafilatura` >=1.6.0
- Extractor: `crawler/extractors/trafilatura_extractor.py`
- Purpose: Content extraction from HTML

## MCP Servers (Tool Providers)

**Azure DevOps MCP Server:**
- Location: `mcp_servers/azure_devops_mcp_server/`
- Port: 8004
- Tools: `search_azure_devops_code`, `get_azure_devops_file`, `get_azure_devops_commit_changes`, `get_azure_devops_commit_file_diff`
- Auth: PAT (`AZURE_DEVOPS_PAT`) or MSAL (`AZURE_DEVOPS_AUTH_MODE=pat|msal`)
- Config: `AZURE_DEVOPS_ORG`, `AZURE_DEVOPS_PROJECT`, `AZURE_DEVOPS_REPO`, `AZURE_DEVOPS_BRANCH`
- SDK: `azure-devops` >=7.1.0b3, `msal` >=1.24.0
- Gateway discovers tools via `GET /tools` endpoint, converts to OpenAI format with `convert_mcp_tool_to_openai()`

**Local Access MCP Server:**
- Location: `mcp_servers/local_access_mcp_server/`
- Tools: `read_local_file`, `list_files`, `search_file_content`, `index_files`
- Purpose: Local filesystem access for the gateway

**Crawler MCP Server:**
- Location: `mcp_servers/crawler_mcp_server/`
- Tool: `crawl_and_refresh`

**WCD Bridge MCP Server:**
- Location: `mcp_servers/wcd_bridge_mcp_server/`
- Tool: `query_composition_db`

**Gateway-native Tools (no MCP server):**
- `save_file_for_download` - File download tool defined in `gateway/utils/tool_constants.py`
- `memory_search` - Memory search tool calling memory service HTTP API

## Memory Service

**Service:** `services/memory_service/main.py`
- Port: 8007
- Library: `memsearch` (MemSearch class with `memsearch.watch()` for auto-indexing file changes)
- Embeddings: Local sentence-transformers (`EMBEDDING_PROVIDER=local`)
- Vector store: Milvus (via pymilvus)

**HTTP Endpoints (called by gateway):**
- `POST /write_daily` - Write to daily conversation log
- `POST /write_memory` - Write durable facts to MEMORY.md
- `POST /search` - Semantic search across memories
- `GET /context` - Load memory context for conversation start
- `POST /reindex` - Rebuild vector index from markdown

**Gateway config:**
- `MEMORY_SERVICE_URL`: http://localhost:8007
- `MEMORY_AUTO_LOG`: true|false (auto-append to daily logs)
- `MEMORY_AUTO_FLUSH`: true|false (80% context flush trigger)
- `MEMORY_FLUSH_THRESHOLD`: 0.8

## Authentication & Identity

**Azure Entra ID (Token-based):**
- Used for: Azure OpenAI, Azure Anthropic endpoints
- Config: `ENTRA_CLIENT_ID`, `ENTRA_TENANT_ID`, `AZURE_FOUNDRY_SCOPE`
- JWT validation: `JWT_VALIDATION_ENABLED` (optional, using `PyJWT` + `cryptography`)
- MSAL client: `clients/hichat/msal_auth.py`, `tools/msauth/authenticate.py`
- Token passed as bearer in gateway middleware via `gateway/utils/token_context.py`

**Azure DevOps Auth:**
- PAT: `AZURE_DEVOPS_PAT` env var
- MSAL: Via `msal` library with `AZURE_DEVOPS_AUTH_MODE`

**API Keys (deprecated in favor of Entra ID):**
- `AZURE_OPENAI_API_KEY` - OpenAI/Anthropic Azure endpoints (optional with Entra ID)
- `OPENAI_API_KEY` - Direct OpenAI API (optional, only if provider=openai)

**Crawl Authentication:**
- `FIRECRAWL_AUTH_TYPE` - none|cookies|headers|basic|bearer
- `llmcrawl auth <url>` CLI command captures browser cookies for authenticated crawling

## Monitoring & Observability

**Metrics:**
- Prometheus FastAPI Instrumentator (`prometheus-fastapi-instrumentator`) - Auto-instrumented HTTP metrics
- Custom Prometheus metrics in `gateway/utils/metrics.py`:
  - `CRAWL_REQUESTS_TOTAL` - Counter by status, domain, source (playwright/firecrawl)
  - `CRAWL_DURATION_SECONDS` - Histogram by domain, source
  - `CRAWL_PAGES_PROCESSED` - Counter by domain, source
  - Functions: `record_llm_request()`, `record_crawl_request()`, `record_tool_call()`, `record_service_error()`, `set_service_up()`

**Monitoring Stack (optional, Docker compose profile "monitoring"):**
- Prometheus at port 9090, config: `deploy/prometheus.yml`
- Grafana at port 3001, provisioning: `deploy/grafana-provisioning/`

**Logging:**
- Python `logging` module throughout
- Custom setup: `gateway/utils/logging.py` (setup_logging, get_logger, log_tool_call, log_tool_result)
- Config: `LOG_LEVEL` (DEBUG|INFO|WARNING|ERROR|CRITICAL), `LOG_FORMAT` (json|text)
- Log directory: `deploy/logs/`

## Message Queues & Events

- None. All inter-service communication is synchronous HTTP REST.
- Firecrawl uses Redis internally for job queuing, but this is opaque to the project.

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected

## CI/CD & Deployment

**GitHub Actions (`.github/workflows/build-wheel.yml`):**
- **build-wheels**: Builds Python wheels for main package + MCP server packages, uploads to GitHub Releases
- **build-memory-service**: Builds Docker image from `services/memory_service/`, pushes to GHCR

**Deployment Scripts (Windows):**
- `scripts/start-services.ps1` - Start all services (Docker containers + Gateway + Memory)
- `scripts/stop-services.ps1` - Stop all services

**CLI Deployment:**
- `llmcrawl deploy --up` - Start services
- `llmcrawl deploy --status` - Health check all services

## Environment Configuration

**Required env vars (in `deploy/.env`):**
- `LLM_PROVIDER` - azure | openai
- `LLM_MODELS` - JSON model routing config
- `VECTOR_DB` - qdrant | pgvector
- `MEMORY_SERVICE_URL` - http://localhost:8007

**Optional env vars:**
- `CLAUDE_BRIDGE_URL` - http://localhost:8006 (only if using HTTP bridge)
- `COPILOT_BRIDGE_URL` - http://localhost:8009 (only if using HTTP bridge)
- `CLAUDE_CLI_PATH` - Override Claude CLI location
- `COPILOT_CLI_PATH` - Override Copilot CLI location
- `MEMORY_AUTO_LOG`, `MEMORY_AUTO_FLUSH`, `MEMORY_FLUSH_THRESHOLD`
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION`
- `AZURE_ANTHROPIC_ENDPOINT`
- `ENTRA_CLIENT_ID`, `ENTRA_TENANT_ID`, `AZURE_FOUNDRY_SCOPE`
- `AZURE_DEVOPS_PAT`, `AZURE_DEVOPS_ORG`, `AZURE_DEVOPS_PROJECT`, `AZURE_DEVOPS_REPO`
- `WIN_COMP_BRIDGE_URL`
- `JWT_VALIDATION_ENABLED`

## Service Port Map

| Port | Service | Location | Runtime |
|------|---------|----------|---------|
| 3002 | Firecrawl | Docker | Container |
| 3003 | Playwright | Docker | Container |
| 5432 | PostgreSQL | Docker | Container |
| 6333 | Qdrant | Docker | Container |
| 6379 | Redis | Docker | Container |
| 8000 | Gateway | Host | Local Python |
| 8001 | Crawler | Docker | Container |
| 8002 | Indexer | Docker | Container |
| 8004 | Azure DevOps MCP | Docker | Container |
| 8005 | WCD Bridge | Host | Local Python |
| 8006 | Claude Bridge | Host | Local Python (optional) |
| 8007 | Memory Service | Host | Local Python |
| 8009 | Copilot Bridge | Host | Local Python (optional) |
| 9090 | Prometheus | Docker | Container (optional) |
| 3001 | Grafana | Docker | Container (optional) |
| 19530 | Milvus | Docker | Container |

---

*Integration audit: 2026-03-31*

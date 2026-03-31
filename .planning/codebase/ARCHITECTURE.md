# Architecture

**Analysis Date:** 2026-03-31

## Pattern Overview

**Overall:** Service-oriented gateway pattern with tool-calling agent loop

**Key Characteristics:**
- Gateway runs on host (not Docker) for direct filesystem and CLI access
- Crawler, Indexer, and MCP servers run in Docker on `webrag-network`
- LLM routing uses a 4-tier resolution strategy (config, Claude CLI, Copilot CLI, default provider)
- Agent loop executes LLM calls with iterative tool calling until the model stops requesting tools
- Memory service provides persistent cross-session context via HTTP API

## Service Topology

**Local (host) services:**
- **Gateway (8000):** FastAPI orchestrator, entry point: `gateway/main.py`
- **Memory Service (8007):** Standalone memsearch-based service, entry point: `services/memory_service/main.py`
- **HiChat (8080):** Web client, entry point: `clients/hichat/main.py`

**Containerized (Docker) services:**
- **Crawler (8001):** FireCrawl + Playwright fallback, entry point: `crawler/main.py`
- **Indexer (8002):** LlamaIndex + Qdrant/pgvector, entry point: `indexer/main.py`
- **Azure DevOps MCP (8004):** Code search with MSAL/PAT auth, entry point: `mcp_servers/azure_devops_mcp_server/`
- **WCD Bridge (8005):** Windows Composition Database queries, entry point: `tools/windows_composition_bridge.py`

**Optional CLI bridges (host, HTTP fallback only):**
- **Claude Bridge (8006):** `tools/claude_bridge.py` -- HTTP wrapper around `claude.exe`
- **Copilot Bridge (8009):** `tools/copilot_bridge.py` -- HTTP wrapper around `copilot.exe`

**Data stores (Docker):**
- PostgreSQL (5432), Qdrant (6333), Redis (6379), Milvus (19530)

**Docker network:** All containers communicate via `webrag-network` external bridge. Create with: `docker network create webrag-network`

## Layers

**Web Client Layer:**
- Purpose: Browser-based chat UI that proxies to the Gateway
- Location: `clients/hichat/`
- Contains: FastAPI app (`main.py`) serving static HTML/JS/CSS, proxying `/agent/chat` and `/api/models/available` to the Gateway
- Depends on: Gateway HTTP API
- Used by: End users via browser at `http://localhost:8080`

**Gateway / Orchestrator Layer:**
- Purpose: Receives chat requests, gathers context, routes to LLM, executes tool loop, returns response
- Location: `gateway/`
- Contains: FastAPI app, routers, LLM client, tool handlers, memory integration, conversation store
- Depends on: LLM providers (OpenAI/Azure/Anthropic/Claude CLI/Copilot CLI), Crawler, Indexer, MCP servers, Memory Service
- Used by: HiChat web client, any HTTP client

**LLM Client Layer:**
- Purpose: Unified interface to 5 LLM provider types
- Location: `gateway/llm/client.py`, `gateway/llm/cli_providers.py`
- Contains: `LLMClient` class with provider-specific completion methods
- Depends on: OpenAI SDK (`AsyncAzureOpenAI`/`AsyncOpenAI`), Anthropic HTTP API, Claude CLI subprocess, Copilot CLI subprocess
- Used by: Agent router (`_execute_llm_with_tools`)

**Tool Execution Layer:**
- Purpose: Dispatches tool calls from LLM to appropriate service
- Location: `gateway/routers/tools.py`
- Contains: `ToolHandler` class with handlers for each tool type
- Depends on: Crawler, Indexer, Azure DevOps MCP, Memory Service, local filesystem
- Used by: Agent router tool loop

**Crawler Layer:**
- Purpose: Fetches and extracts web content
- Location: `crawler/`
- Contains: FireCrawl client (`crawler/clients/firecrawl.py`), Trafilatura extraction (`crawler/extract/trafilatura_wrap.py`), Playwright rendering (`crawler/render/playwright_runner.py`)
- Depends on: External web URLs, Playwright browser service (Docker)
- Used by: Gateway (direct HTTP), Gateway tool handler (`crawl_and_refresh`)

**Indexer Layer:**
- Purpose: Indexes crawled content into vector DB for RAG retrieval
- Location: `indexer/`
- Contains: LlamaIndex integration (`indexer/adapters/llamaindex_store.py`), Qdrant adapter (`indexer/vector/qdrant_store.py`), pgvector adapter (`indexer/vector/pgvector_store.py`)
- Depends on: Qdrant or pgvector (Docker)
- Used by: Gateway (after crawling when `enable_embedding=true`)

**Memory Layer:**
- Purpose: Persistent conversation memory with semantic search
- Location: `services/memory_service/` (service), `gateway/utils/memory_integration.py` (client)
- Contains: memsearch library wrapper, daily log + MEMORY.md storage
- Depends on: Milvus (vector DB), filesystem for markdown storage
- Used by: Gateway (auto-logging, context injection, flush/distillation)

## Data Flow

**Primary Chat Request Flow (HiChat -> Gateway -> LLM):**

1. User sends message via HiChat UI (`clients/hichat/static/app.js`)
2. HiChat proxies POST to Gateway `/agent/chat` with `UnifiedWorkflowRequest`
3. Gateway `execute()` in `gateway/routers/agent.py` begins processing:
   a. Expands reference file paths (`_expand_paths`) -- local or Azure DevOps
   b. Gathers reference file content (`_gather_reference_files`) -- reads from filesystem or AzDO MCP
   c. Crawls seed URLs (`_crawl_urls`) -- calls Crawler HTTP API, optionally indexes via Indexer
   d. Builds context string from gathered content (`_build_context_string`)
   e. Applies workflow restrictions (`_apply_workflow_restrictions`)
   f. Builds system prompt based on `WorkflowType` (`_build_system_prompt`)
   g. Injects durable memory for new conversations (HTTP GET to Memory Service `/context`)
   h. Logs user message to daily log (HTTP POST to Memory Service `/write_daily`)
   i. Builds message list with conversation history (`_build_messages`)
   j. Loads tool definitions (`_load_tools`) -- fetches MCP schemas from AzDO server, builds OpenAI-format tool defs
   k. Checks for 80% context flush trigger
4. Gateway calls `_execute_llm_with_tools()`
5. `LLMClient.chat_completion()` routes to appropriate provider (see Model Routing below)
6. If LLM returns `tool_calls`, gateway enters tool loop (see Tool Loop below)
7. Gateway saves conversation history, logs assistant response to memory, returns `UnifiedWorkflowResponse`

**Tool Calling Loop (`_execute_llm_with_tools` in `gateway/routers/agent.py`):**

1. Initial LLM call with messages + tool definitions
2. While response contains `tool_calls`:
   a. Check cancellation flag for this conversation
   b. Check elapsed time against `MAX_AGENT_ELAPSED_SECONDS` (default 900s / 15min)
   c. Check per-tool usage limits against `TOOL_ROUND_LIMITS`
   d. Filter out tools that exceeded their limits
   e. Append assistant message with tool calls to message list
   f. For each tool call: dispatch to `ToolHandler.handle_tool_call()` in `gateway/routers/tools.py`
   g. Append tool results to message list
   h. Call LLM again with updated messages
3. If time budget exceeded: execute pending `save_file_for_download` calls, ask LLM for wrap-up response
4. Return final response text, token count, and list of saved files

**Tool Dispatch (in `gateway/routers/tools.py`):**
- `crawl_and_refresh` -> Crawler HTTP POST `/crawl`, then optionally Indexer POST `/index`
- `search_azure_devops_code`, `get_azure_devops_file`, etc. -> Azure DevOps MCP HTTP POST `/invoke`
- `query_composition_db` -> WCD Bridge HTTP POST
- `save_file_for_download` -> Direct filesystem write (gateway-native, no MCP)
- `memory_search` -> Memory Service HTTP POST `/search`

**File Save Pipeline:**
1. LLM calls `save_file_for_download` tool with `{filename, content, path?}`
2. `ToolHandler._handle_save_file_for_download()` writes content to disk
3. Response includes `saved_path` in `UnifiedWorkflowResponse.saved_files[]`
4. HiChat UI renders saved file links with viewer integration

**Crawl Pipeline (inside `crawl_and_refresh` tool or `_crawl_urls` context gathering):**
1. Gateway sends URLs to Crawler POST `/crawl` with depth and max_results
2. Crawler tries FireCrawl first (fast, supports auth cookies)
3. If FireCrawl fails for any URL, Playwright fallback renders the page
4. Trafilatura extracts clean text/markdown from HTML
5. Optionally, Gateway sends docs to Indexer POST `/index` for vector indexing

**State Management:**
- Conversation history: In-memory `ConversationStore` with 24h TTL, 50 messages max per conversation (`gateway/utils/conversation_store.py`)
- Long-term memory: Markdown files managed by Memory Service, semantic search via Milvus
- Active request tracking: In-memory dict in `gateway/routers/agent.py` for cancellation support

## Model Routing

**4-Tier Resolution in `LLMClient.get_model_config()` (`gateway/llm/client.py`):**

1. **LLM_MODELS config (highest priority):** JSON array in env var. Each entry has `name`, `deployment_name`, `provider_type` (openai/anthropic/claude/copilot), `max_output_tokens`. User explicitly controls routing.

2. **Claude CLI/Bridge discovery:** At startup, `ClaudeBridgeManager` (`gateway/utils/claude_bridge_manager.py`) probes Claude CLI or Bridge, caches known models (sonnet, opus, haiku + `[1m]` variants). If model name matches cached set, routes to `claude` provider.

3. **Copilot CLI/Bridge discovery:** At startup, `CopilotBridgeManager` (`gateway/utils/copilot_bridge_manager.py`) probes Copilot CLI, uses hardcoded known-models list (`COPILOT_KNOWN_MODELS` in `gateway/llm/cli_providers.py`). If model name matches, routes to `copilot` provider.

4. **Default `LLM_PROVIDER` fallback:** Falls back to `LLM_PROVIDER` env var (azure/openai/anthropic).

**Provider Dispatch in `LLMClient.chat_completion()` (`gateway/llm/client.py`):**
- `copilot` -> `_copilot_chat_completion()` -> `CopilotCLIProvider.run_chat()` (subprocess) or HTTP bridge fallback
- `claude` -> `_claude_chat_completion()` -> `ClaudeCLIProvider.run_chat()` (subprocess) or HTTP bridge fallback
- `anthropic` -> `_anthropic_chat_completion()` -> Direct HTTP POST to Azure Anthropic endpoint
- `openai` (default) -> `_openai_chat_completion()` -> `AsyncAzureOpenAI` or `AsyncOpenAI` SDK

**CLI Subprocess Pattern (`gateway/llm/cli_providers.py`):**
- `ClaudeCLIProvider`: Finds `claude.exe` on PATH, runs with `--output-format stream-json`, parses NDJSON events
- `CopilotCLIProvider`: Finds `copilot.exe` on PATH, runs with `--output-format json`, parses JSONL events
- Both convert OpenAI-style messages to a single text prompt via `build_prompt_from_messages()`
- Both strip `NODE_OPTIONS` from env to avoid Node.js CLI conflicts
- 1800s (30min) subprocess timeout

## Workflow Types

**Defined in `gateway/agents/unified_workflow.py`:**

| Workflow | System Role | File Tools | AzDO Tools | Use Case |
|----------|------------|------------|------------|----------|
| `GENERAL_CHAT` | Informational consultant | No | No | Casual conversation |
| `CODE_ANALYSIS` | Technical architect | Yes | Yes | Code review, refactoring |
| `BUILD_SYSTEM_ANALYSIS` | Build engineer | Yes | Yes | Build/manifest analysis |
| `FILE_EXPLORER` | DevOps assistant | Yes | Yes | File browsing/searching |

Each workflow has a dedicated system prompt builder in `gateway/routers/agent.py`:
- `_build_system_prompt_general_chat()`
- `_build_system_prompt_code_analysis()`
- `_build_system_prompt_build_system()`
- `_build_system_prompt_file_explorer()`

## Key Abstractions

**UnifiedWorkflowRequest (`gateway/agents/unified_workflow.py`):**
- Purpose: Single request model for all workflow types
- Contains: `workflow`, `user_message`, `reference_files`, `seed_urls`, `expose_to_llm`, `model`, `conversation_id`, `effort`
- Pattern: Discriminated union via `workflow` field that controls system prompt and tool availability

**AgentConfig (`gateway/agents/agent_config.py`):**
- Purpose: Holds service URLs for all downstream services
- Examples: `crawler_url`, `indexer_url`, `azure_devops_mcp_url`, `memory_service_url`
- Pattern: Singleton, created once in `get_agent_config()`

**LLMClient (`gateway/llm/client.py`):**
- Purpose: Unified interface to all LLM providers with model resolution
- Pattern: Strategy pattern -- `get_model_config()` resolves provider, `chat_completion()` dispatches to provider-specific method

**ToolHandler (`gateway/routers/tools.py`):**
- Purpose: Dispatches tool calls to appropriate backend service
- Pattern: Command pattern -- tool name determines handler method

**ConversationStore (`gateway/utils/conversation_store.py`):**
- Purpose: In-memory conversation history with automatic TTL cleanup
- Pattern: Simple dict-based store, 24h max age, 50 messages max per conversation
- Used by: Agent router to inject conversation history into LLM messages

## Entry Points

**Gateway FastAPI App:**
- Location: `gateway/main.py`
- Triggers: `uvicorn` or `python -m gateway`
- Responsibilities: Mounts routers, runs lifespan (probes CLI bridges), serves HTTP API

**Agent Chat Endpoint:**
- Location: `gateway/routers/agent.py` -> `POST /agent/chat`
- Triggers: HTTP POST from HiChat or any client
- Responsibilities: Full request lifecycle -- context gathering, LLM call, tool loop, memory integration

**HiChat Client:**
- Location: `clients/hichat/main.py`
- Triggers: `hichat` CLI command or `python -m clients.hichat`
- Responsibilities: Serves web UI, proxies requests to Gateway, handles MSAL auth

**CLI Entry Point:**
- Location: `llmcrawl_cli/main.py`
- Triggers: `llmcrawl` command
- Responsibilities: Deploy commands (`deploy --up/--down/--status`), bridge startup (`claude-bridge`, `copilot-bridge`), auth (`auth <url>`), WCD bridge (`wcd-bridge`)

**Crawler Service:**
- Location: `crawler/main.py`
- Triggers: `uvicorn crawler.main:app` (in Docker)
- Endpoints: `POST /crawl`, `POST /render`, `POST /extract`, `GET /health`

**Indexer Service:**
- Location: `indexer/main.py`
- Triggers: `uvicorn indexer.main:app` (in Docker)
- Endpoints: `POST /index`, `POST /retrieve`, `GET /collection/info`, `DELETE /documents`, `GET /health`

**Memory Service:**
- Location: `services/memory_service/main.py`
- Triggers: `uvicorn services.memory_service.main:app`
- Endpoints: `POST /write_daily`, `POST /write_memory`, `POST /search`, `GET /context`, `POST /reindex`, `GET /health`

## Error Handling

**Strategy:** Catch-and-log with graceful degradation

**Patterns:**
- LLM errors: Caught in `chat_completion()`, re-raised with extracted error message from Azure/OpenAI response body. Tool loop continues if individual tool calls fail.
- Tool errors: Caught in `ToolHandler.handle_tool_call()`, returned as `{"error": "..."}` in tool result so LLM can adapt its strategy.
- Time budget: After `MAX_AGENT_ELAPSED_SECONDS` (default 900s), pending `save_file_for_download` calls are executed, then LLM is asked for a wrap-up response with a budget-exceeded note.
- Per-tool limits: `TOOL_ROUND_LIMITS` dict (env-configurable) controls max calls per tool. Exceeded tools are filtered from subsequent rounds. If all tools exceeded, loop breaks.
- Cancellation: Active requests tracked in `_active_requests` dict. Checked before each tool round and tool execution. Returns `"*Request was cancelled.*"`.
- CLI subprocess: 1800s timeout, exit code checking, stderr/stdout error extraction.
- Service health: All services expose `GET /health` endpoint. `deploy/.env` + `scripts/health_check.ps1` for monitoring.

## Cross-Cutting Concerns

**Logging:** Python `logging` module, configured in `gateway/utils/logging.py`. Structured log helpers: `log_request()`, `log_response()`, `log_tool_call()`, `log_tool_result()`.

**Metrics:** Prometheus via `prometheus_fastapi_instrumentator`. Custom metrics in `gateway/utils/metrics.py` for LLM requests, tool calls, crawl requests, agent activity timing. Optional Grafana dashboards in `deploy/grafana-provisioning/`.

**Authentication:** Bearer token middleware in `gateway/main.py` extracts `Authorization` header, stores in context var (`gateway/utils/token_context.py`). Entra ID auth for Azure OpenAI/Anthropic. MSAL auth in HiChat client (`clients/hichat/msal_auth.py`). PAT auth for Azure DevOps MCP server.

**Prompt Compression:** `gateway/utils/prompt_compressor.py` -- estimates token count via tiktoken, compresses with LLMLingua-2 (BERT-based, CPU-friendly) or truncation fallback if messages exceed provider context limits (200k Anthropic, 128k OpenAI/Azure).

**Memory Integration:** `gateway/utils/memory_integration.py` -- auto-logs messages to daily log (`MEMORY_AUTO_LOG`), injects durable memory at conversation start, triggers 80% context flush with distillation prompt (`MEMORY_AUTO_FLUSH`, `MEMORY_FLUSH_THRESHOLD`).

---

*Architecture analysis: 2026-03-31*

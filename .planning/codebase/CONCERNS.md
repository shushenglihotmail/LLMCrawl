# Codebase Concerns

**Analysis Date:** 2026-03-31

## Security Concerns

**Path Traversal in File Save Tool:**
- Risk: The `_handle_save_file_for_download()` method in `gateway/routers/tools.py` (lines 533-598) accepts LLM-controlled `path` and `filename` parameters without any path traversal validation. An LLM could craft arguments like `filename="../../etc/passwd"` or `path="/etc"` to write files to arbitrary locations on the host filesystem. The method calls `target.parent.mkdir(parents=True, exist_ok=True)` which will create any intermediate directories.
- Files: `gateway/routers/tools.py` (lines 553-576)
- Current mitigation: The gateway runs as the current user, so OS-level permissions provide some protection. The LLM decides the path, not the end user directly, but prompt injection could influence it.
- Recommendations: Resolve the target path and verify it stays within an allowed directory (e.g., cwd or a configured `ALLOWED_SAVE_DIRS` env var). Reject paths containing `..` segments.

**Path Traversal in File Viewer Endpoint:**
- Risk: The `GET /agent/api/view-file?path=...` endpoint (`gateway/routers/agent.py`, lines 1748-1767) accepts arbitrary file paths and reads them. Any user (authenticated or not, since JWT validation is disabled by default) can read any file on the host that the process can access.
- Files: `gateway/routers/agent.py` (lines 1748-1767)
- Current mitigation: None. The path is passed directly to `Path(path).read_text()`.
- Recommendations: Restrict readable paths to a whitelist of allowed directories. At minimum, reject paths outside the save directory.

**CORS Wildcard on All Services:**
- Risk: Every FastAPI service uses `allow_origins=["*"]` in CORS middleware with `allow_credentials=True`. This allows any web origin to make authenticated requests to these APIs.
- Files: `gateway/main.py` (line 84), `crawler/main.py` (line 102), `indexer/main.py` (line 115), `services/memory_service/main.py` (line 272), `mcp_servers/local_access_mcp_server/main.py` (line 32)
- Current mitigation: Comment says "Configure appropriately for production" but no production config exists. The `allow_credentials=True` with `allow_origins=["*"]` combination technically violates the CORS spec.
- Recommendations: Set specific allowed origins via environment variable for production. Remove `allow_credentials=True` when using wildcard origin.

**No Authentication on Most Endpoints:**
- Risk: JWT validation is disabled by default (`JWT_VALIDATION_ENABLED` defaults to `"false"` in `gateway/utils/auth.py` line 29). The bearer token is extracted but only passed through to LLM providers, not validated at the gateway level. The `auto_error=False` setting means missing tokens are silently accepted.
- Files: `gateway/utils/auth.py` (lines 28-29, 44)
- Current mitigation: Optional JWT validation exists but must be explicitly enabled.
- Recommendations: For any internet-exposed deployment, enable JWT validation or add API key authentication.

**JWKS Keys Not Cached:**
- Risk: When JWT validation IS enabled, every request fetches JWKS keys from Microsoft via HTTP. This is slow, unreliable, and creates a DoS vector.
- Files: `gateway/utils/auth.py` (lines 156-192). Comment on line 167 acknowledges: "In production, you should cache JWKS to avoid repeated requests."
- Recommendations: Cache JWKS keys with a TTL (e.g., use `PyJWKClient` with built-in caching).

**PowerShell Injection via WCD Bridge:**
- Risk: The `query_composition_db` tool passes LLM-generated PowerShell snippets directly to the WCD bridge for execution. If the LLM is manipulated via prompt injection, arbitrary PowerShell could be executed on the host.
- Files: `gateway/routers/agent.py` (lines 932-981), `mcp_servers/wcd_bridge_mcp_server/wcd_bridge_mcp_server/windows_composition_bridge.py`
- Current mitigation: The bridge presumably sandboxes execution to `$d` object methods, but the gateway sends raw LLM output.
- Recommendations: Validate queries against a whitelist of allowed `$d` methods. Reject queries containing dangerous cmdlets.

**Full Environment Inherited by CLI Subprocesses:**
- Risk: `_clean_subprocess_env()` in `gateway/llm/cli_providers.py` (lines 29-46) copies the entire `os.environ` to CLI subprocesses, only stripping `NODE_OPTIONS`. API keys, database credentials, and other secrets in the gateway environment are visible to Claude/Copilot subprocesses.
- Files: `gateway/llm/cli_providers.py` (lines 29-46)
- Current mitigation: CLI subprocesses are trusted tools running locally; practical risk is low.
- Recommendations: Build a minimal env containing only `PATH`, `HOME`, `USERPROFILE`, `TEMP`, `PYTHONIOENCODING`. Strip all `*_KEY`, `*_SECRET`, `*_TOKEN`, `*_PASSWORD` vars.

**Hardcoded Default Credentials:**
- Risk: PgVector store uses `postgresql://postgres:password@postgres:5432/rag_db` as default DSN.
- Files: `indexer/vector/pgvector_store.py` (line 28)
- Current mitigation: Environment variable override via `PG_DSN`.
- Recommendations: Remove default password from source code. Require explicit configuration.

## Performance Concerns

**LLMClient Instantiated Per Request:**
- Problem: `LLMClient()` is created fresh on every request in `_execute_llm_with_tools()` (line 1146) and `manual_distill()` (line 1873). The constructor probes for CLI executables, imports modules, and creates HTTP clients.
- Files: `gateway/routers/agent.py` (lines 1146, 1873), `gateway/llm/client.py` (lines 34-81)
- Cause: A `get_llm_client()` singleton exists at line 1500 of `client.py` but is never called from the agent router.
- Improvement path: Use `get_llm_client()` singleton or FastAPI dependency injection.

**In-Memory Conversation Store Not Scalable:**
- Problem: `ConversationStore` uses a plain Python dict with no persistence. All conversations are lost on restart. Cannot scale horizontally (each gateway instance has its own store).
- Files: `gateway/utils/conversation_store.py` (entire file, 82 lines)
- Current capacity: Limited by process memory. 50 messages per conversation, 24-hour TTL.
- Limit: Single-process, single-host only.
- Scaling path: Move to Redis or PostgreSQL as noted in the file's own docstring (line 3).

**httpx Client Created Per Tool Call:**
- Problem: A new `httpx.AsyncClient` is created for each tool call, MCP invocation, and crawl request. Connection pooling is lost.
- Files: `gateway/routers/tools.py` (lines 347, 379, 402, 468), `gateway/routers/agent.py` (lines 216, 369)
- Improvement path: Share a persistent `httpx.AsyncClient` per service connection, created at startup.

**CLI Subprocess Overhead:**
- Problem: Each Claude/Copilot request spawns a new subprocess (`subprocess.run`), which on Windows involves process creation overhead (~200-500ms) plus CLI initialization time. The 1800-second (30-minute) timeout is generous; a stuck subprocess blocks an async worker for the full duration.
- Files: `gateway/llm/cli_providers.py` (lines 228-239, 529-540)
- Cause: CLI tools load the full Node.js runtime per invocation. No way to cancel a running subprocess if the HTTP client disconnects.
- Improvement path: For Claude, use the direct Anthropic API (`provider_type: anthropic`) to avoid subprocess overhead. Add subprocess cancellation via `asyncio.Task` cancellation.

## Maintainability Concerns

**Massive Agent Router File:**
- Problem: `gateway/routers/agent.py` is 1920 lines -- a single file handling path expansion, context gathering, crawling, system prompt construction (4 workflow types), tool loading, LLM execution loop with tool calling, message building, memory integration, and multiple API endpoints.
- Files: `gateway/routers/agent.py` (1920 lines)
- Impact: Difficult to navigate, test, and modify. High risk of merge conflicts.
- Fix approach: Extract into modules: `agent/prompts.py`, `agent/context.py`, `agent/execution.py`, `agent/tools.py`.

**Large LLM Client File:**
- Problem: `gateway/llm/client.py` is 1505 lines handling OpenAI, Azure, Anthropic, Claude CLI, and Copilot CLI -- plus JSON tool call parsing and prompt stripping utilities.
- Files: `gateway/llm/client.py` (1505 lines)
- Fix approach: Extract provider-specific logic into separate files (already partially done with `cli_providers.py`).

**Bare `except:` Clauses:**
- Issue: 13+ bare `except:` clauses that silently swallow all exceptions including `KeyboardInterrupt` and `SystemExit`.
- Files:
  - `crawler/utils/robots.py` (lines 103, 124, 165, 231)
  - `crawler/render/playwright_runner.py` (lines 205, 299, 378, 386, 457, 459)
  - `crawler/main.py` (line 86)
  - `indexer/main.py` (line 82)
  - `indexer/vector/qdrant_store.py` (line 291)
- Fix approach: Replace with `except Exception:` at minimum. For cleanup code, use `finally` blocks.

**Broad `except Exception` Overuse:**
- Issue: Over 80 catch-all `except Exception as e` blocks that log and continue. This masks bugs and makes debugging difficult.
- Files: Nearly every module -- `gateway/routers/agent.py`, `crawler/clients/firecrawl.py`, `gateway/llm/client.py`, `tools/claude_bridge.py`, `clients/hichat/msal_auth.py`
- Fix approach: Catch specific exception types. Let unexpected exceptions propagate.

**Duplicate Code for Save File Tracking:**
- Issue: The pattern of "inject conversation_id into save_file args, execute tool, parse result, append to saved_files" is duplicated 3 times in `_execute_llm_with_tools()`.
- Files: `gateway/routers/agent.py` (lines 1210-1228, 1270-1294, 1296-1326)
- Fix approach: Extract a helper function like `_execute_and_track_save_calls()`.

**Inconsistent Singleton Patterns:**
- Issue: Some modules use module-level globals with getter functions (`_conversation_store`, `_tool_handler`, `_llm_client`, `_agent_config`), but usage is inconsistent -- `LLMClient()` is called directly in the agent router instead of using the existing `get_llm_client()`.
- Files: `gateway/utils/conversation_store.py`, `gateway/routers/tools.py`, `gateway/llm/client.py`, `gateway/routers/agent.py`
- Fix approach: Standardize on FastAPI dependency injection or a consistent singleton pattern.

## Technical Debt

| Item | Severity | Location | Description |
|------|----------|----------|-------------|
| setuptools version conflict | Medium | `pyproject.toml` (lines 42, 51-52) | memsearch requires `setuptools<75`, llama-index requires `setuptools>=80.9`. Cannot install both in same venv. Indexer must run in Docker. |
| CLI tool calling via text parsing | Medium | `gateway/llm/client.py` (lines 660-695, 724-736) | Claude/Copilot CLIs cannot use native tool calling. Tools are injected into system prompt as JSON, then tool calls are parsed from response text. Fragile and error-prone. |
| Prompt token estimation inaccurate | Low | `gateway/utils/prompt_compressor.py` (line 32) | Uses `cl100k_base` tiktoken encoding for all providers including Anthropic, which uses a different tokenizer. Token estimates may be wrong by 10-20% for non-OpenAI models. |
| Hardcoded model lists | Low | `gateway/llm/cli_providers.py` (lines 121-127, 391-410) | Claude and Copilot model lists are hardcoded. Must be manually updated when new models are released. |
| Duplicated crawl fallback formatting | Low | `gateway/routers/tools.py` (lines 218-241, 253-280, 289-321) | Three near-identical dict-comprehension blocks for formatting crawled docs when indexing/retrieval fails. Inconsistent truncation (full vs 500 chars). |

## Dependency Risks

**memsearch and setuptools Conflict:**
- Risk: Core dependency conflict between memsearch (`setuptools<75`) and llama-index (indexer, `setuptools>=80.9`). Documented and managed via Docker isolation, but creates friction for local development.
- Impact: Cannot run indexer and memory service in the same Python environment.
- Migration plan: Wait for upstream to relax constraints, or replace memsearch with direct Milvus client.

**Optional Import Pattern:**
- Risk: Several modules use try/except to make dependencies optional (`asyncpg`, `playwright`, `numpy`, `jwt`). Services start but fail at runtime when functionality is needed.
- Files: `indexer/vector/pgvector_store.py` (lines 14-19), `crawler/render/playwright_runner.py` (lines 16-20), `gateway/utils/auth.py` (lines 11-19)
- Impact: Silent failures. Service appears healthy but specific operations fail.
- Migration plan: Fail fast at startup if required dependencies are missing. Use health checks that exercise critical imports.

**memsearch Library Maintenance:**
- Risk: Relatively new library with a restrictive setuptools constraint. If unmaintained, the memory service is affected.
- Impact: Memory service search functionality depends on it.
- Migration plan: memsearch is contained within `services/memory_service/`. Could be replaced with direct Milvus client + custom embedding logic.

## Operational Risks

**No Data Persistence for Conversations:**
- Risk: All conversation history is in-memory. A gateway restart loses all active conversations.
- Files: `gateway/utils/conversation_store.py`
- Recovery: None. Conversations cannot be recovered after restart.
- Recommendations: Use Redis or PostgreSQL for conversation storage.

**No Health Check for Dependent Services:**
- Risk: Gateway starts successfully even if crawler, indexer, or memory service are down. Tool calls fail at runtime.
- Files: `gateway/main.py` (lifespan, lines 31-57)
- Current mitigation: Health endpoint at `/agent/health` shows configured URLs but does not probe them.
- Recommendations: Add startup probes or lazy health checks.

**CLI Subprocess Timeout Risk:**
- Risk: Claude CLI has a 1800-second (30-minute) timeout. A stuck CLI process blocks an async worker for the full duration. With default uvicorn workers, a few stuck calls can exhaust all workers.
- Files: `gateway/llm/cli_providers.py` (line 236)
- Recommendations: Reduce timeout. Add process group kill on cancellation. Monitor for long-running subprocesses.

**No Request Size Limits:**
- Risk: The `/agent/chat` endpoint accepts unbounded request bodies. Large `reference_files`, `user_message`, or `seed_urls` payloads can consume memory.
- Files: `gateway/routers/agent.py` (line 1464, `execute()`)
- Recommendations: Add request body size limits via middleware or Pydantic validators.

**Dual Gateway on Restart:**
- Risk: `scripts/start-services.ps1` does not check whether a gateway or memory service is already running before starting new instances. Running it twice creates conflicting processes on the same port.
- Files: `scripts/start-services.ps1`
- Fix: Check PID file and port availability before starting.

## Test Coverage Gaps

**Gateway Agent Router (Core Logic) Untested:**
- What's not tested: The core `execute()` endpoint and `_execute_llm_with_tools()` (the main business logic loop) have no unit tests. Existing `test_gateway.py` only tests tool schema structure.
- Files: `gateway/tests/test_gateway.py` (147 lines), `gateway/routers/agent.py` (1920 lines)
- Risk: Regressions in tool calling, prompt building, context gathering, and memory integration go undetected.
- Priority: High

**LLM Client Untested:**
- What's not tested: No tests for `gateway/llm/client.py` (1505 lines). Model resolution, Anthropic format conversion, CLI fallback logic, JSON tool call parsing -- all untested.
- Files: `gateway/llm/client.py`
- Risk: Provider routing bugs and format conversion errors.
- Priority: High

**CLI Providers Untested:**
- What's not tested: `gateway/llm/cli_providers.py` (650 lines). Subprocess spawning, stream-json parsing, prompt building, CLI discovery -- all untested.
- Files: `gateway/llm/cli_providers.py`
- Risk: Claude/Copilot CLI integration breaks silently.
- Priority: High

**File Save Tool Untested (Security-Sensitive):**
- What's not tested: `_handle_save_file_for_download()` in `gateway/routers/tools.py` -- path resolution, directory creation, permission errors, and the path traversal vulnerability.
- Files: `gateway/routers/tools.py` (lines 533-598)
- Risk: Security-sensitive code with no test coverage.
- Priority: High

**Memory Integration Untested:**
- What's not tested: `gateway/utils/memory_integration.py` (379 lines) -- daily log appending, flush detection, distillation parsing.
- Files: `gateway/utils/memory_integration.py`
- Risk: Memory features silently break or corrupt stored memory.
- Priority: Medium

**Overall Coverage:**
- Approximately 1,176 lines of test code covering ~24,153 lines of source. Most tests are integration-level or cover peripheral functionality. The core gateway agent loop, LLM client routing, and CLI providers have zero test coverage.

## Recommendations

1. **[Critical] Fix path traversal in file save/view** -- Add path validation to `_handle_save_file_for_download()` and `/api/view-file`. Restrict operations to an allowed directory tree.

2. **[Critical] Add CORS restrictions for production** -- Replace `allow_origins=["*"]` with configurable origins via environment variable across all services.

3. **[High] Add tests for core gateway logic** -- The agent router, LLM client, and CLI providers are the heart of the system and have zero test coverage. Start with unit tests for `_execute_llm_with_tools`, `get_model_config`, and `build_prompt_from_messages`.

4. **[High] Use LLMClient singleton** -- Replace `LLMClient()` calls in agent router with `get_llm_client()` to avoid per-request initialization overhead.

5. **[High] Break up large files** -- Split `gateway/routers/agent.py` (1920 lines) and `gateway/llm/client.py` (1505 lines) into focused modules.

6. **[Medium] Replace bare `except:` clauses** -- All 13+ bare `except:` blocks should use `except Exception:` at minimum.

7. **[Medium] Persist conversation store** -- Move from in-memory dict to Redis or PostgreSQL for conversation history.

8. **[Medium] Share httpx clients** -- Create persistent `httpx.AsyncClient` instances at startup instead of per-request.

9. **[Low] Cache JWKS keys** -- If JWT validation is enabled, cache signing keys to avoid per-request HTTP calls.

10. **[Low] Add request body size limits** -- Prevent oversized payloads from consuming memory or blocking workers.

---

*Concerns audit: 2026-03-31*

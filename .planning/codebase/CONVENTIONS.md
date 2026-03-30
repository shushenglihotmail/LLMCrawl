# Coding Conventions

**Analysis Date:** 2026-03-29

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python modules: `unified_workflow.py`, `conversation_store.py`, `cli_providers.py`
- Test files: `test_<module>.py` prefix: `test_gateway.py`, `test_crawler.py`, `test_expand_paths.py`
- Config/entry files: `main.py` in each service root

**Functions:**
- Use `snake_case` for all functions and methods: `get_bearer_token()`, `record_llm_request()`, `parse_azdo_uri()`
- Private/internal functions prefixed with underscore: `_mark_request_active()`, `_handle_crawl_and_refresh()`, `_cleanup_old_conversations()`
- Async functions: prefix with `async def`, no naming distinction from sync: `async def export_to_markdown()`
- Factory/accessor functions use `get_` prefix: `get_logger()`, `get_conversation_store()`, `get_claude_bridge_manager()`, `get_file_store()`

**Variables:**
- Use `snake_case` for local variables and parameters
- Use `UPPER_SNAKE_CASE` for module-level constants: `DEFAULT_MAX_RESPONSE_TOKENS`, `EXPORT_DIR`, `MAX_AGENT_ELAPSED_SECONDS`
- Private module-level singletons prefixed with underscore: `_agent_config`, `_active_requests`

**Classes:**
- Use `PascalCase`: `LLMClient`, `ConversationStore`, `JSONFormatter`, `AgentActivityTimer`
- Pydantic models use `PascalCase` with descriptive suffixes: `UnifiedWorkflowRequest`, `UnifiedWorkflowResponse`, `ExportRequest`, `ExportResponse`, `DistillRequest`
- Enums use `PascalCase` with `str, Enum` base: `WorkflowType(str, Enum)`

**Types:**
- Pydantic `BaseModel` subclasses for all API request/response schemas
- Use `typing` module for type hints: `Dict[str, Any]`, `List[str]`, `Optional[str]`
- All function signatures include type annotations (enforced by mypy `disallow_untyped_defs = true`)

## Code Style

**Formatting:**
- **black** (v23.1.0) with 88-character line length
- Target Python 3.10+
- Config in `pyproject.toml` under `[tool.black]`:
  ```toml
  [tool.black]
  line-length = 88
  target-version = ['py310']
  include = '\.pyi?$'
  ```

**Import Sorting:**
- **isort** (v5.12.0) with black-compatible profile
- Config in `pyproject.toml`:
  ```toml
  [tool.isort]
  profile = "black"
  multi_line_output = 3
  line_length = 88
  ```

**Linting:**
- **flake8** (v6.0.0) with max line length 88
- Extended ignores: `E203` (whitespace before ':'), `E221` (multiple spaces before operator), `E231` (missing whitespace after ','), `E713` (test for membership should be 'not in x')
- Config via pre-commit args in `.pre-commit-config.yaml`

**Type Checking:**
- **mypy** (v1.0.1) in strict-ish mode
- Config in `pyproject.toml`:
  ```toml
  [tool.mypy]
  python_version = "3.10"
  warn_return_any = true
  warn_unused_configs = true
  disallow_untyped_defs = true
  ignore_missing_imports = true
  ```
- Excludes `tests/` and `migrations/` directories
- Additional dependency: `types-requests`

## Import Organization

**Order:**
1. Standard library imports (`os`, `json`, `logging`, `asyncio`, `time`, `uuid`)
2. Third-party imports (`fastapi`, `httpx`, `pydantic`, `openai`, `prometheus_client`)
3. Local/project imports (`gateway.utils.*`, `gateway.llm.*`, `gateway.routers.*`)

**Path Style:**
- Absolute imports for cross-module references: `from gateway.llm.client import LLMClient`
- Relative imports within the same package: `from ..utils.logging import get_logger` (seen in `gateway/routers/export.py`)
- Both styles coexist; prefer absolute imports for clarity

**Noqa Comments:**
- Use `# noqa: F401` for imports used indirectly: `import asyncio  # noqa: F401`

## Error Handling

**Patterns:**
- Wrap external service calls (HTTP, LLM, CLI) in `try/except Exception as e` blocks
- Log errors with `logger.error()` or `logger.warning()` before re-raising or returning error responses
- Use `fastapi.HTTPException` for API error responses with appropriate status codes:
  ```python
  raise HTTPException(status_code=status_code, detail=error_msg)
  ```
- Silent fallbacks for non-critical operations (e.g., memory logging failures are logged but don't break the main flow)
- Catch specific exceptions where possible: `except (json.JSONDecodeError, KeyError):`
- Broad `except Exception` as outer catch-all in request handlers

**Error Classification:**
- Use `gateway/utils/metrics.py` `classify_error()` function to categorize errors for metrics
- Record errors via `record_service_error(service_name, exception)` for Prometheus tracking

## Logging

**Framework:** Python standard `logging` module with custom JSON formatter

**Setup:**
- Call `setup_logging()` once at app startup in `gateway/main.py`
- `LOG_LEVEL` env var controls level (default: `INFO`)
- `LOG_FORMAT` env var switches between `text` (default) and `json` structured output

**Logger Creation:**
- Use `get_logger(__name__)` from `gateway/utils/logging.py` OR direct `logging.getLogger(__name__)`
- Both patterns coexist; `get_logger()` is a thin wrapper

**Structured Logging Helpers** (in `gateway/utils/logging.py`):
- `log_request(logger, request_id, method, path, **kwargs)` - HTTP request entry
- `log_response(logger, request_id, status_code, duration_ms, **kwargs)` - HTTP response
- `log_tool_call(logger, request_id, tool_name, arguments)` - Tool invocations
- `log_tool_result(logger, request_id, tool_name, success, duration_ms, result_size)` - Tool results

**Conventions:**
- Always log at service startup/shutdown: `logger.info("Starting Gateway service")`
- Log external integrations on init: `logger.info(f"Claude Bridge configured: {url}")`
- Use f-strings in log messages (not lazy % formatting)
- Suppress noisy third-party loggers: `logging.getLogger("httpx").setLevel(logging.WARNING)`

## Pydantic Model Conventions

**Version:** Pydantic v2.0+

**Request/Response Models:**
- Define inline in router files for endpoint-specific models: `gateway/routers/export.py`, `gateway/routers/agent.py`
- Define in dedicated files for shared models: `gateway/agents/unified_workflow.py`
- Always include `Field(...)` with `description` for API documentation:
  ```python
  class ExportRequest(BaseModel):
      seed_urls: List[str] = Field(..., description="Seed URLs to crawl and export (required)")
      depth: int = Field(1, description="Crawl depth for seed URLs", ge=1, le=5)
  ```
- Use validators (`ge`, `le`) for numeric constraints

**Enum Pattern:**
- Inherit from both `str` and `Enum` for JSON serialization: `class WorkflowType(str, Enum)`
- Use lowercase values: `GENERAL_CHAT = "general_chat"`

**Docstrings on Models:**
- Include usage examples in model docstrings (see `UnifiedWorkflowRequest` in `gateway/agents/unified_workflow.py`)

## Async Patterns

**HTTP Clients:**
- Use `httpx.AsyncClient` for all outbound HTTP calls
- Always specify `timeout` parameter: `httpx.AsyncClient(timeout=30)`
- Use context managers: `async with httpx.AsyncClient(...) as client:`

**FastAPI Endpoints:**
- All route handlers are `async def`
- Use `@asynccontextmanager` for lifespan management in `gateway/main.py`
- Dependency injection via `Depends()` for auth tokens: `Depends(get_bearer_token)`

**Concurrency:**
- `asyncio` for async coordination
- No thread pools or `run_in_executor` patterns observed

## Environment Variable Conventions

**Access Pattern:**
- Always use `os.getenv("VAR_NAME", "default_value")` with sensible defaults
- Cast types explicitly: `int(os.getenv("GATEWAY_PORT", 8000))`
- Boolean checks: `os.getenv("VAR", "false").lower() == "true"`

**Naming:**
- `UPPER_SNAKE_CASE` for all env vars
- Service URLs: `{SERVICE}_URL` pattern (e.g., `CRAWLER_URL`, `INDEXER_URL`, `MEMORY_SERVICE_URL`)
- Service ports: `{SERVICE}_PORT` pattern (e.g., `GATEWAY_PORT`)
- Feature flags: descriptive names (e.g., `MEMORY_AUTO_LOG`, `MEMORY_AUTO_FLUSH`, `JWT_VALIDATION_ENABLED`)
- Secrets/keys: `{PROVIDER}_{TYPE}` (e.g., `AZURE_OPENAI_API_KEY`, `OPENAI_API_KEY`)

**Configuration file:** `deploy/.env` (existence noted, contents not read)

## Module Docstrings

**Pattern:** Every Python module starts with a triple-quoted docstring describing its purpose:
```python
"""
FastAPI Gateway Service - Main orchestrator for the Web RAG system.
Handles chat interactions, tool calling, and coordinates with crawler/indexer services.
"""
```

## Section Headers

**Pattern:** Use comment banners for logical sections within large files:
```python
# =============================================================================
# CRAWL METRICS
# =============================================================================
```

## Singleton Pattern

**Pattern:** Module-level `get_*()` factory functions returning cached instances:
```python
_store: Optional[ConversationStore] = None

def get_conversation_store() -> ConversationStore:
    global _store
    if _store is None:
        _store = ConversationStore()
    return _store
```
Used in: `gateway/utils/conversation_store.py`, `gateway/utils/claude_bridge_manager.py`, `gateway/utils/copilot_bridge_manager.py`, `gateway/utils/file_store.py`

## Comments

**When to Comment:**
- Explain "why" for non-obvious decisions: `# Strip NODE_OPTIONS early -- it can break Node.js-based CLI subprocesses`
- Mark TODO items for known limitations: `# For production, consider using Redis`
- Document env var purposes inline

**JSDoc/TSDoc:** Not applicable (Python project). Use Google-style docstrings with Args/Returns sections for public API functions.

---

*Convention analysis: 2026-03-29*

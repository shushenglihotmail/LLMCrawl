# Testing Patterns

**Analysis Date:** 2026-03-29

## Test Framework

**Runner:**
- pytest >= 7.0.0 (with pytest-asyncio >= 0.21.0 for async tests)
- Config: `pyproject.toml` under `[tool.pytest.ini_options]`

**Assertion Library:**
- Built-in pytest `assert` statements (no additional assertion libraries)

**Mocking:**
- `unittest.mock` (stdlib): `Mock`, `AsyncMock`, `patch`, `patch.dict`

**Run Commands:**
```bash
make test-dev                              # Local pytest with coverage + HTML report
pytest tests/ -v --cov=. --cov-report=html # Equivalent manual command
pytest tests/ -v -k "test_name"            # Single test by name
make test                                  # Run tests inside Docker containers
make test-integration                      # End-to-end integration tests (requires running services)
python tests/integration/test_end_to_end.py # Direct integration test execution
```

## Test File Organization

**Location:** Tests are distributed across four directories (co-located and centralized):

```
tests/
└── integration/
    └── test_end_to_end.py       # Full pipeline integration tests

gateway/tests/
├── test_gateway.py              # Gateway unit tests (prompts, tool handler)
└── test_expand_paths.py         # Manual test script for path expansion (CLI tool, not pytest)

crawler/tests/
└── test_crawler.py              # Crawler unit tests (robots, extraction, firecrawl)

indexer/tests/
└── test_indexer.py              # Indexer unit tests (scoring, chunking, vector stores)
```

**Naming:**
- Test files: `test_<module>.py`
- Test classes: `Test<Component>` (e.g., `TestRobotsChecker`, `TestPrompts`, `TestToolHandler`)
- Test functions: `test_<description>` with snake_case (e.g., `test_robots_checker_init`, `test_tool_schema_structure`)

**Pytest Discovery Config** (from `pyproject.toml`):
```toml
[tool.pytest.ini_options]
minversion = "6.0"
addopts = "-ra -q --strict-markers --cov=. --cov-report=term-missing"
testpaths = ["tests", "gateway/tests", "crawler/tests", "indexer/tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
```

## Test Structure

**Suite Organization:**
```python
class TestToolHandler:
    """Test tool calling functionality."""

    @pytest.fixture
    def tool_handler(self):
        """Create a tool handler instance for testing."""
        with patch("httpx.AsyncClient"):
            return ToolHandler()

    @pytest.mark.asyncio
    async def test_tool_call_structure(self, tool_handler):
        """Test tool call handling structure."""
        # Arrange
        mock_tool_call = {
            "id": "test_call_1",
            "type": "function",
            "function": {
                "name": "crawl_and_refresh",
                "arguments": json.dumps({"query": "test query"}),
            },
        }

        # Act
        with patch.object(tool_handler, "_handle_crawl_and_refresh", new_callable=AsyncMock) as mock_crawl:
            mock_crawl.return_value = {"test": "result"}
            result = await tool_handler.handle_tool_call(mock_tool_call, "test_request_id")

        # Assert
        assert result["tool_call_id"] == "test_call_1"
        assert result["role"] == "tool"
```

**Patterns:**
- Group related tests in classes (`TestRobotsChecker`, `TestRecencyScoring`, `TestDocumentChunking`)
- Use `@pytest.fixture` for test object creation at the class level
- Use `@pytest.mark.asyncio` decorator for all async test methods
- Standalone test functions (outside classes) for simple cases: `test_crawler_health_check()`

## Mocking

**Framework:** `unittest.mock` (stdlib)

**Module-Level Import Mocking:**
Tests mock heavy/unavailable dependencies at module load time to allow tests to run without full service installations:
```python
# Mock the imports that might not be available in test environment
with patch.dict('sys.modules', {
    'openai': Mock(),
    'httpx': Mock(),
    'fastapi': Mock()
}):
    from gateway.llm.prompts import CRAWL_AND_REFRESH_TOOL
```

This pattern is used in:
- `gateway/tests/test_gateway.py` (mocks openai, httpx, fastapi)
- `crawler/tests/test_crawler.py` (mocks httpx, playwright, trafilatura, fastapi)
- `indexer/tests/test_indexer.py` (mocks llama_index, qdrant_client, asyncpg, numpy)

**Method-Level Mocking:**
```python
with patch.object(tool_handler, "_call_crawler", new_callable=AsyncMock) as mock_crawler:
    mock_crawler.return_value = mock_crawl_response
    result = await tool_handler._handle_crawl_and_refresh(arguments, "test_id")
```

**Environment Variable Mocking:**
```python
with patch.dict('os.environ', {'RESPECT_ROBOTS': 'true'}):
    return RobotsChecker()
```

**What to Mock:**
- External HTTP service calls (crawler, indexer, LLM providers)
- Heavy third-party library imports (openai, playwright, llama_index, qdrant_client)
- Environment variables for configuration testing
- Internal methods when testing higher-level orchestration

**What NOT to Mock:**
- Pure logic functions (scoring calculations, text chunking, hash generation)
- Data structures and their validation
- String/URL parsing logic

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture
def robots_checker(self):
    """Create a robots checker for testing."""
    with patch.dict('os.environ', {'RESPECT_ROBOTS': 'true'}):
        return RobotsChecker()

@pytest.fixture
def tool_handler(self):
    """Create a tool handler instance for testing."""
    with patch("httpx.AsyncClient"):
        return ToolHandler()
```

**Inline Test Data:**
Tests construct test data inline rather than using shared fixtures or factory libraries:
```python
sample_docs = [
    {
        "url": "https://example.com/test1",
        "title": "Test Document 1",
        "markdown": "This is a test document about machine learning and AI.",
        "published_at": "2024-01-15T10:00:00Z",
        "metadata": {"source": "test"}
    }
]
```

**Location:** No dedicated fixtures directory. Fixtures are defined within test files.

## Coverage

**Configuration** (from `pyproject.toml`):
```toml
[tool.coverage.run]
source = ["gateway", "crawler", "indexer"]
omit = ["*/tests/*", "*/venv/*", "*/__pycache__/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "if self.debug:",
    "if settings.DEBUG",
    "raise AssertionError",
    "raise NotImplementedError",
    "if 0:",
    "if __name__ == .__main__.:",
]
```

**Requirements:** No minimum coverage threshold enforced. Coverage is reported but not gated.

**View Coverage:**
```bash
pytest tests/ -v --cov=. --cov-report=html   # Generates htmlcov/ directory
pytest tests/ -v --cov=. --cov-report=term-missing  # Terminal output (default via addopts)
```

## Test Types

**Unit Tests:**
- Located in `gateway/tests/`, `crawler/tests/`, `indexer/tests/`
- Test individual components in isolation with mocked dependencies
- Focus on logic correctness (scoring algorithms, data structures, schema validation)
- Many tests verify expected data structures rather than exercising real code paths (assertion on manually constructed dicts)

**Integration Tests:**
- Located in `tests/integration/test_end_to_end.py`
- Require all services to be running (gateway, crawler, indexer)
- Uses a custom `WebRAGIntegrationTest` class (NOT pytest-based; uses `asyncio.run()` with custom reporting)
- Tests: health checks, manual crawling, manual indexing, retrieval, end-to-end chat, general chat
- Run via: `make test-integration` or `python tests/integration/test_end_to_end.py`

**Manual Test Scripts:**
- `gateway/tests/test_expand_paths.py` is a CLI test tool, not a pytest test
- Run directly: `python test_expand_paths.py "gateway/" --gather`
- Tests path expansion and file gathering interactively

**E2E Tests:**
- The integration test in `tests/integration/test_end_to_end.py` serves as the E2E suite
- No browser-based E2E testing framework (Selenium, Playwright for testing, etc.)

## Pre-Commit Hooks

**Config:** `.pre-commit-config.yaml`

**Hooks (in order):**
1. `trailing-whitespace` - Remove trailing whitespace
2. `end-of-file-fixer` - Ensure files end with newline
3. `check-yaml` - Validate YAML syntax
4. `check-added-large-files` - Prevent large file commits
5. `check-merge-conflict` - Detect merge conflict markers
6. `black` (v23.1.0) - Code formatting
7. `isort` (v5.12.0) - Import sorting (black profile)
8. `flake8` (v6.0.0) - Linting (max-line-length=88, extends E203/E221/E231/E713)
9. `mypy` (v1.0.1) - Type checking (excludes tests/ and migrations/)

**Run Manually:**
```bash
make pre-commit          # Run all hooks on all files
pre-commit run --all-files  # Equivalent direct command
```

## CI/CD Pipeline

**Config:** `.github/workflows/build-wheel.yml`

**Triggers:**
- `release: [created]` - On GitHub release creation
- `workflow_dispatch` - Manual trigger

**Jobs:**

1. **build-wheels** (ubuntu-latest, Python 3.12):
   - Builds main LLMCrawl wheel via `python -m build --wheel`
   - Builds all MCP server wheels from `mcp_servers/*/` directories
   - Uploads wheels as GitHub Actions artifact
   - Uploads wheels to GitHub Release (on release events only)

2. **build-memory-service** (ubuntu-latest):
   - Builds Docker image from `services/memory_service/`
   - Pushes to GitHub Container Registry (ghcr.io)
   - Tags with version from release tag or commit SHA

**Notable Gap:** The CI pipeline does NOT run tests or linting. It only builds artifacts. Testing is developer-local only via `make test-dev` and `make pre-commit`.

## Common Patterns

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_can_crawl_allowed(self, robots_checker):
    """Test crawling allowed URLs."""
    with patch.object(robots_checker, '_get_robots_parser', new_callable=AsyncMock) as mock_parser:
        mock_parser.return_value = None
        result = await robots_checker.can_crawl("https://example.com/page")
        assert result is True
```

**Error Testing:**
```python
@pytest.mark.asyncio
async def test_extraction_error_handling(self):
    """Test extraction error handling."""
    expected_result = {"error": "Extraction failed: Invalid HTML"}
    assert "error" in expected_result
```
Note: Error testing is currently lightweight -- tests verify expected error structures rather than triggering actual error paths.

**Context Manager Mocking (multiple patches):**
```python
with (
    patch.object(tool_handler, "_call_crawler", new_callable=AsyncMock) as mock_crawler,
    patch.object(tool_handler, "_call_indexer_index", new_callable=AsyncMock) as mock_indexer,
    patch.object(tool_handler, "_call_indexer_retrieve", new_callable=AsyncMock) as mock_retrieve,
):
    mock_crawler.return_value = mock_crawl_response
    # ...
```

**Standalone Test Execution:**
All test files include a `__main__` guard for direct execution:
```python
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

## Test Quality Notes

**Current State:**
- Test coverage is sparse -- each service has only one test file
- Many tests verify manually constructed expected data structures rather than exercising actual code
- The integration test suite uses a custom runner instead of pytest, so it does not contribute to coverage
- No test database fixtures or service containers (e.g., testcontainers)
- No snapshot testing, property-based testing, or parameterized test patterns
- `gateway/tests/test_expand_paths.py` is a manual CLI tool, not an automated test

**When Writing New Tests:**
- Place unit tests in the corresponding `<service>/tests/` directory
- Follow the class-based grouping pattern: `class Test<Component>`
- Mock heavy imports at module level with `patch.dict('sys.modules', {...})`
- Use `@pytest.mark.asyncio` for any async test function
- Use `AsyncMock` (not `Mock`) for async method patches
- Create fixtures via `@pytest.fixture` methods within test classes

---

*Testing analysis: 2026-03-29*

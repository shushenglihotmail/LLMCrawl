# Code Intelligence Agent

Specialized workflow agent for code operations that reduces LLM calls and costs.

## Three Core Workflows

### 1. UNDERSTAND & DOCUMENT
Analyze files/folders and generate comprehensive documentation.

**Use cases:**
- Explain what a code file or module does
- Generate documentation for a group of files
- Summarize a codebase for onboarding
- Create architectural overview from source files

**Example:**
```python
result = await agent.execute_workflow(
    workflow="understand",
    target_files=[
        "src/onecore/vm/compute/ComputeServiceModule.cpp",
        "src/onecore/vm/compute/ComputeService.h"
    ],
    request="Explain how the Windows Host Compute Service initializes and starts",
    reference_files=["docs/HCS_ARCHITECTURE.md"],
    web_research=True
)
# Returns comprehensive explanation with context from docs and web
```

### 2. INSPECT & ANALYZE
Find bugs, security issues, code smells, and improvement opportunities.

**Use cases:**
- Find potential bugs or logic errors
- Security vulnerability scanning
- Performance issue detection
- Code quality review
- Style and best practice violations

**Example:**
```python
result = await agent.execute_workflow(
    workflow="inspect",
    target_files=["src/api/auth.py"],
    request="Find security vulnerabilities and potential bugs",
    reference_files=["docs/SECURITY_GUIDELINES.md"],
    web_research=True  # Fetch OWASP guidelines, etc.
)
# Returns issues with severity, location, and fixes
```

### 3. GENERATE FROM EXAMPLES
Learn patterns from existing code and generate new files.

**Use cases:**
- Create new files based on existing templates
- Generate boilerplate following project conventions
- Create test files matching existing test patterns
- Generate configuration files from examples

**Example:**
```python
result = await agent.execute_workflow(
    workflow="generate",
    target_files=[],  # No target files for generation
    request="Create a new REST API endpoint for user management",
    reference_files=[
        "gateway/routers/chat.py",  # Example router
        "gateway/routers/tools.py",  # Another example
        "docs/API_PATTERNS.md"      # Style guide
    ],
    web_research=False  # Examples are sufficient
)
# Returns complete new code following patterns
```

## Cost Comparison

| Approach | LLM Calls | Estimated Cost* |
|----------|-----------|-----------------|
| Dynamic tool calling | 5+ rounds | $0.05 per request |
| Code Intelligence Agent | 1-2 calls | $0.01 per request |
| **Savings** | **80% fewer calls** | **80% cost reduction** |

*Estimates based on gpt-4o pricing with typical request sizes

## Architecture Benefits

### Single Round Data Gathering
```
Traditional (5 LLM calls):
Client → LLM: "explain file X"
LLM → Agent: "read file X"
Agent → LLM: "here's file X"
LLM → Agent: "search for HCS docs"
Agent → LLM: "here are docs"
LLM → Agent: "read guide Y"
Agent → LLM: "here's guide Y"
LLM → Client: "explanation"

Code Intelligence Agent (1-2 LLM calls):
Client → Agent: "explain file X with context"
Agent: [reads file X, guide Y, crawls HCS docs] ← No LLM needed
Agent → LLM: "here's everything, explain"
LLM → Client: "explanation"
```

### How It Solves Your Problems

**Problem 1: "How does agent know which pages to crawl?"**
- Solution: Uses cheap planning LLM (gpt-4o-mini) to analyze target files
- Extracts keywords and context from file content
- Plans research based on file type, comments, and structure
- Planning cost: $0.0001 (100x cheaper than main model)

**Problem 2: "How to mix clear text and vectors?"**
- Solution A: Skip vectors, use raw crawled text (simpler)
- Solution B: Use target file as search query → retrieve relevant chunks → combine with files
- Both work! Agent handles the mixing automatically

## Integration

### Gateway Router Integration

```python
# gateway/routers/chat.py

from gateway.agents.file_explanation_agent import CodeIntelligenceAgent

# Detect workflow pattern
if "explain" in query or "document" in query or "summarize" in query:
    workflow = "understand"
elif "find issues" in query or "inspect" in query or "bugs" in query:
    workflow = "inspect"
elif "create" in query or "generate" in query:
    workflow = "generate"
else:
    # Fall back to dynamic tool calling
    return await dynamic_chat_completion(...)

# Extract file paths from query (or from conversation context)
target_files = extract_file_paths(query)
reference_files = extract_reference_files(query)

# Execute agent workflow
agent = CodeIntelligenceAgent(
    mcp_url=os.getenv("MCP_SERVER_URL"),
    crawler_url=os.getenv("CRAWLER_URL"),
    indexer_url=os.getenv("INDEXER_URL"),
    llm_client=llm_client
)

result = await agent.execute_workflow(
    workflow=workflow,
    target_files=target_files,
    request=query,
    reference_files=reference_files
)

return result["result"]
```

### Direct API Endpoint

```python
# gateway/routers/agents.py

@router.post("/agent/code-intelligence")
async def code_intelligence(
    workflow: Literal["understand", "inspect", "generate"],
    target_files: List[str],
    request: str,
    reference_files: Optional[List[str]] = None,
    web_research: bool = True
):
    """Execute code intelligence workflow."""

    agent = CodeIntelligenceAgent(...)

    result = await agent.execute_workflow(
        workflow=workflow,
        target_files=target_files,
        request=request,
        reference_files=reference_files,
        web_research=web_research
    )

    return result
```

## Configuration

Add to `.env`:
```bash
# Code Intelligence Agent
CODE_AGENT_PLANNING_MODEL=gpt-4o-mini  # Cheap model for planning
CODE_AGENT_EXECUTION_MODEL=gpt-4o      # Main model for execution
CODE_AGENT_ENABLE_WEB_RESEARCH=true    # Enable web documentation crawling
```

## Example Use Cases

### 1. Onboarding New Developer
```
Request: "Explain the vmcompute service architecture"
Target files: ["src/onecore/vm/compute/**/*.cpp"]
Reference files: ["docs/VM_ARCHITECTURE.md"]
Web research: true

Result: Comprehensive overview of how vmcompute works, with references to
official Windows docs and internal architecture guides.
```

### 2. Security Review
```
Request: "Find security vulnerabilities in authentication flow"
Target files: ["gateway/auth/*.py"]
Reference files: ["docs/SECURITY_GUIDELINES.md"]
Web research: true (fetches OWASP guidelines)

Result: List of issues with severity ratings and suggested fixes.
```

### 3. Generate New Service
```
Request: "Create a new microservice for file processing"
Target files: [] (none needed for generation)
Reference files: [
    "gateway/main.py",
    "crawler/main.py",
    "docs/SERVICE_TEMPLATE.md"
]
Web research: false

Result: Complete new service with proper structure, error handling,
logging, and API endpoints following project patterns.
```

## Testing

```python
# Test file: tests/test_code_intelligence_agent.py

async def test_understand_workflow():
    agent = CodeIntelligenceAgent(...)

    result = await agent.execute_workflow(
        workflow="understand",
        target_files=["tests/fixtures/sample.py"],
        request="Explain this file",
        reference_files=None,
        web_research=False
    )

    assert result["workflow"] == "understand"
    assert "result" in result
    assert len(result["target_files"]) == 1
```

## Future Enhancements

1. **Caching**: Cache file content and web research results
2. **Streaming**: Stream LLM responses for better UX
3. **Parallel processing**: Read multiple files in parallel
4. **Smart chunking**: For large files, chunk intelligently
5. **Incremental analysis**: Analyze only changed files

# Code Intelligence Agent - Invocation Patterns

## Explicit Invocation Required

To invoke the Code Intelligence Agent, use **explicit, clear commands** with:

1. **Trigger words**: `run`, `call`, `invoke`, `execute`, `use`, `perform`
2. **Agent/workflow name**: `code analysis`, `code intelligence`, `workflow`, `agent`
3. **File pattern**: File extensions and/or directories
4. **Optional**: Workflow type, reference files, web research preference

## Supported Invocation Patterns

### Pattern 1: Extension + Directory

```
run code analysis workflow on *.cpp files under /src/compute/
invoke code intelligence agent on files suffixed with .json in /config/
call code analysis on .man files under /docs/
execute workflow on *.py files under /gateway/
```

**Parsed as:**
- Workflow: Auto-detected from additional context
- Target files: All `*.cpp` files in `/src/compute/`
- Directory: `/src/compute/`

### Pattern 2: Full File Paths

```
run code analysis on /src/auth/handler.cpp
invoke inspect agent on /config/settings.json, /config/database.json
call understand workflow for /docs/ARCHITECTURE.md
```

**Parsed as:**
- Workflow: Auto-detected
- Target files: Specific files listed
- No directory scanning needed

### Pattern 3: Extension Without Directory (Workspace-wide)

```
run code analysis on files suffixed with .json
invoke agent on *.cpp files
call workflow for .xml files
```

**Parsed as:**
- Workflow: Auto-detected
- Target files: All matching files in workspace root
- Scans entire workspace

### Pattern 4: With Explicit Workflow Type

```
run UNDERSTAND workflow on *.cpp files under /src/
invoke INSPECT agent on .json files in /config/ to find schema issues
call GENERATE workflow with template files *.xml under /templates/
```

**Workflow keywords:**
- `UNDERSTAND`: explain, document, summarize, describe, what does, how does
- `INSPECT`: inspect, find issues, find bugs, check for, review, audit, security
- `GENERATE`: generate, create, build, make, write, produce, based on

### Pattern 5: With Reference Files

```
run code analysis on *.cpp under /src/ with reference files /docs/GUIDE.md, /docs/PATTERNS.md
invoke generate agent with template /templates/service.xml to create new service
call understand workflow for *.py files using guide /docs/ARCHITECTURE.md
```

**Reference file patterns:**
- `with reference files <paths>`
- `with template <path>`
- `with guide <path>`
- `based on <paths>`
- `using example <paths>`

### Pattern 6: With Web Research Control

```
run code analysis on *.cpp under /src/ with web research
invoke agent on *.json files without web research
call workflow for *.py files with no web
execute inspect agent on /auth/ skip web
```

**Web research keywords:**
- **Enable**: `with web`, `include web`, `search web`, `fetch docs`
- **Disable**: `no web`, `without web`, `skip web`, `local only`
- **Default**: Enabled for understand/inspect, disabled for generate

## Complete Examples

### Example 1: Understand Windows Service Code

```
run code analysis workflow on *.cpp files under /src/onecore/vm/compute/dll/
and explain how the service initializes with reference files
/src/onecore/vm/compute/dll/README.md
```

**Parsed:**
- Workflow: `understand`
- Target files: All `.cpp` in `/src/onecore/vm/compute/dll/`
- Request: "explain how the service initializes"
- Reference files: `['/src/onecore/vm/compute/dll/README.md']`
- Web research: `true` (default for understand)

**Result:** Comprehensive explanation of service initialization

---

### Example 2: Find Security Issues in Config Files

```
invoke INSPECT agent on files suffixed with .json in /config/
to find security vulnerabilities and misconfigurations
```

**Parsed:**
- Workflow: `inspect`
- Target files: All `.json` in `/config/`
- Request: "find security vulnerabilities and misconfigurations"
- Reference files: `[]`
- Web research: `true` (default for inspect)

**Result:** Structured list of issues with severity and fixes

---

### Example 3: Generate New Service from Template

```
call GENERATE workflow with template files /templates/service_template.cpp,
/templates/service_template.h to create a file processing service
without web research
```

**Parsed:**
- Workflow: `generate`
- Target files: `[]` (not needed for generation)
- Request: "create a file processing service"
- Reference files: `['/templates/service_template.cpp', '/templates/service_template.h']`
- Web research: `false` (explicitly disabled)

**Result:** Complete new service code following template patterns

---

### Example 4: Review Python Gateway Code

```
run code analysis on *.py files under /gateway/ to find bugs,
performance issues, and code smells with reference to
/docs/CODING_STANDARDS.md
```

**Parsed:**
- Workflow: `inspect` (from "find bugs")
- Target files: All `.py` in `/gateway/`
- Request: "find bugs, performance issues, and code smells"
- Reference files: `['/docs/CODING_STANDARDS.md']`
- Web research: `true` (default)

**Result:** Code review with issues categorized by type

---

### Example 5: Document Multiple Configuration Files

```
invoke understand workflow on files suffixed with .man under /docs/config/
and summarize the configuration options
```

**Parsed:**
- Workflow: `understand`
- Target files: All `.man` in `/docs/config/`
- Request: "summarize the configuration options"
- Reference files: `[]`
- Web research: `true`

**Result:** Comprehensive configuration documentation

---

## What Triggers the Agent?

### ✅ WILL Trigger Agent

```
run code analysis workflow on *.cpp files under /src/
invoke code intelligence agent on .json files
call code analysis on /config/settings.json
execute workflow on files suffixed with .py
use code intelligence on *.xml under /templates/
perform code analysis on /auth/handler.cpp
do code inspection on *.cpp files
```

### ❌ Will NOT Trigger Agent (Uses Dynamic Tool Calling Instead)

```
explain the file /src/compute/service.cpp
→ Missing explicit invocation trigger

find bugs in /config/settings.json
→ Missing "code analysis/workflow/agent" keywords

what do these .cpp files do?
→ Missing explicit invocation pattern

can you analyze /src/auth/ for issues?
→ Too conversational, not explicit enough

read *.json files and check for errors
→ No "workflow" or "agent" keyword
```

## Pattern Matching Rules

The detector looks for:

1. **Invocation trigger** (required):
   - `run/call/invoke/execute/start/use/apply/do/perform`
   - Followed by: `code analysis/intelligence` OR `workflow` OR `agent`

2. **File pattern** (required):
   - `*.ext files`
   - `files suffixed with .ext`
   - `/path/to/file.ext`
   - `/path/to/*.ext`

3. **Directory** (optional):
   - `under /path/`
   - `in /path/`
   - `at /path/`
   - `from /path/`

4. **Workflow type** (optional, auto-detected if missing):
   - Explicit: `UNDERSTAND/INSPECT/GENERATE workflow`
   - Implicit: Detected from keywords in request

5. **Reference files** (optional):
   - `with reference files <paths>`
   - `with template <path>`
   - `based on <paths>`

6. **Web research** (optional):
   - `with web` / `without web`
   - Auto-enabled for understand/inspect
   - Auto-disabled for generate

## Integration with Gateway

```python
# gateway/routers/chat.py

from gateway.agents.workflow_detector import WorkflowDetector
from gateway.agents import CodeIntelligenceAgent

# Initialize detector
detector = WorkflowDetector(mcp_url=os.getenv("MCP_SERVER_URL"))

# In chat endpoint
async def chat(query: str):
    # Try to detect explicit agent invocation
    workflow_request = detector.detect_workflow_invocation(query)

    if workflow_request:
        logger.info(f"Using Code Intelligence Agent: {workflow_request.workflow}")

        agent = CodeIntelligenceAgent(
            mcp_url=os.getenv("MCP_SERVER_URL"),
            crawler_url=os.getenv("CRAWLER_URL"),
            indexer_url=os.getenv("INDEXER_URL"),
            llm_client=llm_client
        )

        result = await agent.execute_workflow(
            workflow=workflow_request.workflow,
            target_files=workflow_request.target_files,
            request=workflow_request.request,
            reference_files=workflow_request.reference_files,
            web_research=workflow_request.web_research
        )

        return result["result"]

    else:
        # Fall back to dynamic tool calling
        return await dynamic_chat_completion(query)
```

## Testing

Use the test file with explicit invocations:

```bash
# Test explicit invocations
cat test-code-intelligence-explicit.txt

# Via HiChat console
.\bin\hichat-console.exe

# Try:
> run code analysis workflow on *.cpp files under /src/onecore/vm/compute/dll/
> invoke inspect agent on files suffixed with .json in /config/
> call generate workflow with template /templates/service.xml
```

## Benefits of Explicit Invocation

1. **No Ambiguity**: User intent is 100% clear
2. **Cost Predictable**: Always uses agent (1-2 LLM calls)
3. **No False Positives**: Won't accidentally trigger on general questions
4. **User Control**: Explicit choice between agent vs dynamic mode
5. **Better UX**: Clear mental model of when to use agent vs chat

## Summary

**Simple Rule:**
```
run/invoke/call/execute + code analysis/workflow/agent + file pattern = Agent Mode
Anything else = Dynamic Tool Calling Mode
```

This gives users **full control** over when to use the efficient agent workflow vs the flexible dynamic approach.

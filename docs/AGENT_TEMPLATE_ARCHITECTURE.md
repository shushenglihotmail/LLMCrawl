# Code Intelligence Agent - Complete Architecture

## Problem: Too Many Parameters for Prompt-Based Invocation

**Your original concern:**
> "Since too many parameters, I don't put them in prompt since it could be unclear"

**Solution:** Template-based API with structured parameters

---

## Three Required Parameters

All workflows need exactly **3 parameters**:

### 1. target_files (Required)
```json
{
  "target_files": [
    "/data/files/src/onecore/vm/compute/dll/ComputeServiceModule.cpp",
    "/data/files/src/onecore/vm/compute/dll/ComputeService.h"
  ]
}
```
- **Purpose:** Files to analyze/inspect/generate from
- **Type:** List of file paths
- **Can be:** Specific paths or wildcards (`/src/**/*.cpp`)
- **Note:** Can be empty for `generate` workflow

### 2. web_crawl_urls (Optional)
```json
{
  "web_crawl_urls": [
    "https://docs.microsoft.com/en-us/virtualization/windowscontainers/",
    "https://docs.microsoft.com/en-us/windows/win32/services/"
  ]
}
```
- **Purpose:** Websites to crawl for additional context
- **Type:** List of URLs
- **If provided:** Agent crawls these specific URLs
- **If null/empty:** Agent skips web crawling
- **Note:** Usually enabled for understand/inspect, disabled for generate

### 3. educational_files (Optional)
```json
{
  "educational_files": [
    "/docs/HCS_ARCHITECTURE.md",
    "/docs/CODING_PATTERNS.md",
    "/docs/SECURITY_CHECKLIST.md"
  ]
}
```
- **Purpose:** Instruction files with analysis tips, templates, guides
- **Type:** List of file paths
- **Contains:** Clear text with instructions or educational content
- **If provided:** Agent includes these in context
- **If null/empty:** Agent uses only target files

---

## API Architecture

### Endpoint 1: Discover Templates
```http
GET /agent/templates
```

**Returns:** All available workflow templates with parameter schemas

```json
{
  "templates": {
    "understand": {
      "name": "Understand & Document",
      "description": "Analyze files and generate documentation",
      "parameters": {...}
    },
    "inspect": {...},
    "generate": {...}
  },
  "count": 3
}
```

**Use case:** Client discovers available workflows and their parameters

---

### Endpoint 2: Get Specific Template
```http
GET /agent/templates/{workflow}
```

**Example:** `GET /agent/templates/understand`

**Returns:** Template definition with parameter schema and example

```json
{
  "name": "Understand & Document",
  "description": "Analyze files and generate comprehensive documentation",
  "workflow": "understand",
  "parameters": {
    "target_files": {
      "type": "array",
      "required": true,
      "description": "Files to analyze",
      "example": ["/src/compute/*.cpp"]
    },
    "educational_files": {
      "type": "array",
      "required": false,
      "description": "Instruction files",
      "example": ["/docs/GUIDE.md"]
    },
    "web_crawl_urls": {
      "type": "array",
      "required": false,
      "description": "URLs to crawl",
      "example": ["https://docs.microsoft.com/..."]
    }
  },
  "example": {
    "workflow": "understand",
    "target_files": [...],
    "request": "...",
    "educational_files": [...],
    "web_crawl_urls": [...]
  }
}
```

**Use case:** Client retrieves template to build UI form or CLI prompts

---

### Endpoint 3: Execute Workflow
```http
POST /agent/execute
Content-Type: application/json
```

**Request body (filled template):**
```json
{
  "workflow": "understand",
  "target_files": [
    "/data/files/src/onecore/vm/compute/dll/ComputeServiceModule.cpp"
  ],
  "request": "Explain how the vmcompute service initializes",
  "educational_files": [
    "/data/files/docs/HCS_ARCHITECTURE.md"
  ],
  "web_crawl_urls": [
    "https://docs.microsoft.com/virtualization/"
  ]
}
```

**Response:**
```json
{
  "workflow": "understand",
  "result": "# VMCompute Service Initialization\n\n...",
  "target_files": [...],
  "sources": [...],
  "context_used": {
    "target_files_count": 1,
    "reference_files_count": 1,
    "web_sources_count": 3
  }
}
```

**Use case:** Client executes workflow with filled parameters

---

## Client Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ Client Application                                          │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────┐
        │ 1. GET /agent/templates                  │
        │    → Discover available workflows        │
        └──────────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────┐
        │ 2. GET /agent/templates/understand       │
        │    → Get parameter schema                │
        └──────────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────┐
        │ 3. Build UI Form or CLI Prompts          │
        │    - Target files: [text area]           │
        │    - Request: [text input]               │
        │    - Educational files: [text area]      │
        │    - Web URLs: [text area]               │
        └──────────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────┐
        │ 4. User Fills Template                   │
        │    target_files: [/src/compute/*.cpp]    │
        │    educational_files: [/docs/GUIDE.md]   │
        │    web_crawl_urls: [https://...]         │
        └──────────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────┐
        │ 5. POST /agent/execute                   │
        │    → Send filled template                │
        └──────────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────┐
        │ 6. Receive Result                        │
        │    → Display to user                     │
        └──────────────────────────────────────────┘
```

---

## Implementation Files

### 1. Templates Definition
**File:** `gateway/agents/templates.py`
- Defines Pydantic models for 3 workflows
- `UnderstandWorkflowRequest`
- `InspectWorkflowRequest`
- `GenerateWorkflowRequest`
- Provides template metadata via `get_all_templates()`, `get_template()`

### 2. API Router
**File:** `gateway/routers/agent.py`
- `GET /agent/templates` - List all templates
- `GET /agent/templates/{workflow}` - Get specific template
- `POST /agent/execute` - Execute with filled template
- `GET /agent/health` - Health check

### 3. Agent Implementation
**File:** `gateway/agents/file_explanation_agent.py`
- `CodeIntelligenceAgent` class
- `execute_workflow()` method handles all 3 parameters
- Orchestrates data gathering without multiple LLM rounds

### 4. Documentation
**Files:**
- `docs/AGENT_CLIENT_USAGE.md` - Complete client usage guide
- `docs/AGENT_INVOCATION_PATTERNS.md` - Prompt-based patterns (alternative)
- `docs/CODE_INTELLIGENCE_AGENT.md` - Architecture overview
- `test-agent-templates.txt` - PowerShell test examples

---

## Example Usage Scenarios

### Scenario 1: All 3 Parameters
```json
{
  "workflow": "understand",
  "target_files": ["/src/compute/service.cpp"],
  "request": "Explain initialization",
  "educational_files": ["/docs/ARCHITECTURE.md"],
  "web_crawl_urls": ["https://docs.microsoft.com/..."]
}
```
**Agent behavior:**
1. Reads `/src/compute/service.cpp`
2. Reads `/docs/ARCHITECTURE.md`
3. Crawls Microsoft docs
4. Combines all context → Single LLM call

---

### Scenario 2: Target + Educational Only (No Web)
```json
{
  "workflow": "inspect",
  "target_files": ["/src/auth/handler.cpp"],
  "request": "Find security issues",
  "educational_files": ["/docs/SECURITY_CHECKLIST.md"],
  "web_crawl_urls": null
}
```
**Agent behavior:**
1. Reads `/src/auth/handler.cpp`
2. Reads `/docs/SECURITY_CHECKLIST.md`
3. Skips web crawling
4. Combines files → Single LLM call

---

### Scenario 3: Target + Web Only (No Educational)
```json
{
  "workflow": "understand",
  "target_files": ["/src/config/parser.cpp"],
  "request": "Explain configuration parsing",
  "educational_files": [],
  "web_crawl_urls": ["https://json.org/", "https://yaml.org/"]
}
```
**Agent behavior:**
1. Reads `/src/config/parser.cpp`
2. Skips educational files
3. Crawls JSON/YAML specs
4. Combines file + web → Single LLM call

---

### Scenario 4: Minimal (Only Target File)
```json
{
  "workflow": "understand",
  "target_files": ["/src/utils/helper.cpp"],
  "request": "Explain this utility",
  "educational_files": [],
  "web_crawl_urls": []
}
```
**Agent behavior:**
1. Reads `/src/utils/helper.cpp`
2. Skips everything else
3. Sends only file → Single LLM call

---

## Benefits of Template Approach

| Aspect | Prompt-Based | Template-Based ✅ |
|--------|--------------|-------------------|
| **Parameter clarity** | Hidden in prose | Explicit fields |
| **Validation** | Manual parsing | Pydantic automatic |
| **Discoverability** | Documentation | GET /templates |
| **UI integration** | Complex parsing | Direct JSON mapping |
| **Type safety** | Runtime errors | Compile-time checks |
| **Client complexity** | Parse prompt structure | Fill JSON template |
| **Error handling** | Ambiguous failures | Clear validation errors |
| **Documentation** | Scattered | Self-documenting API |

---

## Migration Path

### Phase 1: Template API Only (Recommended)
```python
# gateway/main.py
from gateway.routers import agent

app.include_router(agent.router)
```

**Clients use:**
```bash
GET /agent/templates/understand
POST /agent/execute
```

### Phase 2: Add Prompt Detection (Optional)
```python
# gateway/routers/chat.py
from gateway.agents import WorkflowDetector

detector = WorkflowDetector(mcp_url=...)

# In chat endpoint:
workflow_request = detector.detect_workflow_invocation(query)
if workflow_request:
    # Use agent
else:
    # Use dynamic tool calling
```

**Clients can use:**
- Template API (explicit, structured)
- OR prompt-based: "run code analysis on *.cpp files under /src/"

---

## Cost Comparison

### Traditional Dynamic Tool Calling
```
Query: "Explain vmcompute service"
Round 1: LLM → read_file(service.cpp)
Round 2: LLM → search_web("vmcompute")
Round 3: LLM → read_file(docs.md)
Round 4: LLM → crawl(ms-docs)
Round 5: LLM → explain
Total: 5 LLM calls = $0.05
```

### Template-Based Agent
```
POST /agent/execute {
  target_files: [service.cpp],
  educational_files: [docs.md],
  web_crawl_urls: [ms-docs]
}
Agent: [reads all, crawls web] (NO LLM)
Agent → LLM: "Here's everything, explain"
Total: 1 LLM call = $0.01
Savings: 80%
```

---

## Testing

```powershell
# 1. List templates
Invoke-RestMethod http://localhost:8000/agent/templates

# 2. Get template
Invoke-RestMethod http://localhost:8000/agent/templates/understand

# 3. Execute workflow
$request = @{
    workflow = "understand"
    target_files = @("/src/file.cpp")
    request = "Explain this"
    educational_files = @("/docs/guide.md")
    web_crawl_urls = @("https://docs.example.com/")
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri http://localhost:8000/agent/execute `
    -Method POST `
    -Body $request `
    -ContentType "application/json"
```

---

## Summary

**Problem:** Too many parameters to express clearly in prompts

**Solution:** Template-based API with exactly 3 parameters:

1. ✅ **target_files** (required) - What to analyze
2. ✅ **web_crawl_urls** (optional) - External context
3. ✅ **educational_files** (optional) - Internal guides/tips

**Client workflow:**
1. Query available templates
2. Get parameter schema
3. Fill template
4. Execute workflow
5. Receive structured result

**Benefits:**
- Clear parameter structure
- Self-documenting API
- Easy UI/CLI integration
- Type-safe validation
- 80% cost savings vs dynamic tool calling

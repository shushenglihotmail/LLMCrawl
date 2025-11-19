# Code Intelligence Agent - Client Usage Guide

## Architecture: Template-Based Invocation

Instead of complex prompts, clients use structured templates with 3 parameters:
1. **target_files** (required) - Files to analyze
2. **web_crawl_urls** (optional) - Websites to crawl for context
3. **educational_files** (optional) - Instruction files with analysis tips

## API Endpoints

### 1. List Available Templates
```http
GET /agent/templates
```

**Response:**
```json
{
  "templates": {
    "understand": {...},
    "inspect": {...},
    "generate": {...}
  },
  "count": 3
}
```

### 2. Get Specific Template
```http
GET /agent/templates/understand
```

**Response:**
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
  "example": {...}
}
```

### 3. Execute Workflow
```http
POST /agent/execute
Content-Type: application/json
```

**Request Body (filled template):**
```json
{
  "workflow": "understand",
  "target_files": [
    "/data/files/src/onecore/vm/compute/dll/ComputeServiceModule.cpp",
    "/data/files/src/onecore/vm/compute/dll/ComputeService.h"
  ],
  "request": "Explain how the vmcompute service initializes",
  "educational_files": [
    "/data/files/docs/HCS_ARCHITECTURE.md"
  ],
  "web_crawl_urls": [
    "https://docs.microsoft.com/en-us/virtualization/windowscontainers/"
  ]
}
```

**Response:**
```json
{
  "workflow": "understand",
  "result": "# VMCompute Service Initialization\n\nThe service initializes through...",
  "target_files": [
    "/data/files/src/onecore/vm/compute/dll/ComputeServiceModule.cpp",
    "/data/files/src/onecore/vm/compute/dll/ComputeService.h"
  ],
  "sources": [
    {"url": "https://docs.microsoft.com/...", "title": "Windows Containers"}
  ],
  "context_used": {
    "target_files_count": 2,
    "reference_files_count": 1,
    "web_sources_count": 3
  }
}
```

## Client Examples

### PowerShell Client

```powershell
# 1. Get available templates
$templates = Invoke-RestMethod -Uri "http://localhost:8000/agent/templates"
$templates.templates.Keys  # Shows: understand, inspect, generate

# 2. Get understand template
$template = Invoke-RestMethod -Uri "http://localhost:8000/agent/templates/understand"
Write-Host $template.description

# 3. Fill template and execute
$request = @{
    workflow = "understand"
    target_files = @(
        "/data/files/src/onecore/vm/compute/dll/ComputeServiceModule.cpp"
    )
    request = "Explain service initialization"
    educational_files = @("/data/files/docs/HCS_GUIDE.md")
    web_crawl_urls = @("https://docs.microsoft.com/virtualization/")
} | ConvertTo-Json

$result = Invoke-RestMethod `
    -Uri "http://localhost:8000/agent/execute" `
    -Method POST `
    -Body $request `
    -ContentType "application/json"

Write-Host $result.result
```

### Python Client

```python
import requests

BASE_URL = "http://localhost:8000"

# 1. List templates
response = requests.get(f"{BASE_URL}/agent/templates")
templates = response.json()
print(f"Available workflows: {list(templates['templates'].keys())}")

# 2. Get template for inspection workflow
response = requests.get(f"{BASE_URL}/agent/templates/inspect")
template = response.json()
print(f"Template: {template['name']}")
print(f"Description: {template['description']}")

# 3. Fill and execute template
request_data = {
    "workflow": "inspect",
    "target_files": ["/src/auth/handler.cpp"],
    "request": "Find security vulnerabilities and memory leaks",
    "educational_files": ["/docs/SECURITY_CHECKLIST.md"],
    "web_crawl_urls": ["https://owasp.org/www-project-top-ten/"]
}

response = requests.post(
    f"{BASE_URL}/agent/execute",
    json=request_data
)

result = response.json()
print(f"Workflow: {result['workflow']}")
print(f"Result:\n{result['result']}")
print(f"Context used: {result['context_used']}")
```

### JavaScript/TypeScript Client

```typescript
const BASE_URL = "http://localhost:8000";

// 1. Get all templates
async function listTemplates() {
  const response = await fetch(`${BASE_URL}/agent/templates`);
  const data = await response.json();
  return data.templates;
}

// 2. Get specific template
async function getTemplate(workflow: string) {
  const response = await fetch(`${BASE_URL}/agent/templates/${workflow}`);
  return await response.json();
}

// 3. Execute workflow
async function executeWorkflow(workflowData: any) {
  const response = await fetch(`${BASE_URL}/agent/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(workflowData)
  });
  return await response.json();
}

// Example usage
const templates = await listTemplates();
console.log("Available:", Object.keys(templates));

const request = {
  workflow: "generate",
  target_files: [],
  request: "Create a new REST API endpoint for user management",
  educational_files: [
    "/templates/api_endpoint.py",
    "/docs/CODING_STANDARDS.md"
  ],
  web_crawl_urls: null  // Don't crawl web for generation
};

const result = await executeWorkflow(request);
console.log(result.result);
```

## UI Integration Examples

### Web Form (React)

```jsx
import React, { useState, useEffect } from 'react';

function CodeAnalysisForm() {
  const [templates, setTemplates] = useState({});
  const [selectedWorkflow, setSelectedWorkflow] = useState('understand');
  const [formData, setFormData] = useState({
    target_files: [],
    request: '',
    educational_files: [],
    web_crawl_urls: []
  });
  const [result, setResult] = useState(null);

  // Load templates on mount
  useEffect(() => {
    fetch('/agent/templates')
      .then(r => r.json())
      .then(data => setTemplates(data.templates));
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();

    const response = await fetch('/agent/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workflow: selectedWorkflow,
        ...formData
      })
    });

    const data = await response.json();
    setResult(data);
  };

  return (
    <form onSubmit={handleSubmit}>
      {/* Workflow selector */}
      <select
        value={selectedWorkflow}
        onChange={e => setSelectedWorkflow(e.target.value)}
      >
        {Object.keys(templates).map(wf => (
          <option key={wf} value={wf}>
            {templates[wf]?.name}
          </option>
        ))}
      </select>

      {/* Target files (required) */}
      <label>Target Files *</label>
      <textarea
        placeholder="One file path per line"
        value={formData.target_files.join('\n')}
        onChange={e => setFormData({
          ...formData,
          target_files: e.target.value.split('\n').filter(Boolean)
        })}
        required
      />

      {/* Request (required) */}
      <label>What to Analyze *</label>
      <input
        type="text"
        placeholder="e.g., Explain service initialization"
        value={formData.request}
        onChange={e => setFormData({...formData, request: e.target.value})}
        required
      />

      {/* Educational files (optional) */}
      <label>Educational Files (optional)</label>
      <textarea
        placeholder="One file path per line"
        value={formData.educational_files.join('\n')}
        onChange={e => setFormData({
          ...formData,
          educational_files: e.target.value.split('\n').filter(Boolean)
        })}
      />

      {/* Web crawl URLs (optional) */}
      <label>Web URLs to Crawl (optional)</label>
      <textarea
        placeholder="One URL per line"
        value={formData.web_crawl_urls.join('\n')}
        onChange={e => setFormData({
          ...formData,
          web_crawl_urls: e.target.value.split('\n').filter(Boolean)
        })}
      />

      <button type="submit">Execute Workflow</button>

      {/* Results */}
      {result && (
        <div className="result">
          <h3>Result</h3>
          <pre>{result.result}</pre>
          <p>Context used: {JSON.stringify(result.context_used)}</p>
        </div>
      )}
    </form>
  );
}
```

### CLI Tool (Python)

```python
#!/usr/bin/env python3
"""
Code Intelligence Agent CLI

Usage:
  agent-cli list-workflows
  agent-cli get-template <workflow>
  agent-cli execute <template.json>
"""

import json
import sys
import requests

BASE_URL = "http://localhost:8000"

def list_workflows():
    """List available workflows."""
    response = requests.get(f"{BASE_URL}/agent/templates")
    templates = response.json()["templates"]

    print("Available workflows:\n")
    for name, template in templates.items():
        print(f"  {name:<12} - {template['description']}")
    print("\nUse 'agent-cli get-template <workflow>' for details")

def get_template(workflow):
    """Get template for workflow."""
    response = requests.get(f"{BASE_URL}/agent/templates/{workflow}")
    if response.status_code == 404:
        print(f"Error: Workflow '{workflow}' not found")
        sys.exit(1)

    template = response.json()
    print(f"\nTemplate: {template['name']}")
    print(f"Description: {template['description']}\n")
    print("Example:")
    print(json.dumps(template["example"], indent=2))

    # Save example to file
    filename = f"template_{workflow}.json"
    with open(filename, "w") as f:
        json.dump(template["example"], f, indent=2)
    print(f"\nExample saved to: {filename}")
    print("Edit this file and run: agent-cli execute template_{workflow}.json")

def execute(template_file):
    """Execute workflow from filled template file."""
    with open(template_file) as f:
        request_data = json.load(f)

    print(f"Executing {request_data['workflow']} workflow...")
    print(f"Target files: {len(request_data['target_files'])}")

    response = requests.post(
        f"{BASE_URL}/agent/execute",
        json=request_data
    )

    if response.status_code != 200:
        print(f"Error: {response.text}")
        sys.exit(1)

    result = response.json()
    print(f"\n=== Result ===\n")
    print(result["result"])
    print(f"\n=== Context Used ===")
    print(json.dumps(result["context_used"], indent=2))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "list-workflows":
        list_workflows()
    elif command == "get-template" and len(sys.argv) == 3:
        get_template(sys.argv[2])
    elif command == "execute" and len(sys.argv) == 3:
        execute(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(1)
```

## Complete Workflow Examples

### Example 1: Understand VMCompute Service

```bash
# 1. Get template
curl http://localhost:8000/agent/templates/understand > template.json

# 2. Edit template.json
cat > request.json << 'EOF'
{
  "workflow": "understand",
  "target_files": [
    "/data/files/src/onecore/vm/compute/dll/ComputeServiceModule.cpp",
    "/data/files/src/onecore/vm/compute/dll/ComputeService.h"
  ],
  "request": "Explain how the vmcompute service initializes and exposes COM interfaces",
  "educational_files": [
    "/data/files/docs/HCS_ARCHITECTURE.md"
  ],
  "web_crawl_urls": [
    "https://docs.microsoft.com/en-us/virtualization/windowscontainers/"
  ]
}
EOF

# 3. Execute
curl -X POST http://localhost:8000/agent/execute \
  -H "Content-Type: application/json" \
  -d @request.json
```

### Example 2: Inspect for Security Issues

```json
{
  "workflow": "inspect",
  "target_files": [
    "/src/auth/authentication.cpp",
    "/src/auth/authorization.cpp"
  ],
  "request": "Find security vulnerabilities including: SQL injection, buffer overflows, race conditions, authentication bypass",
  "educational_files": [
    "/docs/SECURITY_GUIDELINES.md",
    "/docs/SECURE_CODING_CHECKLIST.md"
  ],
  "web_crawl_urls": [
    "https://owasp.org/www-project-top-ten/",
    "https://cwe.mitre.org/data/definitions/119.html"
  ]
}
```

### Example 3: Generate New Service

```json
{
  "workflow": "generate",
  "target_files": [],
  "request": "Create a new Windows service called FileMonitorService that monitors a directory for file changes and logs events. Include proper service lifecycle, COM interface, and error handling.",
  "educational_files": [
    "/data/files/src/onecore/vm/compute/dll/ComputeServiceModule.cpp",
    "/data/files/src/onecore/vm/compute/dll/ComputeServiceModule.h",
    "/docs/SERVICE_TEMPLATE.md",
    "/docs/CODING_STANDARDS.md"
  ],
  "web_crawl_urls": null
}
```

## Benefits of Template Approach

| Aspect | Prompt-Based | Template-Based |
|--------|--------------|----------------|
| **Clarity** | Ambiguous parsing | Structured parameters |
| **Validation** | Manual checking | Pydantic validation |
| **UI Integration** | Complex form parsing | Direct JSON mapping |
| **Discoverability** | Hidden parameters | Explicit parameter list |
| **Type Safety** | Runtime errors | Compile-time checks |
| **Documentation** | Scattered in docs | Self-documenting API |

## Testing

```powershell
# Test template listing
Invoke-RestMethod http://localhost:8000/agent/templates

# Test template retrieval
Invoke-RestMethod http://localhost:8000/agent/templates/understand

# Test execution
$request = @{
    workflow = "understand"
    target_files = @("/data/files/src/onecore/vm/compute/dll/ComputeServiceModule.cpp")
    request = "Explain initialization"
    educational_files = @()
    web_crawl_urls = @()
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri http://localhost:8000/agent/execute `
    -Method POST `
    -Body $request `
    -ContentType "application/json"
```

## Summary

**Template-based approach provides:**
- ✅ Clear 3-parameter structure (target_files, web_crawl_urls, educational_files)
- ✅ Self-documenting API (GET /templates)
- ✅ Easy UI/CLI integration
- ✅ Type-safe validation
- ✅ Discoverability (clients query available workflows)
- ✅ Clean separation: client fills template → server executes workflow

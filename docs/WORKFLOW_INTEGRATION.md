# Workflow Integration Guide

This document describes the workflow system implemented in LLMCrawl and how to integrate it with clients like HiChat.

## Workflow Types

The system supports four workflow types defined in `gateway/agents/unified_workflow.py`:

### 1. GENERAL_CHAT (`"general_chat"`)
**System Role**: Informational Consultant - friendly, conversational assistant

**Use Cases**:
- General questions and casual conversation
- Information lookup
- Explanations and recommendations

**Client UI Restrictions**:
- Target Files: **Disabled** (hidden or greyed out)
- Reference Files: **Disabled** (hidden or greyed out)
- Azure DevOps in Expose to LLM: **Disabled** (always false)

**Available Options**:
- Local MCP: Can be enabled
- Crawler: Can be enabled
- Seed URLs: Can be used

### 2. CODE_ANALYSIS (`"code_analysis"`)
**System Role**: Technical Architect - deep code analysis, review, and refactoring

**Use Cases**:
- Code review
- Code refactoring
- Architecture analysis
- Bug hunting
- Performance analysis

**Client UI**:
- **All options available**
- Target Files: Enabled
- Reference Files: Enabled
- All Expose to LLM options: Available

### 3. BUILD_SYSTEM_ANALYSIS (`"build_system_analysis"`)
**System Role**: Technical Architect & Build Engineer - metadata, manifest, and build system expert

**Use Cases**:
- Build system troubleshooting
- Dependency analysis
- Configuration management
- CI/CD pipeline analysis
- Package management

**Client UI**:
- **All options available**
- Target Files: Enabled
- Reference Files: Enabled
- All Expose to LLM options: Available

### 4. FILE_EXPLORER (`"file_explorer"`)
**System Role**: DevOps Engineer & File System Assistant - browsing and searching files

**Use Cases**:
- Browse repositories and local file systems
- Search files by name patterns (wildcards: `*.cpp`, `test_*.py`)
- Search files by content keywords
- Explore folder structures
- Find files matching specific criteria

**Client UI**:
- **All options available**
- Target Files: Enabled (used as example paths, NOT read for content)
- Reference Files: Enabled
- All Expose to LLM options: Available

**Special Behavior**:
- Target files are listed as a path tree (📁/📄 icons) without reading content
- LLM uses target paths as EXAMPLES to understand what to search for
- Reference files and seed URLs serve as INSTRUCTIONS/TIPS for searching
- LLM proactively constructs search queries from natural language

## API Request Format

The `workflow` field is now part of `UnifiedWorkflowRequest`:

```json
{
    "workflow": "code_analysis",  // or "general_chat", "build_system_analysis", or "file_explorer"
    "user_message": "Please review this code for potential issues",
    "target_paths": ["azdo:/src/myproject/*.cpp"],
    "reference_files": ["/docs/coding-standards.md"],
    "seed_urls": [],
    "enable_embedding": false,
    "expose_to_llm": {
        "local_mcp": false,
        "azure_devops_mcp": true,
        "crawler": false
    },
    "model": "gpt-4",
    "max_tokens": 2000
}
```

**Default**: If `workflow` is not specified, it defaults to `"general_chat"`.

## HiChat Client Implementation Guide

### 1. Add Workflow Selector UI

Add a workflow selector dropdown or radio buttons at the top of the chat interface:

```typescript
enum WorkflowType {
    GENERAL_CHAT = "general_chat",
    CODE_ANALYSIS = "code_analysis",
    BUILD_SYSTEM_ANALYSIS = "build_system_analysis",
    FILE_EXPLORER = "file_explorer"
}

// Display names
const WORKFLOW_LABELS = {
    [WorkflowType.GENERAL_CHAT]: "💬 General Chat",
    [WorkflowType.CODE_ANALYSIS]: "🔍 Code Analysis",
    [WorkflowType.BUILD_SYSTEM_ANALYSIS]: "🔧 Build System",
    [WorkflowType.FILE_EXPLORER]: "📁 File Explorer"
};
```

### 2. Control UI Visibility Based on Workflow

```typescript
function getWorkflowUIConfig(workflow: WorkflowType) {
    switch (workflow) {
        case WorkflowType.GENERAL_CHAT:
            return {
                targetFilesEnabled: false,
                referenceFilesEnabled: false,
                azureDevOpsExposable: false,
                localMcpExposable: true,
                crawlerExposable: true,
                seedUrlsEnabled: true
            };
        case WorkflowType.CODE_ANALYSIS:
        case WorkflowType.BUILD_SYSTEM_ANALYSIS:
        case WorkflowType.FILE_EXPLORER:
            return {
                targetFilesEnabled: true,
                referenceFilesEnabled: true,
                azureDevOpsExposable: true,
                localMcpExposable: true,
                crawlerExposable: true,
                seedUrlsEnabled: true
            };
    }
}
```

### 3. Include Workflow in Request

When sending a request to the `/agent/chat` endpoint, include the selected workflow:

```typescript
async function sendChatRequest(message: string, workflow: WorkflowType, options: ChatOptions) {
    const request = {
        workflow: workflow,  // Add this field
        user_message: message,
        target_paths: options.targetPaths,
        reference_files: options.referenceFiles,
        // ... other fields
    };

    const response = await fetch('/agent/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request)
    });

    return response.json();
}
```

### 4. Suggested UI Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Workflow: [💬 General Chat ▼]                              │
│            ├─ 💬 General Chat                               │
│            ├─ 🔍 Code Analysis                              │
│            ├─ 🔧 Build System                               │
│            └─ 📁 File Explorer                              │
├─────────────────────────────────────────────────────────────┤
│  Target Files: [disabled when General Chat]                 │
│  Reference Files: [disabled when General Chat]              │
│  Seed URLs: [always available]                              │
├─────────────────────────────────────────────────────────────┤
│  Expose to LLM:                                             │
│  ☐ Local MCP                                                │
│  ☐ Azure DevOps [disabled when General Chat]                │
│  ☐ Web Crawler                                              │
├─────────────────────────────────────────────────────────────┤
│  [Chat messages area]                                       │
├─────────────────────────────────────────────────────────────┤
│  [Message input]                              [Send]        │
└─────────────────────────────────────────────────────────────┘
```

## Server-Side Enforcement

Note that even if a client sends `azure_devops_mcp: true` with `GENERAL_CHAT` workflow, the server will automatically enforce the workflow restrictions and disable Azure DevOps access.

This is implemented in `_apply_workflow_restrictions()` in `gateway/routers/agent.py`.

## Workflow Prompts

Each workflow has a specialized system prompt that guides the LLM behavior:

- **GENERAL_CHAT**: Friendly informational consultant tone
- **CODE_ANALYSIS**: Technical architect focused on code quality, bugs, and refactoring
- **BUILD_SYSTEM_ANALYSIS**: Build engineer focused on dependencies, configuration, and CI/CD
- **FILE_EXPLORER**: DevOps engineer for browsing/searching files with query construction

The appropriate prompt is automatically selected based on the workflow type.

## FILE_EXPLORER Workflow Details

The FILE_EXPLORER workflow has special behavior:

### Target Files as Examples
Unlike other workflows, FILE_EXPLORER does NOT read file content from target paths.
Instead, it lists the expanded paths as a tree structure:

```
Target Path Structure (examples of files/folders to search for):
  📁 src/components/
  📄 src/components/Button.tsx
  📄 src/components/Input.tsx
```

The LLM uses these as EXAMPLES to understand:
- File naming patterns and extensions
- Folder structure and organization
- Where similar files might be located

### Query Construction
The FILE_EXPLORER prompt instructs the LLM to automatically construct search queries:

| User Request | Constructed Query |
|--------------|-------------------|
| "find all JSON files" | `*.json` pattern |
| "find test files" | `test_*.py` or `*_test.py` |
| "find files containing TODO" | content search for 'TODO' |
| "where is class X defined" | content search for 'class X' |

# LLMCrawl System Architecture

## Overview

LLMCrawl is a production-grade Web RAG system that combines LLM chat capabilities with real-time web crawling and semantic search. The system features conversation memory, intelligent tool calling, multi-source web scraping, and workflow-based interactions.

**Hybrid Architecture:** Gateway and Memory Service run as local Python processes for direct filesystem access, while other services run in Docker containers.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                             │
├─────────────────────────────────────────────────────────────────┤
│  HiChat Web Client  │  HiChat CLI  │  REST API  │  cURL         │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                      HTTP POST /agent/chat
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                    GATEWAY SERVICE (Port 8000)                   │
├──────────────────────────────────────────────────────────────────┤
│  • FastAPI REST API                                              │
│  • Multi-Provider LLM Support (OpenAI, Azure, Anthropic, Claude) │
│  • Workflow System (General Chat, Code Analysis, Build, Explorer)│
│  • Conversation Store (In-Memory, 24h TTL)                       │
│  • Tool Calling & Orchestration                                  │
│  • Prompt Compression (LLMLingua-2 / tiktoken fallback)         │
└────┬────────────┬───────────────┬────────────────────────────────┘
     │            │               │
     │ Tool Call  │               │ Index Request
     │            │               ▼
     │            │   ┌────────────────────────────────────────────┐
     │            │   │      INDEXER SERVICE (Port 8002)           │
     │            │   ├────────────────────────────────────────────┤
     │            │   │  • LlamaIndex Document Processing          │
     │            │   │  • Embedding Generation                    │
     │            │   │  • Vector DB Storage (Qdrant/pgvector)     │
     │            │   │  • Semantic Search with Recency Boost      │
     │            │   └────────────────────────────────────────────┘
     │            │                      │
     │            │                      ▼
     │            │      ┌──────────────────────────────┐
     │            │      │  VECTOR DB (Qdrant/pgvector) │
     │            │      └──────────────────────────────┘
     │            │
     │            └─────────────┐
     │                          │
     ▼                          ▼
┌────────────────┐   ┌──────────────────────────────┐
│ CRAWLER (8001) │   │   MCP SERVERS                │
├────────────────┤   ├──────────────────────────────┤
│ • FireCrawl    │   │  LOCAL ACCESS (8003)          │
│   Search API   │   │  • Read local files           │
│ • Playwright   │   │  • List directories           │
│   Fallback     │   │  • Semantic search            │
│ • Trafilatura  │   │                               │
│   Extraction   │   │  AZURE DEVOPS (8004)          │
│ • Auth Support │   │  • Code search                │
└────┬───────────┘   │  • File retrieval             │
     │               │  • MSAL/PAT auth              │
     │               └──────────────────────────────┘
     ▼
┌─────────────────┐
│ FIRECRAWL (3002)│
├─────────────────┤       ┌──────────────┐
│ • Search/Scrape │───────│ Redis (6379) │ Rate Limiting
│ • Rate Limiting │       └──────────────┘
│ • Clean HTML    │
└─────────────────┘       ┌──────────────┐
                          │ PostgreSQL   │ Metadata Storage
                          └──────────────┘

Host-side Bridge Services (accessed via host.docker.internal):
┌─────────────────┐  ┌──────────────────┐
│  WCD Bridge     │  │  Claude Bridge   │
│  (8005)         │  │  (8006)          │
└─────────────────┘  └──────────────────┘

Memory Service (Port 8007):
┌─────────────────────────────────────────┐
│  MEMORY SERVICE (memsearch)              │
├─────────────────────────────────────────┤
│  • Auto-logging to daily markdown        │
│  • 80% context flush with distillation   │
│  • Semantic search across history        │
│  • Durable facts in MEMORY.md            │
│  • memsearch.watch() auto-indexing       │
└─────────────────────────────────────────┘
```

## Service Communication

```
┌─────────────────────────────────────────────────────────────────┐
│                    LOCAL PYTHON SERVICES                         │
│  Gateway (:8000) ◄──► Memory Service (:8007) ◄──► Milvus        │
└─────────────────────────────────────────────────────────────────┘
                       │
                       ▼ (HTTP to localhost for Docker containers)
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Network: webrag-network                │
└─────────────────────────────────────────────────────────────────┘

Gateway (LOCAL :8000)
    │    │    │        │
    │    │    │        ├─► LLM API (OpenAI/Azure/Anthropic)
    │    │    │        │
    │    │    └────────┼─► http://localhost:8003 (MCP Server)
    │    │             │
    │    └─────────────┼─► http://localhost:8002 (Indexer)
    │                  │        │
    └──────────────────┼─► http://localhost:8001 (Crawler)
                       │        │
                       │        └─► http://firecrawl:3002
                       │                 │
                       │                 └─► http://redis:6379
                       │
                       ├─► http://localhost:6333 (Qdrant)
                       │
                       └─► http://localhost:19530 (Milvus for Memory)
```

**Note:** Gateway and Memory Service run locally (not in Docker) for direct filesystem access.
They communicate with Docker services via `localhost:PORT` instead of Docker network names.

## Data Flow

### User Query Flow

```mermaid
sequenceDiagram
    participant User
    participant Gateway
    participant ConvStore as Conversation Store
    participant LLM as LLM Provider
    participant Crawler
    participant Indexer
    participant VectorDB

    User->>Gateway: POST /chat {message, conversation_id}
    Gateway->>ConvStore: Load previous messages
    ConvStore-->>Gateway: User/Assistant history
    Gateway->>Gateway: Check triggers & workflow

    alt Needs Fresh Data
        Gateway->>LLM: Chat with tools
        LLM-->>Gateway: tool_calls: crawl_and_refresh
        Gateway->>Crawler: POST /crawl {query, freshness}
        Crawler-->>Gateway: Clean documents
        Gateway->>Indexer: POST /index {documents}
        Indexer->>VectorDB: Store embeddings
        Indexer-->>Gateway: Ranked sources
        Gateway->>LLM: Generate response with sources
    else General Knowledge
        Gateway->>LLM: Direct chat
    end

    Gateway->>ConvStore: Store messages
    Gateway-->>User: {response, sources, conversation_id}
```

### Conversation Memory Flow

```mermaid
stateDiagram-v2
    [*] --> NewConversation: No conversation_id
    [*] --> LoadHistory: Has conversation_id

    NewConversation --> BuildContext: Generate UUID
    LoadHistory --> BuildContext: Retrieve messages

    BuildContext --> CheckTriggers: System + History + User

    CheckTriggers --> IncludeTools: Trigger detected
    CheckTriggers --> DirectLLM: General question

    IncludeTools --> ExecuteTool: LLM calls tool
    ExecuteTool --> GenerateResponse: Tool returns data

    DirectLLM --> GenerateResponse: No tool needed

    GenerateResponse --> StoreMessages: Save user + assistant
    StoreMessages --> [*]: Return response
```

## Workflow System

The system supports four workflow types for different use cases:

### 1. GENERAL_CHAT (`"general_chat"`)
**System Role**: Informational Consultant

**Use Cases**:
- General questions and casual conversation
- Information lookup
- Explanations and recommendations

**Restrictions**:
- Target Files: Disabled
- Reference Files: Disabled
- Azure DevOps: Disabled

### 2. CODE_ANALYSIS (`"code_analysis"`)
**System Role**: Technical Architect

**Use Cases**:
- Code review and refactoring
- Architecture analysis
- Bug hunting and performance analysis

**Available**: All options enabled

### 3. BUILD_SYSTEM_ANALYSIS (`"build_system_analysis"`)
**System Role**: Build Engineer

**Use Cases**:
- Build system troubleshooting
- Dependency analysis
- CI/CD pipeline analysis

**Available**: All options enabled

### 4. FILE_EXPLORER (`"file_explorer"`)
**System Role**: DevOps Engineer

**Use Cases**:
- Browse repositories and file systems
- Search files by patterns (`*.cpp`, `test_*.py`)
- Search files by content keywords

**Special Behavior**: Target files shown as path tree (not read for content)

### Workflow Request Format

```json
{
    "workflow": "code_analysis",
    "user_message": "Review this code for issues",
    "target_paths": ["azdo:/src/myproject/*.cpp"],
    "reference_files": ["/docs/standards.md"],
    "expose_to_llm": {
        "local_mcp": false,
        "azure_devops_mcp": true,
        "crawler": false
    }
}
```

## Tool Selection Matrix

| Query Type | Trigger Words | Tools Loaded | LLM Decision |
|------------|---------------|--------------|--------------|
| "Latest NVIDIA news" | "latest" | crawl + MCP | crawl_and_refresh |
| "Read README.md" | "read", filename | MCP only | read_local_file |
| "List files in src" | "list", "files" | MCP only | list_files |
| "What is Python?" | General knowledge | None | Direct LLM |

## MCP Server Architecture

### Local Access MCP Server (Port 8003)
- Read files with path validation
- List directories with filters
- Semantic search (optional)
- Security: Path traversal protection

### Azure DevOps MCP Server (Port 8004)
- Code search using Azure DevOps Code Search API
- File retrieval from specific paths/branches
- MSAL OAuth + PAT authentication
- Automatic search optimization

**Tool Selection Logic:**
```python
# Local file operations
"List files in /docs folder" → Local MCP (8003)

# Azure DevOps operations
"azdo:find TypeScript files" → Azure DevOps MCP (8004)
```

## Conversation Store Architecture

```
ConversationStore (In-Memory)
├── conversations: Dict[conversation_id, List[Message]]
│   └── Message: {role, content, tool_calls?, tool_call_id?}
├── timestamps: Dict[conversation_id, datetime]
├── max_age: 24 hours
└── max_messages: 50 per conversation
```

**Stored**: User messages, Assistant responses
**NOT Stored**: System prompts, Few-shot examples, Tool call intermediates

## Prompt Compression

When prompts exceed context limits, automatic compression is applied.

### Context Limits

| Provider | Context Window | Reserved for Response | Max Input |
|----------|---------------|----------------------|-----------|
| Anthropic Claude | 200,000 | 16,000 | 184,000 |
| OpenAI GPT-4 | 128,000 | 16,000 | 112,000 |

### Compression Priority (First = Compressed First)
1. Tool results
2. Old assistant messages
3. Old user messages
4. Recent user messages
5. System prompts (never compressed)

## Data Storage

| Service | Data Type | Storage | Persistence |
|---------|-----------|---------|-------------|
| Gateway | Conversations | In-memory (24h TTL) | Temporary |
| Crawler | HTML cache | Redis | Temporary |
| Indexer | Embeddings | Qdrant/pgvector | Persistent |
| MCP Server | File data | Host volume | Persistent |
| Memory Service | Daily logs | ./memory/daily/*.md | Persistent |
| Memory Service | Durable facts | ./memory/MEMORY.md | Persistent |
| Memory Service | Vector index | Milvus container volume | Rebuildable |
| Qdrant | Vectors | /qdrant/storage | Persistent |

## Security Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                         Internet (External)                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  Port 8000  │
                    └──────┬──────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│               Docker Network (Internal)                          │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐        │
│  │ Gateway │   │ Crawler │   │ Indexer │   │   MCP   │        │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
     ┌────────────────┐      ┌──────────────────┐
     │  Host System   │      │  External APIs   │
     │  (MCP folder)  │      │  (LLM, etc)      │
     └────────────────┘      └──────────────────┘
```

## Resource Usage (Typical)

| Service | CPU (Avg) | Memory | Purpose |
|---------|-----------|--------|---------|
| Gateway | 10-20% | 200-400 MB | Orchestration |
| Crawler | 40-60% | 500-1000MB | Web scraping |
| Indexer | 15-30% | 300-500 MB | Embedding |
| MCP Server | 5-10% | 100-200 MB | File ops |
| Qdrant | 10-20% | 500-1000MB | Vector DB |
| **Total** | ~1.5 CPU | ~3-4 GB | |

## Performance Metrics

| Operation | Typical Time | Max Time |
|-----------|-------------|----------|
| Simple query (no tools) | 500-800ms | 2s |
| News query (with crawl) | 10-15s | 45s |
| Follow-up (with tool) | 8-12s | 45s |
| Conversation load | <10ms | 50ms |

## Scaling Considerations

### Current Limitations
1. **Conversation Store**: In-memory (lost on restart) - Use Redis for production
2. **Sequential Playwright**: No parallel browser instances - Browser pooling for scale
3. **Single Gateway**: No load balancing - Multiple replicas for production

### Production Setup

```
                    ┌──────────────┐
                    │ Load Balancer│
                    └──────┬───────┘
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
        Gateway-1      Gateway-2      Gateway-3
            │              │              │
            └──────────────┼──────────────┘
                           │
                    ┌──────▼───────┐
                    │ Shared Redis │ (Conversation Store)
                    └──────────────┘
```

## Quick Reference: Service URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Gateway | http://localhost:8000 | Main API |
| Gateway Health | http://localhost:8000/health | Health check |
| Gateway Chat | http://localhost:8000/agent/chat | Chat endpoint |
| Gateway Distill | http://localhost:8000/agent/distill | Manual memory save |
| Crawler | http://localhost:8001 | Crawl service |
| Indexer | http://localhost:8002 | Index service |
| MCP Server | http://localhost:8003 | File operations |
| Memory Service | http://localhost:8007 | Long-term memory |
| Qdrant Dashboard | http://localhost:6333/dashboard | Vector DB UI |
| HiChat | http://localhost:8080 | Web client |
| Grafana | http://localhost:3001 | Monitoring |
| Prometheus | http://localhost:9090 | Metrics |

## Memory Service Architecture

The Memory Service implements OpenClaw-style auto-memory with two types of persistence:

### Memory Types

| Type | File | Content | Visibility |
|------|------|---------|------------|
| **Sessional** | `daily/YYYY-MM-DD.md` | Full conversation logs + summaries | Searched on demand |
| **Durable** | `MEMORY.md` | Always-true facts and rules | Always in system prompt |

### Memory Flow

```mermaid
sequenceDiagram
    participant User
    participant Gateway
    participant LLM
    participant Memory as Memory Service

    User->>Gateway: Send message
    Gateway->>Memory: Log user message (daily log)
    Gateway->>Gateway: Check token count

    alt Token count >= 80%
        Gateway->>LLM: Inject distillation prompt
        LLM-->>Gateway: Response with [SUMMARY] [FACTS]
        Gateway->>Memory: Save summary to daily log
        Gateway->>Memory: Save facts to MEMORY.md
        Gateway->>Gateway: Strip markers from response
    end

    Gateway->>Memory: Log assistant response
    Memory-->>Memory: memsearch.watch() auto-indexes
    Gateway-->>User: Clean response
```

### File Structure

```
deploy/memory/
├── daily/                    # Sessional memory (per-day logs)
│   ├── 2026-03-05.md        # Full transcript + session summaries
│   ├── 2026-03-06.md
│   └── 2026-03-07.md
└── MEMORY.md                 # Durable facts (always loaded)

# Vector index stored in Milvus container volume (not local file)
# Milvus v2.5.5+ required (milvus-lite doesn't support Windows)
```

## Related Documentation

- **[INSTALL.md](INSTALL.md)** - Installation guide
- **[CONFIGURATION.md](CONFIGURATION.md)** - Configuration reference
- **[DEVELOPMENT.md](DEVELOPMENT.md)** - Development setup
- **[DIAGNOSTICS.md](DIAGNOSTICS.md)** - Troubleshooting
- **[MEMORY.md](MEMORY.md)** - Memory service details
- **[MCP_SERVERS.md](MCP_SERVERS.md)** - MCP server details

# LLMCrawl Memory Service

OpenClaw-style auto-memory with semantic search for long-term conversation persistence.

**Requirements:** Milvus v2.5.5+ container for vector storage (milvus-lite doesn't support Windows).

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Memory Types](#memory-types)
- [How It Works](#how-it-works)
  - [Auto-Logging](#auto-logging)
  - [80% Context Flush](#80-context-flush)
  - [Manual Distillation](#manual-distillation)
- [Configuration](#configuration)
- [File Structure](#file-structure)
- [API Endpoints](#api-endpoints)
- [HiChat Integration](#hichat-integration)
- [Portability](#portability)
- [Troubleshooting](#troubleshooting)

---

## Overview

The Memory Service provides persistent, searchable memory across conversations. Unlike the in-memory conversation store (24-hour TTL), the memory service:

- **Persists forever** - Markdown files on disk
- **Semantic search** - Find relevant past conversations by meaning
- **Auto-distillation** - Extracts key information when context fills up
- **Always-loaded facts** - Important rules injected into every conversation

**Key Principle**: Markdown is the source of truth. The vector index is a rebuildable cache.

---

## Architecture

Both Gateway and Memory Service run as **local Python processes** (not Docker containers) for direct filesystem access.

```
┌─────────────────────────────────────────────────────────────────┐
│ Gateway / Agent (LOCAL PYTHON SERVICE)                           │
│                                                                  │
│  1. On each message:                                            │
│     └── Write directly to deploy/memory/daily/YYYY-MM-DD.md    │
│                                                                  │
│  2. Before LLM call, check token count:                         │
│     └── If >= 80%: inject distillation prompt                   │
│                                                                  │
│  3. After LLM response:                                         │
│     └── Parse for [SUMMARY] → append to daily log               │
│     └── Parse for [FACTS] → append to MEMORY.md                 │
│                                                                  │
│  4. LLM can call memory_search tool ───► Memory Service         │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ Memory Service (Port 8007) - LOCAL PYTHON SERVICE                │
│                                                                  │
│  Endpoints:                                                      │
│    POST /search    ← Semantic search (LLM tool)                 │
│    GET  /context   ← Get memory for conversation start          │
│    POST /reindex   ← Rebuild vector index                       │
│    GET  /health    ← Health check                               │
│                                                                  │
│  Background:                                                     │
│    memsearch.watch() ← Auto-indexes file changes (1.5s debounce)│
│                                                                  │
│  Vector Storage: ─────────────────────► Milvus Container        │
│                                         (localhost:19530)        │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ deploy/memory/ (Markdown files - source of truth)               │
│                                                                  │
│  ├── daily/                                                     │
│  │   ├── 2026-03-05.md   # Full conversation transcript         │
│  │   ├── 2026-03-06.md   # Includes session summaries           │
│  │   └── 2026-03-07.md                                          │
│  └── MEMORY.md           # Durable facts (always loaded)        │
│                                                                  │
│  Vector index stored in Milvus container volume (not local file)│
└─────────────────────────────────────────────────────────────────┘
```

---

## Memory Types

The system maintains two distinct types of memory:

| Type | File | Analogy | Content | When Loaded |
|------|------|---------|---------|-------------|
| **Sessional** | `daily/YYYY-MM-DD.md` | Daily Journal | "What happened today" | Searched on demand |
| **Durable** | `MEMORY.md` | Cheat Sheet | "Always-true rules" | Every conversation start |

### Sessional Memory (Daily Logs)

- Full conversation transcripts with timestamps
- Session summaries extracted at 80% flush
- Automatically indexed for semantic search
- One file per day

**Example daily log entry:**
```markdown
### [10:15:32] user
How do I configure the Go proxy for SSO?

### [10:15:45] assistant
To configure the Go proxy for SSO, you need to...

---
## Session Summary (10:45)
We debugged the Go SSO proxy and fixed a 403 error by updating header parsing.
The solution involved base64 encoding the X-Auth-Token header.
---
```

### Durable Memory (MEMORY.md)

- Permanent facts, rules, and preferences
- Injected into system prompt for every new conversation
- User preferences, project constraints, technical details

**Example MEMORY.md entry:**
```markdown
## 2026-03-07 10:45
- The Go SSO proxy requires X-Auth-Token header to be base64 encoded
- User prefers Python over Go for new services
- Project uses PostgreSQL 16 with pgvector extension
```

---

## How It Works

### Auto-Logging

Every user and assistant message is automatically written to the daily log:

```
User sends message
    │
    ▼
Gateway writes to daily/2026-03-07.md
    │
    ▼
memsearch.watch() detects change
    │
    ▼
Auto-indexes content (1.5s debounce)
```

**Format:**
```markdown
### [HH:MM:SS] role
Message content here...
```

### 80% Context Flush

When the conversation context reaches 80% of the model's limit:

1. **Detection**: Gateway calculates token count before LLM call
2. **Injection**: Hidden distillation prompt added to messages
3. **Response**: LLM includes `[SUMMARY]` and `[FACTS]` markers
4. **Parsing**: Gateway extracts and saves to appropriate files
5. **Cleanup**: Markers stripped before showing response to user

**Distillation Prompt:**
```
### MEMORY CHECKPOINT (80% context used)

Before continuing, extract important information:

[SUMMARY]
(2-3 sentence recap of what was accomplished)
[/SUMMARY]

[FACTS]
- Any permanent rules or preferences discovered
- Important decisions that should be remembered
[/FACTS]

After the markers, continue with your normal response.
```

**LLM Response Example:**
```
[SUMMARY]
We configured the authentication proxy and fixed CORS issues.
The solution involved updating the nginx config and adding proper headers.
[/SUMMARY]

[FACTS]
- CORS requires explicit origin in production (no wildcards)
- Auth proxy timeout must be > 30s for large file uploads
[/FACTS]

Now, to continue with your question about...
```

### Manual Distillation

Users can trigger distillation at any time via:

1. **HiChat Button**: Click "Save to Memory" in the UI
2. **API Call**: `POST /agent/distill` with conversation ID

This is useful for:
- Saving important information before ending a session
- Capturing key decisions mid-conversation
- User-initiated memory checkpoints

---

## Configuration

Add these to your `.env` file:

```bash
# Memory service URL (local service, not Docker)
MEMORY_SERVICE_URL=http://localhost:8007

# Memory data path (local folder accessible by both gateway and memory-service)
MEMORY_DATA_PATH=deploy/memory

# Milvus URL (Docker container for vector storage)
# Required: Milvus v2.5.5+ (milvus-lite doesn't support Windows)
MILVUS_URI=http://localhost:19530

# Enable auto-logging of all messages to daily logs
MEMORY_AUTO_LOG=true

# Enable automatic 80% context flush with distillation
MEMORY_AUTO_FLUSH=true

# Context threshold for triggering distillation (0.0-1.0)
MEMORY_FLUSH_THRESHOLD=0.8
```

### Milvus Container

The memory service requires a Milvus v2.5.5+ container for vector storage:

```yaml
# docker-compose.dev.yml
milvus:
  image: milvusdb/milvus:v2.5.5
  container_name: web-rag-milvus
  command: ["milvus", "run", "standalone"]
  ports:
    - "19530:19530"
    - "9091:9091"
  environment:
    - ETCD_USE_EMBED=true
    - ETCD_DATA_DIR=/var/lib/milvus/etcd
    - COMMON_STORAGETYPE=local
  volumes:
    - milvus_data:/var/lib/milvus
```

**Note:** Gateway and Memory Service run locally (not in Docker containers) for direct filesystem access. Only Milvus runs in Docker.

---

## File Structure

```
deploy/memory/
├── daily/                    # Sessional memory (one file per day)
│   ├── 2026-03-05.md
│   ├── 2026-03-06.md
│   └── 2026-03-07.md
└── MEMORY.md                 # Durable facts (always loaded)

# Vector index stored in Milvus container volume (milvus_data)
# NOT a local file - Milvus Lite doesn't support Windows
```

### Daily Log Format

```markdown
# Conversation Log - 2026-03-07

### [09:15:00] user
First message of the day...

### [09:15:12] assistant
Response to first message...

### [10:30:00] user
Another conversation...

---
## Session Summary (10:45)
Summary of the session extracted at 80% flush...
---

### [14:00:00] user
Afternoon conversation...
```

### MEMORY.md Format

```markdown
# Long-term Memory

## 2026-03-05 14:30
- User prefers concise responses
- Project uses TypeScript 5.0+

## 2026-03-06 10:15
- Database is PostgreSQL 16 with pgvector
- Deployment target is Azure Kubernetes Service
```

---

## API Endpoints

### Health Check
```bash
curl http://localhost:8007/health
```

Response:
```json
{
  "status": "healthy",
  "service": "memory-service",
  "memory_file_exists": true,
  "daily_log_count": 5,
  "watcher_running": true
}
```

### Semantic Search
```bash
curl -X POST http://localhost:8007/search \
  -H "Content-Type: application/json" \
  -d '{"query": "SSO proxy configuration", "limit": 5}'
```

Response:
```json
{
  "results": [
    {
      "content": "To configure the Go proxy for SSO...",
      "source": "daily/2026-03-07.md",
      "heading": "[10:15:45] assistant",
      "score": 0.85
    }
  ],
  "query": "SSO proxy configuration"
}
```

### Get Context
```bash
curl "http://localhost:8007/context?max_tokens=2000"
```

Returns MEMORY.md content plus relevant recent memories.

### Manual Distillation (via Gateway)
```bash
curl -X POST http://localhost:8000/agent/distill \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "your-conversation-id"}'
```

Response:
```json
{
  "success": true,
  "conversation_id": "your-conversation-id",
  "summary_preview": "We configured the proxy...",
  "facts_preview": "- CORS requires explicit origin...",
  "message": "Saved session summary and durable facts to memory"
}
```

### Reindex
```bash
curl -X POST http://localhost:8007/reindex
```

Rebuilds the vector index from all markdown files.

---

## HiChat Integration

### Save to Memory Button

HiChat includes a "Save to Memory" button that:

1. Triggers manual distillation for the current conversation
2. Shows preview of saved summary and facts
3. Confirms successful save with a system message

### How to Use

1. Have a conversation with important information
2. Click "Save to Memory" button (next to Send)
3. LLM extracts summary and facts
4. Confirmation message shows what was saved

---

## Portability

The `MemoryClient` class (`services/memory_service/client.py`) is designed to be portable to other languages:

### Python
```python
from memory_service.client import MemoryClient

client = MemoryClient("/data/memory")
client.append_to_daily_log("user", "Hello!")
client.append_durable_facts("User prefers Python")
```

### Go
```go
func (c *MemoryClient) AppendToDailyLog(role, content string) {
    today := time.Now().Format("2006-01-02")
    filename := filepath.Join(c.DailyFolder, today+".md")

    timestamp := time.Now().Format("15:04:05")
    entry := fmt.Sprintf("\n### [%s] %s\n%s\n", timestamp, role, content)

    f, _ := os.OpenFile(filename, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
    defer f.Close()
    f.WriteString(entry)
}
```

### C#
```csharp
public void AppendToDailyLog(string role, string content) {
    var today = DateTime.Now.ToString("yyyy-MM-dd");
    var filename = Path.Combine(DailyFolder, $"{today}.md");

    var timestamp = DateTime.Now.ToString("HH:mm:ss");
    var entry = $"\n### [{timestamp}] {role}\n{content}\n";

    File.AppendAllText(filename, entry);
}
```

The HTTP API (`/search`, `/context`) is language-agnostic for semantic search.

---

## Troubleshooting

### Memory Service Not Starting

```bash
# Check if memory service is running (local process)
curl http://localhost:8007/health

# Check if Milvus container is running
docker ps | grep milvus
docker logs web-rag-milvus

# Start services with PowerShell script
.\scripts\start-services.ps1
```

### Milvus Connection Issues

```bash
# Verify Milvus is accessible
curl http://localhost:19530/health

# Check Milvus logs
docker logs web-rag-milvus

# Restart Milvus container
docker restart web-rag-milvus
```

### Files Not Being Indexed

```bash
# Check if watcher is running
curl http://localhost:8007/health
# Look for: "watcher_running": true

# Force reindex
curl -X POST http://localhost:8007/reindex
```

### MEMORY.md Not Loading

```bash
# Check if file exists
cat deploy/memory/MEMORY.md

# Check gateway logs for memory loading
# Gateway runs locally, check terminal output or log files
cat deploy/logs/gateway.log | grep "memory"
```

### Distillation Not Triggering

1. Check `MEMORY_AUTO_FLUSH=true` in `.env`
2. Check `MEMORY_FLUSH_THRESHOLD=0.8` (or your desired threshold)
3. Verify context is actually reaching the threshold
4. Check gateway logs for "triggering memory flush"

### Permission Issues

```bash
# Ensure memory folder is writable
chmod -R 777 deploy/memory/
```

### Stopping/Starting Services

```powershell
# Windows: Use the service management scripts
.\scripts\stop-services.ps1           # Stop all services
.\scripts\stop-services.ps1 -Service memory   # Stop only memory service
.\scripts\start-services.ps1          # Start all services
.\scripts\restart-services.ps1        # Restart all services
```

---

## Related Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and data flows
- **[CONFIGURATION.md](CONFIGURATION.md)** - Environment variable reference
- **[DIAGNOSTICS.md](DIAGNOSTICS.md)** - Troubleshooting guide

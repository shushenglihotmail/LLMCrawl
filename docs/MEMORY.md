# Memory Service

Standalone containerized service for conversation memory with semantic search.

**Key principle:** All operations via HTTP REST API. Gateway is a pure HTTP client.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Standalone Deployment](#standalone-deployment)
- [API Reference](#api-reference)
- [Integration Guide](#integration-guide)
- [Memory Types](#memory-types)
- [How It Works](#how-it-works)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## Overview

The Memory Service provides persistent, searchable memory across conversations:

- **All operations via HTTP** - Write, search, and read through REST API
- **Semantic search** - Find relevant past conversations by meaning
- **Auto-indexing** - File changes automatically indexed (1.5s debounce)
- **Format consistency** - All clients share same file structure and format
- **Standalone deployment** - Can be used by any application

---

## Architecture

```
┌─────────────────┐           ┌──────────────────────────────────┐
│                 │           │      Memory Service (8007)       │
│   Your App      │───HTTP───▶│                                  │
│   (Gateway)     │           │  POST /write_daily  (log msgs)   │
│                 │           │  POST /write_memory (save facts) │
└─────────────────┘           │  POST /search       (find)       │
                              │  GET  /context      (load)       │
                              │  POST /reindex      (rebuild)    │
                              └────────────┬───────────────────────┘
                                           │
                              ┌────────────▼───────────────────────┐
                              │     Storage (MEMORY_DATA_PATH)     │
                              │  ├── daily/YYYY-MM-DD.md           │
                              │  └── MEMORY.md                     │
                              └────────────┬───────────────────────┘
                                           │
                              ┌────────────▼───────────────────────┐
                              │     Milvus (Vector DB)             │
                              │     localhost:19530                │
                              └────────────────────────────────────┘
```

**Key points:**
- Gateway does NOT access files directly - all via HTTP
- Memory service manages file format consistency
- Milvus stores vector embeddings for semantic search

---

## Standalone Deployment

The memory service can be deployed independently for use by any application.

### Using Pre-built Image (Recommended)

```bash
# Pull from GitHub Container Registry
docker pull ghcr.io/shushenglihotmail/memory-service:latest

# Or specific version
docker pull ghcr.io/shushenglihotmail/memory-service:1.2.0
```

### Build Docker Image Locally

```bash
cd services/memory_service
docker build -t memory-service:latest .
```

### Transfer Image to Another Machine (No Registry)

If you don't want to push to a container registry, you can transfer the image directly:

**On source machine (save image to file):**
```bash
# Save image to tar file
docker save memory-service:latest -o memory-service.tar

# Or with compression (smaller file)
docker save memory-service:latest | gzip > memory-service.tar.gz
```

**Transfer the file** (scp, USB drive, network share, etc.):
```bash
scp memory-service.tar.gz user@target-machine:/path/to/
```

**On target machine (load image from file):**
```bash
# Load from tar file
docker load -i memory-service.tar

# Or from compressed file
gunzip -c memory-service.tar.gz | docker load

# Verify image is loaded
docker images | grep memory-service
```

### Deploy with docker-compose

```bash
cd memory-service

# Set your data path
export MEMORY_DATA_PATH=/path/to/your/logs

# Start services (memory-service + Milvus)
docker compose up -d

# Service available at http://localhost:8007
```

### Deploy Standalone (bring your own Milvus)

```bash
# Start Milvus first
docker run -d --name milvus \
  -p 19530:19530 \
  -e ETCD_USE_EMBED=true \
  -e ETCD_DATA_DIR=/var/lib/milvus/etcd \
  milvusdb/milvus:v2.5.5 milvus run standalone

# Start memory service
docker run -d \
  --name memory-service \
  -p 8007:8007 \
  -v /path/to/your/logs:/data \
  -e MEMORY_DATA_PATH=/data \
  -e MILVUS_URI=host.docker.internal:19530 \
  memory-service:latest
```

### Verify Deployment

```bash
# Health check
curl http://localhost:8007/health

# Expected response:
{
  "status": "healthy",
  "service": "memory-service",
  "memory_file_exists": false,
  "daily_log_count": 0,
  "watcher_running": true
}
```

---

## API Reference

### POST /write_daily

Write a conversation message to today's daily log.

**Request:**
```http
POST /write_daily
Content-Type: application/json

{
  "role": "user",
  "content": "Hello, how are you?",
  "session_id": "conv-abc123"
}
```

**Response:**
```json
{
  "success": true,
  "file_path": "/data/daily/2024-01-15.md",
  "message": "Appended user message to daily log"
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | string | Yes | Message role: "user", "assistant", or "system" |
| `content` | string | Yes | Message content |
| `session_id` | string | No | Session/conversation ID for grouping messages |

**Session Grouping:**
When `session_id` is provided, messages are grouped under session headers. A new session header is written when a new `session_id` is first seen in today's log. This allows clear separation between different conversation sessions (e.g., when user clicks "Clear Context").

---

### POST /write_memory

Write facts to MEMORY.md (durable long-term memory).

**Request:**
```http
POST /write_memory
Content-Type: application/json

{
  "content": "- User prefers dark mode\n- Project uses Python 3.10",
  "section": "User Preferences",
  "replace": false
}
```

**Response:**
```json
{
  "success": true,
  "file_path": "/data/MEMORY.md",
  "message": "Written 45 chars to MEMORY.md"
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | Yes | Content to write |
| `section` | string | No | Section header (creates `## Section` heading) |
| `replace` | boolean | No | If true, replace entire file (default: false) |

---

### POST /search

Semantic search across all indexed memories.

**Request:**
```http
POST /search
Content-Type: application/json

{
  "query": "user preferences",
  "limit": 5
}
```

**Response:**
```json
{
  "results": [
    {
      "content": "User prefers dark mode",
      "source": "MEMORY.md",
      "heading": "User Preferences",
      "score": 0.95
    },
    {
      "content": "User asked about Python setup...",
      "source": "daily/2024-01-15.md",
      "heading": "[10:30:00] user",
      "score": 0.82
    }
  ],
  "query": "user preferences"
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Search query |
| `limit` | integer | No | Max results (default: 5, max: 50) |

---

### GET /context

Get memory context for conversation start.

**Request:**
```http
GET /context?max_tokens=2000&query=optional+focus
```

**Response:**
```json
{
  "context": "## Long-term Memory\n\n- User prefers dark mode\n...",
  "sources": ["MEMORY.md", "daily/2024-01-15.md"],
  "token_count": 450
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `max_tokens` | integer | No | Max tokens to return (default: 2000) |
| `query` | string | No | Optional query to focus context |

---

### POST /reindex

Rebuild the vector index from markdown files.

**Request:**
```http
POST /reindex?force=true
```

**Response:**
```json
{
  "success": true,
  "chunks_indexed": 42,
  "message": "Indexed 42 chunks"
}
```

**Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `force` | boolean | No | Re-embed all chunks even if unchanged |

---

### GET /health

Health check endpoint.

**Request:**
```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "memory-service",
  "version": "1.0.0",
  "memory_file_exists": true,
  "daily_log_count": 5,
  "watcher_running": true
}
```

---

## Integration Guide

### Python

```python
import httpx

MEMORY_URL = "http://localhost:8007"

async def log_message(role: str, content: str):
    """Log a conversation message."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{MEMORY_URL}/write_daily",
            json={"role": role, "content": content}
        )
        return resp.json()

async def search_memory(query: str, limit: int = 5):
    """Search memories."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{MEMORY_URL}/search",
            json={"query": query, "limit": limit}
        )
        return resp.json()["results"]

async def get_context(max_tokens: int = 2000):
    """Get memory context for conversation start."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{MEMORY_URL}/context",
            params={"max_tokens": max_tokens}
        )
        return resp.json()["context"]

async def save_facts(facts: str):
    """Save durable facts to MEMORY.md."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{MEMORY_URL}/write_memory",
            json={"content": facts}
        )
        return resp.json()
```

### Go

```go
package memory

import (
    "bytes"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
)

const memoryURL = "http://localhost:8007"

func LogMessage(role, content string) error {
    body := map[string]string{"role": role, "content": content}
    jsonBody, _ := json.Marshal(body)

    resp, err := http.Post(
        memoryURL+"/write_daily",
        "application/json",
        bytes.NewBuffer(jsonBody),
    )
    if err != nil {
        return err
    }
    defer resp.Body.Close()

    if resp.StatusCode != 200 {
        body, _ := io.ReadAll(resp.Body)
        return fmt.Errorf("failed: %s", body)
    }
    return nil
}

func Search(query string, limit int) ([]map[string]interface{}, error) {
    body := map[string]interface{}{"query": query, "limit": limit}
    jsonBody, _ := json.Marshal(body)

    resp, err := http.Post(
        memoryURL+"/search",
        "application/json",
        bytes.NewBuffer(jsonBody),
    )
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()

    var result struct {
        Results []map[string]interface{} `json:"results"`
    }
    json.NewDecoder(resp.Body).Decode(&result)
    return result.Results, nil
}
```

### curl

```bash
# Log a user message
curl -X POST http://localhost:8007/write_daily \
  -H "Content-Type: application/json" \
  -d '{"role": "user", "content": "Hello world!"}'

# Log an assistant response
curl -X POST http://localhost:8007/write_daily \
  -H "Content-Type: application/json" \
  -d '{"role": "assistant", "content": "Hi there!"}'

# Save durable facts
curl -X POST http://localhost:8007/write_memory \
  -H "Content-Type: application/json" \
  -d '{"content": "- User prefers Python\n- Project deadline is March"}'

# Search memories
curl -X POST http://localhost:8007/search \
  -H "Content-Type: application/json" \
  -d '{"query": "user preferences", "limit": 5}'

# Get context for new conversation
curl "http://localhost:8007/context?max_tokens=2000"

# Force reindex
curl -X POST "http://localhost:8007/reindex?force=true"

# Health check
curl http://localhost:8007/health
```

---

## Memory Types

| Type | File | Content | When Loaded |
|------|------|---------|-------------|
| **Sessional** | `daily/YYYY-MM-DD.md` | Conversation transcripts | Searched on demand |
| **Durable** | `MEMORY.md` | Always-true facts | Every conversation start |

### Daily Logs (Sessional Memory)

Auto-generated format with session grouping:
```markdown
# 2024-01-15

## Session 10:15 [ID: conv-abc123]

### [10:15:32] user
How do I configure the proxy?

### [10:15:45] assistant
To configure the proxy, you need to...

---

## Session 14:30 [ID: conv-def456]

### [14:30:12] user
New question after Clear Context

### [14:30:25] assistant
Here's the answer...

---
## Session Summary (15:00)
We configured the proxy and answered questions about deployment.
---
```

**Session headers** are automatically written when:
- A new `session_id` is first seen in today's log
- User clicks "Clear Context" in HiChat (creates new conversation_id)

### MEMORY.md (Durable Memory)

```markdown
## 2024-01-15 10:45
- CORS requires explicit origin in production
- User prefers Python over Go

## 2024-01-16 14:30
- Project uses PostgreSQL 16 with pgvector
- Deployment target is Azure Kubernetes
```

---

## How It Works

### Auto-Logging Flow

```
App sends message
    │
    ▼
POST /write_daily {"role": "user", "content": "..."}
    │
    ▼
Memory service writes to daily/YYYY-MM-DD.md
    │
    ▼
memsearch.watch() detects file change
    │
    ▼
Auto-indexes content (1.5s debounce)
    │
    ▼
Content searchable via POST /search
```

### 80% Context Flush (Gateway Feature)

When conversation context reaches 80% capacity:

1. **Gateway** injects distillation prompt into LLM call
2. **LLM** responds with `[SUMMARY]` and `[FACTS]` markers
3. **Gateway** parses response and calls memory service:
   - `POST /write_daily` with summary
   - `POST /write_memory` with facts
4. **Gateway** strips markers before showing response to user

---

## Configuration

### Memory Service Environment

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MEMORY_DATA_PATH` | Yes | `/data/memory` | Path to markdown files |
| `PORT` | No | `8007` | HTTP listening port |
| `MILVUS_URI` | No | `./milvus.db` | Milvus connection URI |
| `EMBEDDING_PROVIDER` | No | `local` | Embedding provider |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity |

### Gateway Environment

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MEMORY_SERVICE_URL` | Yes* | - | Memory service URL (e.g., `http://localhost:8007`) |
| `MEMORY_AUTO_LOG` | No | `true` | Auto-log messages to daily logs |
| `MEMORY_AUTO_FLUSH` | No | `true` | Enable 80% context flush |
| `MEMORY_FLUSH_THRESHOLD` | No | `0.8` | Context % to trigger flush |

*Required if memory features are enabled

---

## Troubleshooting

### Service Not Starting

```bash
# Check health
curl http://localhost:8007/health

# Check logs
docker logs memory-service

# Check Milvus
docker logs memory-milvus
curl http://localhost:19530/health
```

### Search Returns Empty Results

```bash
# Check if files exist
ls -la /path/to/memory/

# Force reindex
curl -X POST http://localhost:8007/reindex?force=true

# Check watcher status
curl http://localhost:8007/health
# Look for: "watcher_running": true
```

### Connection Refused

```bash
# Check if service is running
docker ps | grep memory

# Check port binding
netstat -an | grep 8007

# Restart service
docker restart memory-service
```

### Milvus Issues

```bash
# Check Milvus health
curl http://localhost:9091/healthz

# Restart Milvus
docker restart memory-milvus

# Check Milvus logs
docker logs memory-milvus --tail 50
```

---

## Related Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture
- **[CONFIGURATION.md](CONFIGURATION.md)** - Environment variables
- **[memory-service/README.md](../memory-service/README.md)** - Standalone deployment

# Memory Service

A standalone, containerized semantic search and indexing service for markdown log files. Provides HTTP REST APIs for writing, searching, and retrieving memory context.

## Architecture

```
Your App ──HTTP──> Memory Service ──> Storage (markdown files)
                        │
                        └──> Milvus (vector DB)
```

**Key features:**
- All operations via HTTP REST API (no direct file access needed)
- Automatic indexing on file changes
- Semantic search using sentence-transformers
- Format consistency enforced by the service

## Build

### Using pre-built image (recommended)

```bash
# Pull from GitHub Container Registry
docker pull ghcr.io/shushenglihotmail/memory-service:latest

# Or specific version
docker pull ghcr.io/shushenglihotmail/memory-service:1.2.0
```

### Building locally

```bash
# Build the Docker image
cd services/memory_service
docker build -t memory-service:latest .
```

### Transfer to another machine (no registry)

```bash
# On source machine: save to file
docker save memory-service:latest | gzip > memory-service.tar.gz

# Transfer file (scp, USB, network share, etc.)
scp memory-service.tar.gz user@target:/path/to/

# On target machine: load from file
gunzip -c memory-service.tar.gz | docker load
```

## Quick Start

### Using docker-compose (recommended)

```bash
# Navigate to memory-service folder
cd memory-service

# Copy and edit configuration
cp .env.example .env
# Edit .env to set MEMORY_DATA_PATH

# Start services (builds if needed)
docker compose up -d --build

# Service available at http://localhost:8007
```

Or inline:

```bash
MEMORY_DATA_PATH=/path/to/your/logs docker compose up -d --build
```

### Standalone Docker run (bring your own Milvus)

```bash
# Start Milvus first
docker run -d --name milvus \
  -p 19530:19530 \
  -e ETCD_USE_EMBED=true \
  milvusdb/milvus:v2.5.5 milvus run standalone

# Start memory service
docker run -d \
  -p 8007:8007 \
  -v /path/to/your/logs:/data \
  -e MEMORY_DATA_PATH=/data \
  -e MILVUS_URI=host.docker.internal:19530 \
  memory-service:latest
```

## HTTP API Reference

### Write Daily Log

Write a conversation message to today's daily log. Auto-indexed for search.
Messages are grouped by `session_id` with session headers for clear separation.

```http
POST /write_daily
Content-Type: application/json

{
  "role": "user",
  "content": "Hello, how are you?",
  "session_id": "conv-abc123"
}
```

Response:
```json
{
  "success": true,
  "file_path": "/data/daily/2024-01-15.md",
  "message": "Appended user message to daily log"
}
```

### Write Durable Memory

Write facts to MEMORY.md (long-term memory).

```http
POST /write_memory
Content-Type: application/json

{
  "content": "- User prefers dark mode\n- User name is John",
  "section": "User Preferences"
}
```

### Search Memories

Semantic search across all indexed memories.

```http
POST /search
Content-Type: application/json

{
  "query": "user preferences",
  "limit": 5
}
```

Response:
```json
{
  "results": [
    {
      "content": "User prefers dark mode",
      "source": "MEMORY.md",
      "heading": "User Preferences",
      "score": 0.95
    }
  ],
  "query": "user preferences"
}
```

### Get Context

Get memory context for conversation start.

```http
GET /context?max_tokens=2000
```

### Health Check

```http
GET /health
```

### Force Reindex

Rebuild the vector index from markdown files.

```http
POST /reindex?force=true
```

## Integration Examples

### Python

```python
import httpx

MEMORY_URL = "http://localhost:8007"

async def log_message(role: str, content: str):
    async with httpx.AsyncClient() as client:
        await client.post(f"{MEMORY_URL}/write_daily",
                         json={"role": role, "content": content})

async def search(query: str, limit: int = 5):
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{MEMORY_URL}/search",
                                json={"query": query, "limit": limit})
        return resp.json()["results"]
```

### Go

```go
package main

import (
    "bytes"
    "encoding/json"
    "net/http"
)

func LogMessage(role, content string) error {
    body := map[string]string{"role": role, "content": content}
    jsonBody, _ := json.Marshal(body)
    _, err := http.Post("http://localhost:8007/write_daily",
                        "application/json", bytes.NewBuffer(jsonBody))
    return err
}
```

### curl

```bash
# Log a user message
curl -X POST http://localhost:8007/write_daily \
  -H "Content-Type: application/json" \
  -d '{"role": "user", "content": "Hello world!", "session_id": "conv-abc123"}'

# Search memories
curl -X POST http://localhost:8007/search \
  -H "Content-Type: application/json" \
  -d '{"query": "hello", "limit": 5}'
```

## Storage Format

The memory service manages files in this structure:

```
{MEMORY_DATA_PATH}/
├── daily/                    # Daily conversation logs
│   ├── 2024-01-15.md
│   ├── 2024-01-16.md
│   └── ...
└── MEMORY.md                 # Durable long-term facts
```

Daily log format (auto-generated with session grouping):
```markdown
# 2024-01-15

## Session 14:30 [ID: conv-abc123]

### [14:30:45] user
Hello, how are you?

### [14:30:52] assistant
I'm doing well, thank you for asking!

---

## Session 16:00 [ID: conv-def456]

### [16:00:12] user
New conversation after Clear Context
```

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MEMORY_DATA_PATH` | Yes | - | Host path to markdown files |
| `PORT` | No | `8007` | HTTP listening port |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity |
| `MILVUS_URI` | No | `milvus:19530` | Milvus connection URI |

## Requirements

- Docker and Docker Compose
- Milvus v2.5+ (included in docker-compose)
- ~2GB RAM for Milvus + embeddings

## Full Documentation

For comprehensive documentation including:
- Complete API reference with all parameters
- Integration examples (Python, Go, curl)
- Memory types and storage format details
- 80% context flush workflow
- Troubleshooting guide

See **[docs/MEMORY.md](../docs/MEMORY.md)**

# LLMCrawl Visual Overview

Quick visual guide to understanding the LLMCrawl system architecture.

## System at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                      LLMCrawl System                             │
│                                                                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │   Web RAG    │    │ Local Files  │    │  LLM Brain   │     │
│  │   Pipeline   │    │   Pipeline   │    │  (OpenAI)    │     │
│  └──────────────┘    └──────────────┘    └──────────────┘     │
│         │                    │                    │              │
│         └────────────────────┴────────────────────┘              │
│                              │                                    │
│                    ┌─────────▼──────────┐                       │
│                    │   Gateway :8000    │                       │
│                    │   (Orchestrator)   │                       │
│                    └────────┬───────────┘                       │
│            ┌────────────────┼────────────────┐                  │
│            │                │                │                  │
│     ┌──────▼──────┐  ┌─────▼─────┐  ┌──────▼──────┐          │
│     │   Crawler   │  │  Indexer  │  │ MCP Server  │          │
│     │    :8001    │  │   :8002   │  │    :8003    │          │
│     └─────────────┘  └───────────┘  └─────────────┘          │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Request Flow Comparison

### Web RAG Query (News/Web Content)

```
User: "What are the latest NVIDIA earnings?"
  │
  ├─► Gateway detects "latest" (trigger word)
  │
  ├─► Gateway calls LLM with crawl_and_refresh tool
  │
  ├─► LLM decides: "Use crawl_and_refresh"
  │
  ├─► Crawler:
  │     ├─ FireCrawl searches for pages
  │     ├─ Playwright renders JavaScript
  │     └─ Trafilatura extracts text
  │
  ├─► Indexer:
  │     ├─ Chunks into 512-token pieces
  │     ├─ Generates embeddings
  │     └─ Stores in vector DB
  │
  ├─► Indexer retrieves relevant chunks
  │
  ├─► Gateway sends results to LLM
  │
  └─► LLM generates answer with citations
       │
       └─► User receives: "According to NVIDIA's Q3 2024
            earnings report [1], revenue increased..."
```

### Local File Query

```
User: "List files in the src folder"
  │
  ├─► Gateway loads MCP tools
  │
  ├─► Gateway calls LLM with all tools
  │
  ├─► LLM decides: "Use list_files from MCP"
  │
  ├─► MCP Server:
  │     ├─ Validates path security
  │     ├─ Lists files and directories
  │     └─ Returns structured data
  │
  ├─► Gateway sends results to LLM
  │
  └─► LLM formats friendly response
       │
       └─► User receives: "Found 3 files and 48
            directories in src/..."
```

## Tool Selection Matrix

```
Query Type              | Trigger Words/Context      | Tools Loaded           | LLM Decision
─────────────────────────────────────────────────────────────────────────────────────────
"Latest NVIDIA news"    | "latest"                   | crawl + MCP           | crawl_and_refresh
"Recent tech earnings"  | "recent"                   | crawl + MCP           | crawl_and_refresh
"Read README.md"        | "read", filename           | MCP only              | read_local_file
"List files in src"     | "list", "files"            | MCP only              | list_files
"Search for API docs"   | "search", + context        | MCP (if indexed)      | search_file_content
"What is Python?"       | General knowledge          | None                  | Direct LLM
Follow-up: "Tell more"  | Previous context           | Same as previous      | Based on history
```

## Service Communication Map

```
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Network: webrag-network                │
└─────────────────────────────────────────────────────────────────┘

External (Port 8000)
    │
    ▼
┌───────────────┐
│   Gateway     │──────┐
│   :8000       │      │
└───────────────┘      │
    │    │    │        │
    │    │    │        ├─► http://openai.com (LLM API)
    │    │    │        │
    │    │    └────────┼─► http://mcp-server:8003
    │    │             │
    │    └─────────────┼─► http://indexer:8002
    │                  │        │
    └──────────────────┼─► http://crawler:8001
                       │        │
                       │        └─► http://firecrawl:3002
                       │                 │
                       │                 └─► http://redis:6379
                       │
                       └─► http://qdrant:6333

MCP Server Volume:
    C:\os (Windows) → /data/files (Container)
```

## Data Storage Locations

```
Service         | Data Type          | Storage Location              | Persistence
────────────────────────────────────────────────────────────────────────────────
Gateway         | Conversations      | In-memory (24h TTL)          | Temporary
Crawler         | HTML cache         | Redis                        | Temporary
Indexer         | Embeddings         | Qdrant/pgvector              | Persistent
MCP Server      | File data          | Host volume mount            | Persistent
MCP Server      | File index         | /data/mcp_vector_db          | Persistent (optional)
Redis           | Rate limits        | In-memory                    | Temporary
Qdrant          | Vector database    | /qdrant/storage              | Persistent
```

## Security Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                         Internet                                 │
│                         (External)                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  Firewall   │
                    │  Port 8000  │
                    └──────┬──────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│               Docker Network (Internal)                          │
│                                                                   │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐        │
│  │ Gateway │   │ Crawler │   │ Indexer │   │   MCP   │        │
│  │         │   │         │   │         │   │         │        │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘        │
│                                                                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
     ┌────────────────┐      ┌──────────────────┐
     │  Host System   │      │  External APIs   │
     │  C:\os folder  │      │  (OpenAI, etc)   │
     └────────────────┘      └──────────────────┘
          (Read-Only in prod)
```

## MCP Server Path Security

```
Allowed Access:
┌─────────────────────────────────────┐
│  Root: /data/files (mounted)        │
│                                      │
│  ├── documents/          ✓          │
│  │   ├── readme.md      ✓          │
│  │   └── guide.pdf      ✓          │
│  │                                   │
│  ├── src/                ✓          │
│  │   ├── main.py        ✓          │
│  │   └── utils/         ✓          │
│  │       └── helper.py  ✓          │
│  │                                   │
│  └── configs/            ✓          │
│      └── app.yaml       ✓          │
└─────────────────────────────────────┘

Denied Access:
┌─────────────────────────────────────┐
│  /etc/passwd             ✗          │
│  /root/.ssh/             ✗          │
│  C:\Windows\System32     ✗          │
│  /data/files/../../../   ✗          │
│  /proc/                  ✗          │
└─────────────────────────────────────┘
```

## Conversation Flow with Memory

```
Turn 1:
User: "What are the latest NVIDIA earnings?"
  ├─► Gateway: New conversation (generate ID)
  ├─► LLM: Trigger web crawl
  ├─► Response: [earnings data with citations]
  └─► Store: User message + Assistant message

Turn 2:
User: "What about their revenue?"
  ├─► Gateway: Load conversation history
  ├─► Context: Previous NVIDIA earnings discussion
  ├─► LLM: Knows context, references previous data
  ├─► Response: "In the earnings I mentioned..."
  └─► Store: Update conversation

Turn 3 (1 hour later):
User: "Tell me more"
  ├─► Gateway: Load same conversation
  ├─► Context: Full history available
  ├─► LLM: Continues same topic
  └─► Store: Keep updating

Turn N (25 hours later):
User: "Tell me more"
  └─► Gateway: Conversation expired (24h TTL)
      └─► Start new conversation
```

## Resource Usage (Typical)

```
Service          | CPU (Avg) | Memory     | Disk I/O   | Network I/O
─────────────────────────────────────────────────────────────────────
Gateway          | 10-20%    | 200-400 MB | Low        | High
Crawler          | 40-60%    | 500-1000MB | Medium     | High
Indexer          | 15-30%    | 300-500 MB | Medium     | Low
MCP Server       | 5-10%     | 100-200 MB | High       | Low
Qdrant           | 10-20%    | 500-1000MB | High       | Medium
Redis            | 2-5%      | 100-200 MB | Low        | Low
─────────────────────────────────────────────────────────────────────
Total            | ~1.5 CPU  | ~3-4 GB    |            |

Note: CPU percentages are of a single core. Crawler benefits most from
multiple cores due to Playwright rendering.
```

## Development vs Production

```
┌─────────────────────────────┬─────────────────────────────┐
│       Development            │        Production           │
├─────────────────────────────┼─────────────────────────────┤
│ Hot-reload enabled           │ Optimized images            │
│ Code mounted as volumes      │ Code baked into images      │
│ Debug logging               │ Info/Error logging          │
│ Single instance per service  │ Can scale horizontally      │
│ Read-write file access       │ Read-only file access       │
│ Network: webrag-network      │ Network: deploy_webrag      │
│ Container names: *-dev       │ Container names: prod       │
│ MCP: web-rag-mcp-server      │ MCP: mcp-server             │
│ Quick iteration             │ Stable, versioned           │
└─────────────────────────────┴─────────────────────────────┘
```

## Monitoring Stack

```
┌────────────────────────────────────────────────────────────┐
│                    Monitoring Layer                         │
│                                                              │
│  ┌──────────────┐         ┌──────────────┐                │
│  │  Prometheus  │────────▶│   Grafana    │                │
│  │    :9090     │         │    :3001     │                │
│  └──────┬───────┘         └──────────────┘                │
│         │                                                    │
│         │ (scrapes metrics)                                 │
└─────────┼────────────────────────────────────────────────────┘
          │
          ├─► Gateway:8000/metrics
          ├─► Crawler:8001/metrics
          ├─► Indexer:8002/metrics
          ├─► MCP:8003/metrics
          └─► Qdrant:6333/metrics

Grafana Dashboards:
  ├─ Service Health Overview
  ├─ Request Latency Distribution
  ├─ Tool Usage Analytics
  ├─ Error Rate Trends
  └─ Resource Utilization
```

## Quick Reference: Important URLs

```
Service              | URL                              | Purpose
─────────────────────────────────────────────────────────────────────
Gateway              | http://localhost:8000            | Main API
Gateway Health       | http://localhost:8000/health     | Health check
Gateway Chat         | http://localhost:8000/agent/chat| Chat endpoint
Crawler              | http://localhost:8001            | Crawl service
Indexer              | http://localhost:8002            | Index service
MCP Server           | http://localhost:8003            | File operations
MCP Tools List       | http://localhost:8003/tools      | Available tools
Qdrant Dashboard     | http://localhost:6333/dashboard  | Vector DB UI
Grafana              | http://localhost:3001            | Monitoring
Prometheus           | http://localhost:9090            | Metrics
Demo Client          | http://localhost:3000            | Web interface
```

## Common Commands Cheatsheet

```bash
# Start services
cd deploy && docker-compose up -d

# View logs
cd deploy && docker-compose logs -f gateway

# Check health
curl http://localhost:8000/health

# Test web RAG
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Latest tech news"}'

# Test MCP (list files)
curl -X POST http://localhost:8003/invoke \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "list_files", "arguments": {"folder_path": "."}}'

# Stop services
docker-compose down

# Rebuild after changes
docker-compose build gateway
docker-compose up -d gateway

# Check resource usage
docker stats

# Connect to container
docker-compose exec gateway bash
```

---

**For detailed information**, see:
- [Architecture Guide](ARCHITECTURE.md) - Complete system design
- [Deployment Guide](DEPLOYMENT.md) - Deployment instructions
- [Main README](../README.md) - Quick start guide

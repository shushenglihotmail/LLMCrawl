# LLMCrawl Configuration Guide

Complete reference for all LLMCrawl environment variables and settings.

## Table of Contents

- [Quick Start](#quick-start)
- [Configuration File Location](#configuration-file-location)
- [LLM Configuration](#llm-configuration)
  - [Provider Selection](#provider-selection)
  - [Azure OpenAI](#azure-openai)
  - [OpenAI Direct](#openai-direct)
  - [Anthropic Claude (Azure)](#anthropic-claude-azure)
  - [Claude Bridge (Claude CLI)](#claude-bridge-claude-cli)
  - [Model Configuration](#model-configuration)
  - [Embedding Model](#embedding-model)
- [Entra ID Authentication](#entra-id-authentication)
- [Tool Configuration](#tool-configuration)
  - [Azure DevOps MCP](#azure-devops-mcp)
  - [Local File Access MCP](#local-file-access-mcp)
  - [Windows Composition Database](#windows-composition-database)
  - [Tool Call Limits](#tool-call-limits)
- [Memory Service](#memory-service)
- [Web Crawling](#web-crawling)
  - [Domain Allowlist](#domain-allowlist)
  - [Internal Site Authentication](#internal-site-authentication)
- [Vector Database](#vector-database)
- [Service Configuration](#service-configuration)
- [Logging and Caching](#logging-and-caching)
- [Rate Limiting](#rate-limiting)
- [Applying Changes](#applying-changes)
- [Complete Settings Reference](#complete-settings-reference)

---

## Quick Start

```bash
# 1. Navigate to deployment folder
cd llmcrawl-deploy

# 2. Edit configuration
notepad .env        # Windows
nano .env           # Linux/Mac

# 3. Apply changes (restart services)
llmcrawl deploy --down && llmcrawl deploy --up
```

---

## Configuration File Location

**Location:** `llmcrawl-deploy/.env`

```
your-folder/
└── llmcrawl-deploy/
    ├── .env              ← EDIT THIS FILE
    ├── .env.example      ← Reference template
    └── docker-compose.yml
```

The `.env` file is created by `llmcrawl deploy --init`.

---

## LLM Configuration

### Provider Selection

```bash
# Base LLM provider: openai or azure
LLM_PROVIDER=azure
```

| Value | Description |
|-------|-------------|
| `azure` | Azure OpenAI (recommended) |
| `openai` | Direct OpenAI API |

### Azure OpenAI

```bash
# Azure OpenAI endpoint
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/

# API version
AZURE_OPENAI_API_VERSION=2025-01-01-preview

# API Key (optional if using Entra ID authentication)
AZURE_OPENAI_API_KEY=your-key-here
```

### OpenAI Direct

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-key
```

### Anthropic Claude (Azure)

For Claude models hosted on Azure AI Foundry:

```bash
# Anthropic endpoint (Azure AI Foundry)
AZURE_ANTHROPIC_ENDPOINT=https://your-resource.services.ai.azure.com/anthropic/

# Uses same API key as Azure OpenAI (or Entra ID bearer token)
```

### Claude Bridge (Claude CLI)

For routing requests through the locally installed Claude Code CLI:

```bash
# Claude Bridge URL (host-side service)
# Since gateway runs locally, use localhost (not host.docker.internal)
CLAUDE_BRIDGE_URL=http://localhost:8006
```

**Note:** The `start-services.ps1` script automatically sets this to `localhost:8006` for local gateway.

**Setup:**
1. Install Claude Code CLI: `npm install -g @anthropic-ai/claude-code`
2. Start the bridge: `llmcrawl claude-bridge` or `python tools/claude_bridge.py`
3. Models with `provider_type: "claude"` will route through the bridge

### Model Configuration

Configure available models with the `LLM_MODELS` JSON array:

```bash
LLM_MODELS=[
  {
    "name": "gpt-4",
    "display_name": "GPT-4",
    "deployment_name": "gpt-4-deployment",
    "provider_type": "openai",
    "max_output_tokens": 16384
  },
  {
    "name": "claude-sonnet-4-5",
    "display_name": "Claude Sonnet 4.5",
    "deployment_name": "claude-sonnet-4-5",
    "provider_type": "anthropic",
    "max_output_tokens": 64000
  },
  {
    "name": "claude-opus-4-6",
    "display_name": "Claude Opus 4.6 (CLI)",
    "deployment_name": "claude-opus-4-6",
    "provider_type": "claude"
  }
]
```

**Model Properties:**

| Property | Required | Description |
|----------|----------|-------------|
| `name` | Yes | API identifier used in requests |
| `display_name` | Yes | Shown in HiChat UI dropdown |
| `deployment_name` | Yes | Azure deployment name (or model ID for Claude) |
| `provider_type` | Yes | Routing: `openai`, `anthropic`, or `claude` |
| `max_output_tokens` | No | Maximum response tokens (default: 16384 for OpenAI, 64000 for Anthropic) |

**Provider Types:**

| Type | Route | Use For |
|------|-------|---------|
| `openai` | Azure OpenAI or direct OpenAI API | GPT-4, GPT-4o, o1, o3 models |
| `anthropic` | Azure Anthropic endpoint | Claude models on Azure AI Foundry |
| `claude` | Claude Bridge (host-side CLI) | Claude Opus via Claude Code CLI |

### Embedding Model

```bash
# Embedding model for vector search
EMBED_MODEL=text-embedding-3-large
```

---

## Entra ID Authentication

Use Azure Entra ID (OAuth) instead of API keys for Azure AI services:

```bash
# Entra ID Application (client) ID
# Use Azure CLI client ID for broad permissions without admin consent:
ENTRA_CLIENT_ID=04b07795-8ddb-461a-bbee-02f9e1bf7b46

# Entra ID Tenant ID
ENTRA_TENANT_ID=your-tenant-id-here

# Azure Foundry scope for token acquisition
AZURE_FOUNDRY_SCOPE=https://cognitiveservices.azure.com/.default

# JWT validation at gateway (optional, for production)
JWT_VALIDATION_ENABLED=false
```

**How it works:**
1. HiChat acquires bearer token via MSAL browser flow
2. Token is passed to gateway with each request
3. Gateway forwards token to Azure OpenAI/Anthropic endpoints
4. No API keys stored in configuration

See [AUTHENTICATION.md](AUTHENTICATION.md) for detailed Entra ID setup.

---

## Tool Configuration

### Azure DevOps MCP

Allow the agent to search and read code from Azure DevOps:

```bash
# Personal Access Token (required)
AZURE_DEVOPS_PAT=your-pat-here

# Default organization/project (optional, can be overridden per request)
AZURE_DEVOPS_ORG=your-organization
AZURE_DEVOPS_PROJECT=your-project
AZURE_DEVOPS_REPO=your-repo
AZURE_DEVOPS_BRANCH=main
```

**Creating a PAT:**
1. Go to `https://dev.azure.com/{org}/_usersSettings/tokens`
2. Create token with **Code (Read)** and **Code (Search)** scopes
3. Copy token to `.env`

### Local File Access MCP

Allow the agent to read files on your local machine:

```bash
# Host folder to mount (use forward slashes on Windows)
MCP_HOST_FOLDER=C:/src

# Container mount point (don't change)
MCP_ROOT_FOLDER=/data/files

# Vector database for file indexing
MCP_VECTOR_DB_PATH=/data/mcp_vector_db
```

### Windows Composition Database

For querying Windows build component information:

```bash
# WCD Bridge URL (host-side service)
WIN_COMP_BRIDGE_URL=http://host.docker.internal:8005
```

**Setup:**
```powershell
# Start with network share
llmcrawl wcd-bridge --build "\\winbuilds\release\rs_sparc_ctr_exp\29503.1000"

# Or with WCDaaS local mode
llmcrawl wcd-bridge --wcdaas-local --branch rs_sparc_ctr_exp --build-name 29503.1000
```

See [WINDOWS_COMPOSITION_TOOL.md](WINDOWS_COMPOSITION_TOOL.md) for details.

### Tool Call Limits

Control how many times each tool can be called per request:

```bash
# Per-tool limits (JSON object, -1 = unlimited)
TOOL_ROUND_LIMITS={
  "search_azure_devops_code": 30,
  "get_azure_devops_file": 30,
  "crawl_and_refresh": 20,
  "read_local_file": 50,
  "list_files": 50,
  "search_file_content": 50,
  "index_files": 50,
  "query_composition_db": -1
}

# Default limit for tools not specified above
MAX_TOOL_ROUNDS=5

# Code analysis limits
MAX_FILES_PER_REQUEST=80
MAX_INPUT_TOKENS=100000
```

---

## Memory Service

OpenClaw-style long-term memory with auto-distillation:

```bash
# Memory service URL (local service, not Docker)
# Since both gateway and memory-service run locally, use localhost
MEMORY_SERVICE_URL=http://localhost:8007

# Memory data path (local folder for both gateway and memory service)
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

**Architecture Note:** Gateway and Memory Service run as local Python processes (not Docker containers) for direct filesystem access. Only Milvus runs in Docker for vector storage.

**How it works:**
1. Every message is logged to `memory/daily/YYYY-MM-DD.md`
2. When context reaches 80%, a hidden distillation prompt is injected
3. LLM responds with `[SUMMARY]` (session summary) and `[FACTS]` (durable facts)
4. Summary goes to daily log, facts go to `MEMORY.md`
5. `MEMORY.md` is always loaded into the system prompt for new conversations

**Manual Trigger:**
Users can click "Save to Memory" in HiChat to trigger distillation at any time.

See [MEMORY.md](MEMORY.md) for detailed memory service documentation.

---

## Web Crawling

### Domain Allowlist

```bash
# Comma-separated list of allowed domains
ALLOWED_DOMAINS=sec.gov,ft.com,wsj.com,nvidia.com,reuters.com,bloomberg.com

# Respect robots.txt
RESPECT_ROBOTS=true

# Concurrent requests
MAX_CONCURRENCY=4

# Request timeout (milliseconds)
REQUEST_TIMEOUT_MS=20000

# User agent string
USER_AGENT=WebRAG/1.0 (+https://github.com/yourorg/webrag)
```

### Internal Site Authentication

For crawling sites requiring SSO/cookie authentication:

```bash
# Authentication type: none, cookies, headers, basic, bearer
FIRECRAWL_AUTH_TYPE=cookies

# Captured session state (auto-populated by llmcrawl auth command)
FIRECRAWL_AUTH_STORAGE_STATE={"cookies": [...], "origins": [...]}
```

**One-command setup:**
```bash
llmcrawl auth https://internal-site.com
```

This opens a browser, captures cookies after login, and updates `.env` automatically.

See [AUTHENTICATION.md](AUTHENTICATION.md) for details.

---

## Vector Database

```bash
# Vector database type
VECTOR_DB=qdrant
# Options: qdrant, pgvector

# Qdrant URL (default container)
QDRANT_URL=http://qdrant:6333

# PostgreSQL connection (for pgvector)
PG_DSN=postgresql://postgres:password@postgres:5432/rag_db
```

---

## Service Configuration

### Service Ports

```bash
# Change if defaults conflict with other services
GATEWAY_PORT=8000
CRAWLER_PORT=8001
INDEXER_PORT=8002
```

### Service URLs

**Local Services** (gateway runs locally, uses localhost to reach Docker):

```bash
# Docker services accessed from local gateway
CRAWLER_URL=http://localhost:8001
INDEXER_URL=http://localhost:8002
MCP_SERVER_URL=http://localhost:8003
AZURE_DEVOPS_MCP_URL=http://localhost:8004
MEMORY_SERVICE_URL=http://localhost:8007
MILVUS_URI=http://localhost:19530

# Host-side bridge services
CLAUDE_BRIDGE_URL=http://localhost:8006
WIN_COMP_BRIDGE_URL=http://localhost:8005
```

**Note:** Since gateway runs locally (not in Docker), it uses `localhost:PORT` to reach Docker services, not Docker network names like `http://crawler:8001`.

### Container-to-Container URLs

For Docker services communicating with each other:

```bash
# Inside Docker network (used by crawler, indexer, etc.)
FIRECRAWL_URL=http://firecrawl:3002
REDIS_URL=redis://redis:6379/0
```

---

## Logging and Caching

```bash
# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# Log format: json or text
LOG_FORMAT=json

# Redis URL (caching and rate limiting)
REDIS_URL=redis://redis:6379/0

# Cache TTL (seconds)
CACHE_TTL_SECONDS=3600
```

---

## Rate Limiting

```bash
# Requests per minute
RATE_LIMIT_PER_MINUTE=60

# Burst allowance
RATE_LIMIT_BURST=10
```

---

## Applying Changes

**Important:** After editing `.env`, restart services to apply changes.

```bash
# Recommended method
llmcrawl deploy --down
llmcrawl deploy --up

# Alternative (force recreate)
cd llmcrawl-deploy
docker compose up -d --force-recreate
```

**Note:** `docker compose restart` does NOT reload `.env` changes.

---

## Complete Settings Reference

| Variable | Default | Description |
|----------|---------|-------------|
| **LLM Configuration** |||
| `LLM_PROVIDER` | `openai` | Base provider: `openai` or `azure` |
| `AZURE_OPENAI_ENDPOINT` | - | Azure OpenAI resource URL |
| `AZURE_OPENAI_API_KEY` | - | API key (optional with Entra ID) |
| `AZURE_OPENAI_API_VERSION` | `2025-01-01-preview` | Azure OpenAI API version |
| `AZURE_ANTHROPIC_ENDPOINT` | - | Azure Anthropic endpoint URL |
| `OPENAI_API_KEY` | - | Direct OpenAI API key |
| `LLM_MODELS` | `[]` | JSON array of available models |
| `EMBED_MODEL` | `text-embedding-3-large` | Embedding model |
| `CLAUDE_BRIDGE_URL` | - | Claude Code CLI bridge URL |
| **Entra ID Auth** |||
| `ENTRA_CLIENT_ID` | - | Azure AD application ID |
| `ENTRA_TENANT_ID` | - | Azure AD tenant ID |
| `AZURE_FOUNDRY_SCOPE` | - | Token scope for Azure AI |
| `JWT_VALIDATION_ENABLED` | `false` | Validate JWT tokens at gateway |
| **Tool Configuration** |||
| `AZURE_DEVOPS_PAT` | - | Azure DevOps Personal Access Token |
| `AZURE_DEVOPS_ORG` | - | Default Azure DevOps organization |
| `AZURE_DEVOPS_PROJECT` | - | Default Azure DevOps project |
| `AZURE_DEVOPS_REPO` | - | Default repository |
| `AZURE_DEVOPS_BRANCH` | `main` | Default branch |
| `WIN_COMP_BRIDGE_URL` | - | WCD Bridge service URL |
| `TOOL_ROUND_LIMITS` | `{}` | Per-tool call limits (JSON) |
| `MAX_TOOL_ROUNDS` | `5` | Default tool call limit |
| `MAX_FILES_PER_REQUEST` | `80` | Max files for code analysis |
| `MAX_INPUT_TOKENS` | `100000` | Max input tokens |
| **MCP Server** |||
| `MCP_HOST_FOLDER` | `./data/files` | Host folder to mount |
| `MCP_ROOT_FOLDER` | `/data/files` | Container mount point |
| `MCP_VECTOR_DB_PATH` | `/data/mcp_vector_db` | MCP vector DB path |
| **Memory Service** |||
| `MEMORY_SERVICE_URL` | `http://localhost:8007` | Memory service URL (local service) |
| `MEMORY_DATA_PATH` | `deploy/memory` | Memory data path (local folder) |
| `MILVUS_URI` | `http://localhost:19530` | Milvus vector DB URL |
| `MEMORY_AUTO_LOG` | `true` | Auto-log messages to daily log |
| `MEMORY_AUTO_FLUSH` | `true` | Auto-distill at 80% context |
| `MEMORY_FLUSH_THRESHOLD` | `0.8` | Context threshold for distillation |
| **Web Crawling** |||
| `ALLOWED_DOMAINS` | - | Comma-separated domain allowlist |
| `RESPECT_ROBOTS` | `true` | Respect robots.txt |
| `MAX_CONCURRENCY` | `4` | Concurrent crawl requests |
| `REQUEST_TIMEOUT_MS` | `20000` | Request timeout (ms) |
| `USER_AGENT` | `WebRAG/1.0` | User agent string |
| `FIRECRAWL_AUTH_TYPE` | `none` | Auth type: none/cookies/headers/basic/bearer |
| `FIRECRAWL_AUTH_STORAGE_STATE` | - | Captured auth cookies (JSON) |
| **Vector Database** |||
| `VECTOR_DB` | `qdrant` | Vector DB: `qdrant` or `pgvector` |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant URL |
| `PG_DSN` | - | PostgreSQL connection string |
| **Services** |||
| `GATEWAY_PORT` | `8000` | Gateway port |
| `CRAWLER_PORT` | `8001` | Crawler port |
| `INDEXER_PORT` | `8002` | Indexer port |
| `FIRECRAWL_URL` | `http://firecrawl:3002` | Firecrawl URL |
| **Logging & Cache** |||
| `LOG_LEVEL` | `INFO` | Log level |
| `LOG_FORMAT` | `json` | Log format: json/text |
| `REDIS_URL` | `redis://redis:6379/0` | Redis URL |
| `CACHE_TTL_SECONDS` | `3600` | Cache TTL |
| **Rate Limiting** |||
| `RATE_LIMIT_PER_MINUTE` | `60` | Requests per minute |
| `RATE_LIMIT_BURST` | `10` | Burst allowance |

---

## Related Documentation

- **[INSTALL.md](INSTALL.md)** - Installation and setup guide
- **[AUTHENTICATION.md](AUTHENTICATION.md)** - Entra ID and internal site authentication
- **[DIAGNOSTICS.md](DIAGNOSTICS.md)** - Monitoring and troubleshooting
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design and workflows

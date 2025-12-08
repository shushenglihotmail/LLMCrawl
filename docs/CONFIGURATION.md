# LLMCrawl Configuration Guide

Complete guide for configuring LLMCrawl environment variables and settings.

## Table of Contents

- [Quick Start](#quick-start)
- [Configuration File Location](#configuration-file-location)
- [Required Configuration](#required-configuration)
- [LLM Configuration](#llm-configuration)
- [Tool Configuration](#tool-configuration)
- [Service Configuration](#service-configuration)
- [Vector Database](#vector-database)
- [Logging and Cache](#logging-and-cache)
- [Applying Changes](#applying-changes)
- [Troubleshooting](#troubleshooting)
- [Security Best Practices](#security-best-practices)

---

## Quick Start

```bash
# 1. Navigate to deployment folder
cd llmcrawl-deploy

# 2. Edit configuration
notepad .env        # Windows
# or: nano .env     # Linux/Mac

# 3. Apply changes (restart services)
llmcrawl deploy --down
llmcrawl deploy --up
```

---

## Configuration File Location

**⚠️ IMPORTANT:** Configuration is in `llmcrawl-deploy/.env`

```
your-folder/
└── llmcrawl-deploy/
    ├── .env              ← EDIT THIS FILE
    ├── .env.example      ← Reference (copy to .env if missing)
    ├── docker-compose.yml
    └── ...
```

The `.env` file was created when you ran `llmcrawl deploy --init`.

---

## Required Configuration

At minimum, configure one LLM provider:

### Option A: Azure OpenAI (Recommended)

```bash
# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY=your-azure-openai-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
LLM_PROVIDER=azure

# Model Configuration (JSON array)
LLM_MODELS=[{"name":"gpt-4","display_name":"GPT-4","deployment_name":"your-gpt4-deployment","provider_type":"openai"}]
```

### Option B: OpenAI Direct

```bash
# OpenAI Configuration
OPENAI_API_KEY=sk-your-openai-key
LLM_PROVIDER=openai
```

### Option C: Anthropic Claude (via Azure)

```bash
# Azure with Anthropic
AZURE_ANTHROPIC_ENDPOINT=https://your-resource.services.ai.azure.com/anthropic/
AZURE_OPENAI_API_KEY=your-azure-key

# Add Claude to models
LLM_MODELS=[{"name":"claude-sonnet","display_name":"Claude Sonnet","deployment_name":"claude-sonnet","provider_type":"anthropic"}]
```

---

## LLM Configuration

### Available Models

Configure multiple models for user selection:

```bash
# JSON array of available models
LLM_MODELS=[
  {"name":"gpt-4","display_name":"GPT-4","deployment_name":"gpt-4-deployment","provider_type":"openai"},
  {"name":"gpt-4o","display_name":"GPT-4o","deployment_name":"gpt-4o-deployment","provider_type":"openai"},
  {"name":"claude-sonnet","display_name":"Claude Sonnet","deployment_name":"claude-sonnet","provider_type":"anthropic"}
]
```

**Model Properties:**
- `name`: Internal identifier
- `display_name`: Shown in UI
- `deployment_name`: Azure deployment name (must match your Azure resource)
- `provider_type`: `openai` or `anthropic`

### Embedding Model

```bash
# OpenAI embedding model
EMBED_MODEL=text-embedding-3-large

# Or Azure embedding deployment
AZURE_EMBED_DEPLOYMENT=text-embedding-3-large
```

### Context and Token Limits

```bash
# Maximum context tokens (depends on model)
MAX_CONTEXT_TOKENS=128000

# Maximum input tokens for code analysis
MAX_INPUT_TOKENS=100000
```

---

## Tool Configuration

### Azure DevOps Integration

```bash
# Personal Access Token (required for Azure DevOps tools)
AZURE_DEVOPS_PAT=your-pat-here

# Default settings (can be overridden per request)
AZURE_DEVOPS_ORG=your-organization
AZURE_DEVOPS_PROJECT=your-project
AZURE_DEVOPS_REPO=your-repo
AZURE_DEVOPS_BRANCH=main
```

**How to create a PAT:**
1. Go to `https://dev.azure.com/{your-org}/_usersSettings/tokens`
2. Create new token with **Code (Read)** scope
3. Copy the token to `.env`

### Local File Access (MCP Server)

```bash
# Host folder to mount (accessible to LLM)
# Windows: Use forward slashes
MCP_HOST_FOLDER=C:/src

# Linux/Mac:
# MCP_HOST_FOLDER=/home/user/src
```

### Tool Call Limits

```bash
# Per-tool call limits (JSON object)
# -1 = unlimited
TOOL_ROUND_LIMITS={"search_azure_devops_code":30,"get_azure_devops_file":30,"crawl_and_refresh":20,"read_local_file":50,"list_files":50,"search_file_content":50}

# Default limit for tools not specified above
MAX_TOOL_ROUNDS=5

# Maximum files per code analysis request
MAX_FILES_PER_REQUEST=80
```

### Windows Composition Database (WCD)

```bash
# WCD Bridge URL (if running wcd-bridge on host)
WIN_COMP_BRIDGE_URL=http://host.docker.internal:8005
```

---

## Service Configuration

### Service Ports

```bash
# Change ports if defaults conflict with other services
GATEWAY_PORT=8000
CRAWLER_PORT=8001
INDEXER_PORT=8002
MCP_SERVER_PORT=8003
HICHAT_PORT=8080
```

### Internal Service URLs

These are used for container-to-container communication:

```bash
# Usually don't need to change these
CRAWLER_URL=http://crawler:8001
INDEXER_URL=http://indexer:8002
MCP_SERVER_URL=http://mcp-server:8003
AZURE_DEVOPS_MCP_URL=http://azure-devops-mcp-server:8004
```

### Web Crawling

```bash
# Allowed domains for crawling (comma-separated)
ALLOWED_DOMAINS=example.com,docs.microsoft.com

# Respect robots.txt
RESPECT_ROBOTS=true

# Concurrent crawl requests
MAX_CONCURRENCY=4

# Request timeout (milliseconds)
REQUEST_TIMEOUT_MS=20000

# Gateway timeout (seconds)
GATEWAY_TIMEOUT=45

# Crawler timeout (seconds)
CRAWLER_TIMEOUT=25
```

### Authentication for Internal Sites

```bash
# Authentication type: none, cookies, headers, basic
FIRECRAWL_AUTH_TYPE=cookies

# Test URL for auth verification
AUTH_TEST_URL=https://internal-site.com

# Captured session state (set by llmcrawl auth command)
FIRECRAWL_AUTH_STORAGE_STATE=<captured_state>
```

> **Tip:** Use `llmcrawl auth <url>` to automatically capture and configure authentication cookies.

---

## Vector Database

```bash
# Vector database type: qdrant or pgvector
VECTOR_DB=qdrant

# Qdrant URL (default, runs in container)
QDRANT_URL=http://qdrant:6333

# PostgreSQL (for pgvector)
# PG_DSN=postgresql://user:password@postgres:5432/rag_db
```

---

## Logging and Cache

```bash
# Log level: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# Log format: json or text
LOG_FORMAT=json

# Redis URL (for caching)
REDIS_URL=redis://redis:6379/0

# Cache TTL (seconds)
CACHE_TTL_SECONDS=3600
```

---

## Applying Changes

**⚠️ IMPORTANT:** After editing `.env`, you must restart services to apply changes.

### Using llmcrawl CLI

```bash
# Recommended: Stop and start
llmcrawl deploy --down
llmcrawl deploy --up
```

### Using Docker Compose Directly

```bash
cd llmcrawl-deploy

# Force recreate to reload .env
docker compose up -d --force-recreate
```

> **Note:** `docker compose restart` does NOT reload `.env` changes!

---

## Troubleshooting

### Changes Not Applied

**Problem:** Modified `.env` but services still use old values

**Solution:**
```bash
# Stop completely and restart
llmcrawl deploy --down
llmcrawl deploy --up
```

### Missing API Key Error

**Problem:** "Invalid API key" or "API key not found"

**Solution:**
```bash
# Check if key is set in .env
cd llmcrawl-deploy
grep API_KEY .env

# Verify no typos, extra spaces, or quotes around value
# CORRECT:
OPENAI_API_KEY=sk-abc123

# WRONG:
OPENAI_API_KEY="sk-abc123"   # No quotes!
OPENAI_API_KEY= sk-abc123    # No leading space!
```

### Model Not Found

**Problem:** "Deployment not found" or "Model not found"

**Solution:**
1. Verify deployment name in Azure Portal matches `deployment_name` in `LLM_MODELS`
2. Check the model JSON is valid (no trailing commas, proper quotes)
3. Ensure `provider_type` is correct (`openai` or `anthropic`)

### Azure DevOps 401 Error

**Problem:** "Unauthorized" when using Azure DevOps tools

**Solution:**
1. Verify PAT hasn't expired
2. Check PAT has **Code (Read)** scope
3. Ensure `AZURE_DEVOPS_PAT` is set correctly in `.env`

### Port Already in Use

**Problem:** "Port 8000 is already in use"

**Solution:**
```bash
# Option 1: Stop conflicting service
# Option 2: Change port in .env
GATEWAY_PORT=8100
```

---

## Security Best Practices

1. **Never commit `.env`** - It's in `.gitignore` for a reason
2. **Use environment variables** - Don't hardcode credentials in code
3. **Rotate credentials regularly** - Update API keys and PATs periodically
4. **Use separate configurations** - Different `.env` for dev/staging/prod
5. **Limit file access** - Only mount necessary folders in `MCP_HOST_FOLDER`
6. **Restrict domains** - Use `ALLOWED_DOMAINS` to limit crawlable sites

---

## Complete .env Example

See `llmcrawl-deploy/.env.example` for a complete example with all options.

```bash
# View example configuration
cat llmcrawl-deploy/.env.example
```

---

## Related Documentation

- **[INSTALL.md](../INSTALL.md)** - Installation and setup guide
- **[DIAGNOSTICS.md](DIAGNOSTICS.md)** - Troubleshooting and debugging
- **[MONITORING.md](MONITORING.md)** - Metrics and dashboards

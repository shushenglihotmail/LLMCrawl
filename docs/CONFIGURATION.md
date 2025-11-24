# LLMCrawl Configuration Guide

## Environment Variables Location

**⚠️ IMPORTANT: Use `deploy/.env` for all configuration**

All Docker services read environment variables from **`deploy/.env`** only. Do not create a `.env` file in the root directory.

```
LLMCrawl/
├── deploy/
│   └── .env              ← USE THIS FILE (services read from here)
└── .env                  ← DO NOT CREATE (ignored by services)
```

## Quick Start

1. **Copy the example file:**
   ```bash
   cd deploy
   cp .env.example .env
   ```

2. **Edit `deploy/.env`** with your credentials:
   ```bash
   # Required: Azure OpenAI credentials
   AZURE_OPENAI_API_KEY=your-key-here
   AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/

   # Required: Azure DevOps PAT (if using Azure DevOps MCP)
   AZURE_DEVOPS_PAT=your-pat-here
   ```

3. **Start services:**
   ```bash
   docker compose up -d
   ```

4. **After changing `.env`, recreate containers:**
   ```bash
   docker compose up -d --force-recreate
   ```
   > **Note:** `docker compose restart` does NOT reload `.env` changes!

## Configuration Sections

### 1. LLM Configuration

```env
# Azure OpenAI (Recommended)
AZURE_OPENAI_API_KEY=your-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_OPENAI_API_VERSION=2025-01-01-preview
AZURE_ANTHROPIC_ENDPOINT=https://your-resource.services.ai.azure.com/anthropic/
LLM_PROVIDER=azure

# Available Models (JSON array)
LLM_MODELS=[
  {"name":"gpt-5-chat","display_name":"GPT-5 Chat","deployment_name":"gpt-5-chat","provider_type":"openai"},
  {"name":"claude-sonnet-4-5","display_name":"Claude Sonnet 4-5","deployment_name":"claude-sonnet-4-5","provider_type":"anthropic"}
]

# Embedding Model
EMBED_MODEL=text-embedding-3-large
```

### 2. Azure DevOps MCP Server

```env
# Personal Access Token (required for Azure DevOps integration)
AZURE_DEVOPS_PAT=your-pat-here

# Default branch (optional, can be overridden per request)
AZURE_DEVOPS_BRANCH=main
```

### 3. Tool Configuration

```env
# Maximum rounds of tool calls per request
MAX_TOOL_ROUNDS=5

# Code Intelligence Agent limits
MAX_FILES_PER_REQUEST=80
MAX_INPUT_TOKENS=100000
```

### 4. Vector Database

```env
VECTOR_DB=qdrant
QDRANT_URL=http://qdrant:6333
PG_DSN=postgresql://postgres:password@postgres:5432/rag_db
```

### 5. Firecrawl Configuration

```env
FIRECRAWL_URL=http://firecrawl:3002
FIRECRAWL_API_KEY=your_firecrawl_key_here

# Authentication (optional, for authenticated sites)
FIRECRAWL_AUTH_TYPE=none
# FIRECRAWL_AUTH_TYPE=cookies
# AUTH_TEST_URL=https://your-site.com
# FIRECRAWL_AUTH_STORAGE_STATE=<captured_session_state>
```

### 6. Web Crawling

```env
ALLOWED_DOMAINS=sec.gov,ft.com,wsj.com,nvidia.com
RESPECT_ROBOTS=true
MAX_CONCURRENCY=4
REQUEST_TIMEOUT_MS=20000
```

### 7. Service URLs

```env
# Internal service endpoints (Docker network)
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8000
CRAWLER_HOST=0.0.0.0
CRAWLER_PORT=8001
INDEXER_HOST=0.0.0.0
INDEXER_PORT=8002
MCP_SERVER_URL=http://mcp-server:8003
AZURE_DEVOPS_MCP_URL=http://azure-devops-mcp-server:8004
```

### 8. MCP Server (Local Files)

```env
MCP_ROOT_FOLDER=/data/files
MCP_VECTOR_DB_PATH=/data/mcp_vector_db
```

### 9. Logging & Cache

```env
LOG_LEVEL=INFO
LOG_FORMAT=json
REDIS_URL=redis://redis:6379/0
CACHE_TTL_SECONDS=3600
```

## Docker Compose Reference

The `deploy/docker-compose.yml` file:
- Reads environment variables from `deploy/.env` (relative path: `env_file: - .env`)
- All services use these same environment variables
- Changes to `.env` require `docker compose up -d --force-recreate`

## Troubleshooting

### Changes Not Applied
**Problem:** Modified `.env` but services still use old values

**Solution:** Use `--force-recreate` to reload environment:
```bash
cd deploy
docker compose up -d --force-recreate
```

### Wrong .env File
**Problem:** Created `.env` in root directory

**Solution:** Delete root `.env` and use `deploy/.env` only:
```bash
rm .env
cd deploy
# Edit deploy/.env instead
```

### Missing Configuration
**Problem:** Service fails with "missing environment variable"

**Solution:** Check `deploy/.env` has the required variable:
```bash
cd deploy
grep VARIABLE_NAME .env
```

## Security Best Practices

1. **Never commit** `deploy/.env` to git (already in `.gitignore`)
2. **Protect API keys** - Use environment variables, not hardcoded values
3. **Rotate credentials** regularly (PATs, API keys)
4. **Use separate** dev/prod configurations

## Related Documentation

- [README.md](../README.md) - Main project documentation
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [deploy/.env.example](../deploy/.env.example) - Example configuration file
- [MULTI_PROVIDER_LLM.md](MULTI_PROVIDER_LLM.md) - LLM provider setup
- [tools/msauth/README.md](../tools/msauth/README.md) - Firecrawl authentication
- [mcp_servers/azure_devops_mcp_server/README.md](../mcp_servers/azure_devops_mcp_server/README.md) - Azure DevOps MCP setup

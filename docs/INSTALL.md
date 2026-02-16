# LLMCrawl Installation Guide

This guide walks you through installing and running LLMCrawl on a fresh machine.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Initialize Deployment](#initialize-deployment)
4. [Configuration](#configuration)
5. [Start Services](#start-services)
6. [Verify Installation](#verify-installation)
7. [Optional Components](#optional-components)
8. [Management Commands](#management-commands)
9. [Upgrading](#upgrading)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before installing LLMCrawl, ensure you have the following:

### Required Software

| Software | Version | Download |
|----------|---------|----------|
| **Docker Desktop** | 4.0+ | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop) |
| **Python** | 3.10+ | [python.org/downloads](https://www.python.org/downloads/) |

### API Keys (at least one required)

| Provider | How to Get |
|----------|------------|
| **OpenAI** | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| **Azure OpenAI** | [Azure Portal](https://portal.azure.com) → Create OpenAI resource |
| **Anthropic** | [console.anthropic.com](https://console.anthropic.com/) |

### Verify Prerequisites

```bash
# Check Docker is running
docker --version
# Expected: Docker version 24.0.0 or higher

# Check Docker Compose
docker compose version
# Expected: Docker Compose version v2.0.0 or higher

# Check Python
python --version
# Expected: Python 3.10.0 or higher
```

> **Important**: Make sure Docker Desktop is **running** before proceeding.

---

## Installation

### Step 1: Create a Working Directory

```bash
# Create a folder for LLMCrawl
mkdir llmcrawl
cd llmcrawl
```

### Step 2: Create and Activate Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate the virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Windows (Command Prompt):
.\venv\Scripts\activate.bat

# Linux/Mac:
source venv/bin/activate
```

You should see `(venv)` in your terminal prompt when activated.

### Step 3: Install LLMCrawl

#### Option A: Install from Wheel File (Recommended)

```bash
# Install the wheel (adjust version number as needed)
pip install llmcrawl-1.0.1-py3-none-any.whl

# Verify installation
llmcrawl --help
```

#### Option B: Install from Source

```bash
# Clone or extract the source code
git clone https://github.com/your-org/LLMCrawl.git
cd LLMCrawl

# Install in development mode
pip install -e .

# Verify installation
llmcrawl --help
```

---

## Initialize Deployment

This step creates a deployment folder with all necessary configuration files.

```bash
# Initialize the deployment folder
llmcrawl deploy --init
```

This creates a `llmcrawl-deploy/` folder in your current directory:

```
llmcrawl-deploy/
├── docker-compose.yml      # Docker service orchestration
├── .env                    # Your configuration (edit this!)
├── .env.example            # Reference configuration
├── Dockerfile.*            # Service build files
├── prometheus.yml          # Monitoring config
├── grafana-provisioning/   # Grafana dashboards
├── gateway/                # Gateway service code
├── crawler/                # Crawler service code
├── indexer/                # Indexer service code
├── mcp_servers/            # MCP server code
├── data/files/             # Default MCP file mount point
├── logs/                   # Service logs
└── docs/                   # Documentation
```

> **Note**: Run `llmcrawl deploy --init` only once. To update an existing deployment after upgrading the wheel, use `llmcrawl deploy --upgrade` instead.

---

## Configuration

### Step 1: Navigate to Deployment Folder

```bash
cd llmcrawl-deploy
```

### Step 2: Edit Configuration

Open `.env` in your preferred editor:

```bash
# Windows
notepad .env

# Linux/Mac
nano .env
```

### Step 3: Configure LLM Provider (Required)

You need **at least one** LLM provider configured:

#### Option A: OpenAI Direct

```bash
OPENAI_API_KEY=sk-your-openai-key-here
LLM_PROVIDER=openai
```

#### Option B: Azure OpenAI

```bash
AZURE_OPENAI_API_KEY=your-azure-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview
LLM_PROVIDER=azure
```

#### Option C: Anthropic Claude (via Azure AI)

```bash
AZURE_ANTHROPIC_ENDPOINT=https://your-resource.services.ai.azure.com/anthropic/
AZURE_OPENAI_API_KEY=your-azure-key-here
LLM_PROVIDER=azure
```

### Step 4: Configure Available Models

Edit the `LLM_MODELS` setting to define which models are available:

```bash
# Example: Single model
LLM_MODELS=[{"name":"gpt-4","display_name":"GPT-4","deployment_name":"gpt-4","provider_type":"openai"}]

# Example: Multiple models
LLM_MODELS=[{"name":"gpt-4","display_name":"GPT-4","deployment_name":"gpt-4","provider_type":"openai"},{"name":"claude-sonnet","display_name":"Claude Sonnet","deployment_name":"claude-sonnet","provider_type":"anthropic"}]
```

### Optional Settings

```bash
# Service Ports (change if defaults conflict)
GATEWAY_PORT=8000
HICHAT_PORT=8080

# Logging level
LOG_LEVEL=INFO              # Options: DEBUG, INFO, WARNING, ERROR

# Local file access (path for MCP server to read)
MCP_HOST_FOLDER=C:/src      # Windows: Use forward slashes
```

---

## Start Services

### Start All Services

From the **parent folder** of `llmcrawl-deploy/` (or from anywhere if you specify `--dir`):

```bash
# Go back to parent folder
cd ..

# Start services
llmcrawl deploy --up
```

Or specify the deployment directory explicitly:

```bash
llmcrawl deploy --up --dir ./llmcrawl-deploy
```

### First-Time Startup

The first startup takes **5-10 minutes** as Docker:
1. Downloads base images (PostgreSQL, Qdrant, Redis, Python, etc.)
2. Builds the LLMCrawl service images

Subsequent starts are much faster (under 30 seconds).

### Expected Output

```
🚀 Starting LLMCrawl services...
🐳 Running: docker compose -f docker-compose.yml up --build -d

✅ Services started successfully!

Access points:
  • HiChat Web UI:    http://localhost:8080
  • Gateway API:      http://localhost:8000
  • Gateway Docs:     http://localhost:8000/docs
  • Qdrant Dashboard: http://localhost:6333/dashboard
```

---

## Verify Installation

### Quick Health Check

After starting services, run the health check to verify all services are responding:

```bash
llmcrawl deploy --health
```

**Expected output:**

```
============================================================
          LLMCrawl Service Health Check
============================================================

🔍 Gateway (port 8000)
----------------------------------------
   Status: ✅ HEALTHY
   Service: llmcrawl-gateway

🔍 Crawler (port 8001)
----------------------------------------
   Status: ✅ HEALTHY
   Service: llmcrawl-crawler
   Components:
     - playwright: ✅ healthy
     - firecrawl: ✅ healthy

🔍 Indexer (port 8002)
----------------------------------------
   Status: ✅ HEALTHY
   Vector Store: ✅ healthy

🔍 MCP Server (port 8003)
----------------------------------------
   Status: ✅ HEALTHY

🔍 Qdrant (port 6333)
----------------------------------------
   Status: ✅ HEALTHY

============================================================
   Summary: ✅ 6/7 services healthy
============================================================
```

> **Note**: Some services like Azure DevOps MCP (port 8004) or Playwright (port 3000) may show as unreachable if not configured - this is normal.

### 1. Check Service Status

```bash
llmcrawl deploy --status
```

All services should show as "running".

### 2. Open HiChat Web Interface

Open your browser to: **http://localhost:8080**

1. Select a model from the dropdown
2. Type a message like "Hello, what can you help me with?"
3. You should receive a response from the LLM

### 3. Check API Documentation

Open: **http://localhost:8000/docs**

This shows the interactive API documentation for the Gateway service.

### 4. View Logs (if issues)

```bash
# View all service logs
llmcrawl deploy --logs

# View specific service logs
llmcrawl deploy --logs gateway
```

---

## Optional Components

These components can be enabled based on your needs.

### HiChat Web Client (Standalone)

The HiChat web client is included in the Docker services and accessible at http://localhost:8080. However, you can also run it standalone for development or when using Entra ID authentication with Azure Foundry.

#### Using HiChat CLI (Production)

After installing the wheel package, HiChat CLI is available:

```bash
# Run with default settings (loads from llmcrawl-deploy/.env)
hichat

# Specify custom deploy directory
hichat --deploy-dir /path/to/llmcrawl-deploy

# Custom port and gateway
hichat --port 3000 --gateway http://my-gateway:8000

# Don't auto-open browser
hichat --no-browser
```

**Environment Configuration:**

HiChat automatically searches for `.env` in these locations (in order):
1. Path specified via `--deploy-dir`
2. Current directory (`./env`)
3. `./llmcrawl-deploy/.env`
4. User home directory (`~/.llmcrawl/.env`)

**Setup for Production:**

```bash
# Option 1: Use llmcrawl-deploy folder (recommended)
mkdir llmcrawl-deploy
cp /path/to/deploy/.env llmcrawl-deploy/
hichat

# Option 2: Use home directory
mkdir -p ~/.llmcrawl
cp /path/to/deploy/.env ~/.llmcrawl/
hichat

# Option 3: Specify deploy directory
hichat --deploy-dir ./llmcrawl-deploy
```

#### Running from Source (Development)

For development, use the helper script:

```bash
# From repository root
.\scripts\start_hichat.ps1

# Or manually
cd clients/hichat
python main.py --deploy-dir ../../deploy
```

#### Entra ID Authentication

If using Azure Foundry with Entra ID authentication, configure in `.env`:

```bash
# Azure Entra ID settings (use Azure CLI client ID for broad permissions)
ENTRA_CLIENT_ID=04b07795-8ddb-461a-bbee-02f9e1bf7b46
ENTRA_TENANT_ID=your-tenant-id
AZURE_FOUNDRY_SCOPE=https://cognitiveservices.azure.com/user_impersonation

# Azure Foundry endpoints
AZURE_OPENAI_ENDPOINT=https://your-foundry.cognitiveservices.azure.com/
AZURE_ANTHROPIC_ENDPOINT=https://your-foundry-anthropic.cognitiveservices.azure.com/

# Leave API keys empty to use bearer tokens
AZURE_OPENAI_API_KEY=
```

On first request, HiChat will:
1. Open a browser for Microsoft sign-in
2. Cache the token at `~/.llmcrawl/token_cache.bin`
3. Automatically refresh tokens on subsequent runs
4. Pass bearer token to gateway → Azure Foundry

See [AUTHENTICATION.md](AUTHENTICATION.md) for more details on Entra ID setup.

---

### Monitoring (Prometheus + Grafana)

For visual dashboards and metrics:

```bash
# Start services with monitoring
llmcrawl deploy --up --profile monitoring
```

Access points:
- **Grafana**: http://localhost:3001 (admin/admin)
- **Prometheus**: http://localhost:9090

See [DIAGNOSTICS.md](DIAGNOSTICS.md) for monitoring setup.

---

### Local File Access (MCP Server)

Allow the agent to read files on your local machine.

**Configuration** in `.env`:

```bash
# Path to expose (use forward slashes on Windows)
MCP_HOST_FOLDER=C:/src
```

The agent can then read, list, and search files within this folder.

---

### Azure DevOps Integration

Allow the agent to search and read code from Azure DevOps repositories.

**Setup:**

1. Create a Personal Access Token (PAT) at:
   `https://dev.azure.com/[your-org]/_usersSettings/tokens`

2. Required scopes: **Code (Read)**, optionally **Code (Search)**

3. Configure in `.env`:

```bash
AZURE_DEVOPS_PAT=your-pat-token-here
AZURE_DEVOPS_ORG=your-org
AZURE_DEVOPS_PROJECT=your-project
```

---

### Internal Site Authentication

To crawl internal sites requiring authentication (e.g., wikis behind SSO):

**One-time setup:**

```bash
# Install auth tool dependencies
pip install playwright httpx requests
playwright install chromium
```

**Authenticate to a site:**

```bash
# Option 1: Run from the deployment folder
cd llmcrawl-deploy
llmcrawl auth https://www.osgwiki.com/wiki/Main_Page

# Option 2: Specify deployment directory with --dir
llmcrawl auth https://www.osgwiki.com/wiki/Main_Page --dir ./llmcrawl-deploy
```

This opens Edge, lets you log in, captures cookies, and updates `.env` automatically.

**Additional options:**

```bash
# Skip auto-apply (just save cookies to .auth/ folder)
llmcrawl auth https://internal-site.com --dir ./llmcrawl-deploy --no-apply

# Skip container restart after applying
llmcrawl auth https://internal-site.com --dir ./llmcrawl-deploy --no-restart
```

See [AUTHENTICATION.md](AUTHENTICATION.md) for detailed instructions.

---

### Windows Composition Database (WCD) Tool

Query Windows build component information. Requires Windows host.

**Option A: Network Share Mode**

Use this if you have access to Windows build network shares:

```bash
llmcrawl wcd-bridge --build "\\winbuilds\release\rs_sparc_ctr_exp\29498.1001.251201-1700"
```

**Option B: WCDaaS Local Mode (Recommended)**

Use this if network shares are unavailable or slow. First, download the WCD tools by opening this URL in your browser:

```
https://wcdaas-pme.azurewebsites.net/default.aspx?action=wcd&branch=rs_sparc_ctr_exp&buildName=29503.1000.251209-1700&arch=amd64
```

Then start the bridge with local mode:

```bash
llmcrawl wcd-bridge --wcdaas-local --branch rs_sparc_ctr_exp --build-name 29503.1000.251209-1700
```

Options:
- `--branch` - WCD branch name (default: rs_sparc_ctr_exp)
- `--build-name` - Build name (e.g., 29503.1000.251209-1700)
- `--arch` - Architecture (default: amd64fre, also: arm64fre)

**Configure in `.env`:**

```bash
WIN_COMP_BRIDGE_URL=http://host.docker.internal:8005
```

Keep the bridge running in a separate terminal while using WCD queries.

---

### Claude Bridge (Claude Code CLI)

Route LLM requests through the Claude Code CLI on the host machine. This enables Docker-based gateway containers to use Claude models via the locally installed `claude.exe`.

**Prerequisites:**
- Claude Code CLI installed (`claude.exe` available in `%USERPROFILE%\.claude-cli\currentVersion\` or system PATH)

**Start the bridge:**

```bash
# Default (port 8006, auto-detect claude CLI)
llmcrawl claude-bridge

# Custom port
llmcrawl claude-bridge --port 8007

# Explicit Claude CLI path
llmcrawl claude-bridge --claude-path "C:\Users\you\.claude-cli\currentVersion\claude.exe"
```

Options:
- `--port`, `-p` - Port to run the bridge on (default: 8006)
- `--claude-path` - Full path to `claude` CLI executable (auto-detected if not specified)

**Auto-detection order** for Claude CLI:
1. `CLAUDE_CLI_PATH` environment variable
2. `%USERPROFILE%\.claude-cli\currentVersion\claude.exe` (Windows)
3. System PATH

**Configure in `.env`:**

```bash
CLAUDE_BRIDGE_URL=http://host.docker.internal:8006
```

Keep the bridge running in a separate terminal while using Claude models.

---

## Management Commands

### Service Control

| Task | Command |
|------|---------|
| Start all services | `llmcrawl deploy --up` |
| Stop all services | `llmcrawl deploy --down` |
| Stop specific service | `llmcrawl deploy --stop gateway` |
| Restart all services | `llmcrawl deploy --restart` |
| Restart specific service | `llmcrawl deploy --restart gateway` |
| Restart with rebuild | `llmcrawl deploy --restart gateway --build` |
| View status | `llmcrawl deploy --status` |
| View logs | `llmcrawl deploy --logs` |
| View specific logs | `llmcrawl deploy --logs gateway` |

### Development Mode

When running from source repository:

```bash
# Use --dev flag for development compose file
llmcrawl deploy --up --dev --dir ./deploy
llmcrawl deploy --restart gateway --build --dev --dir ./deploy
```

---

## Upgrading

When a new version of LLMCrawl is released:

### Step 1: Install New Version

```bash
# Activate your virtual environment first
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate      # Linux/Mac

# Install new wheel
pip install --upgrade llmcrawl-1.1.0-py3-none-any.whl
```

### Step 2: Upgrade Deployment

```bash
# From the folder containing llmcrawl-deploy/
llmcrawl deploy --upgrade
```

This will:
1. **Backup** your `.env` and config files to `backups/`
2. **Update** all deployment files (docker-compose.yml, Dockerfiles, service code)
3. **Merge** your existing `.env` settings into the new configuration
4. **Rebuild and restart** all services

### Upgrade Options

```bash
# Upgrade without restarting (manual restart later)
llmcrawl deploy --upgrade --no-restart

# Then restart when ready
llmcrawl deploy --up
```

### After Upgrade

- Check `backups/` folder if you need to restore settings
- Review `.env` for new configuration options
- Restart standalone tools (WCD bridge, HiChat CLI) if running

---

## Troubleshooting

### Docker Not Running

```
❌ Error: Docker is not running or not installed.
```

**Solution**: Start Docker Desktop application.

### Port Already in Use

```
Error: Bind for 0.0.0.0:8000 failed: port is already allocated
```

**Solution**: Edit `.env` and change the conflicting port:

```bash
GATEWAY_PORT=8001
```

### API Key Errors

```
Error: Invalid API key provided
```

**Solution**:
1. Verify the API key in `.env` is correct
2. Ensure no extra spaces or quotes around the key
3. Check the key hasn't expired

### Services Not Starting

```bash
# Check service logs for errors
llmcrawl deploy --logs gateway

# Check all container status
docker ps -a
```

### Reset Everything

```bash
# Stop and remove all containers/volumes
llmcrawl deploy --down
docker system prune -a --volumes

# Reinitialize (--force overwrites existing)
llmcrawl deploy --init --force
# Edit .env again
llmcrawl deploy --up
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Initialize deployment | `llmcrawl deploy --init` |
| Start services | `llmcrawl deploy --up` |
| Stop services | `llmcrawl deploy --down` |
| View status | `llmcrawl deploy --status` |
| View logs | `llmcrawl deploy --logs` |
| Upgrade deployment | `llmcrawl deploy --upgrade` |
| Authenticate to site | `llmcrawl auth <url>` |
| Start WCD bridge | `llmcrawl wcd-bridge --build <path>` |
| Start HiChat CLI | `hichat` or `hichat --deploy-dir ./llmcrawl-deploy` |
| Open HiChat (Docker) | http://localhost:8080 |
| API Documentation | http://localhost:8000/docs |

---

## Service Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Your Browser                             │
│                   http://localhost:8080                      │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    HiChat Web UI                             │
│                    (Port 8080)                               │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    Gateway API                               │
│                    (Port 8000)                               │
│              LLM Orchestration & Agent                       │
└──────┬──────────────────┼───────────────────────┬───────────┘
       │                  │                       │
┌──────▼──────┐   ┌───────▼───────┐      ┌───────▼───────┐
│   Crawler   │   │    Indexer    │      │  MCP Servers  │
│  (Port 8001)│   │  (Port 8002)  │      │  (Port 8003+) │
└──────┬──────┘   └───────┬───────┘      └───────────────┘
       │                  │
┌──────▼──────────────────▼───────────────────────────────────┐
│                   Data Stores                                │
│  PostgreSQL (5432) │ Qdrant (6333) │ Redis (6379)           │
└─────────────────────────────────────────────────────────────┘
```

---

## Getting Help

- **Troubleshooting**: See [DIAGNOSTICS.md](DIAGNOSTICS.md)
- **Architecture**: See [ARCHITECTURE.md](ARCHITECTURE.md)
- **Configuration**: See [CONFIGURATION.md](CONFIGURATION.md)
- **Monitoring**: See [DIAGNOSTICS.md](DIAGNOSTICS.md)
- **Authentication**: See [AUTHENTICATION.md](AUTHENTICATION.md)

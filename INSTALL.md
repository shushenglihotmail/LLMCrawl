# LLMCrawl Installation Guide

This guide walks you through installing and running LLMCrawl on a fresh machine.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Upgrading](#upgrading)
4. [Configuration](#configuration)
5. [Starting Services](#starting-services)
6. [Using HiChat Client](#using-hichat-client)
7. [Management Commands](#management-commands)
8. [Troubleshooting](#troubleshooting)

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
# Check Docker
docker --version
# Expected: Docker version 24.0.0 or higher

# Check Docker Compose
docker compose version
# Expected: Docker Compose version v2.0.0 or higher

# Check Python
python --version
# Expected: Python 3.10.0 or higher
```

---

## Installation

### Step 1: Create a Virtual Environment (Recommended)

Create a dedicated virtual environment to keep LLMCrawl and its dependencies isolated:

```bash
# Create a folder for LLMCrawl
mkdir llmcrawl
cd llmcrawl

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

### Step 2: Install LLMCrawl

#### Option A: Install from Wheel File (Recommended)

If you received a `.whl` file:

```bash
# Install the wheel
pip install llmcrawl-1.0.0-py3-none-any.whl

# Verify installation
llmcrawl --help
```

#### Option B: Install from Source

If you have access to the source code:

```bash
# Clone or extract the source
cd LLMCrawl

# Install in development mode
pip install -e .

# Verify installation
llmcrawl --help
```

---

## Upgrading

When a new version is available, follow these steps:

### Step 1: Install the New Version

```bash
# From wheel file
pip install --upgrade llmcrawl-1.1.0-py3-none-any.whl

# Or from source
cd LLMCrawl
git pull
pip install -e .
```

### Step 2: Upgrade Deployment

```bash
# Run from the folder containing llmcrawl-deploy/
# (The command automatically finds ./llmcrawl-deploy)
llmcrawl deploy --upgrade
```

This command will:
1. **Backup** your current `.env` and config files to `backups/`
2. **Update** all deployment files (docker-compose.yml, Dockerfiles, etc.)
3. **Merge** your existing `.env` settings into the new configuration
4. **Rebuild and restart** all services

### Upgrade Options

```bash
# Upgrade without restarting services (manual restart later)
llmcrawl deploy --upgrade --no-restart

# Then manually restart when ready
llmcrawl deploy --up
```

### After Upgrade

- Check `backups/` folder if you need to restore any settings
- Review `.env` for any new configuration options
- Restart any standalone tools (WCD bridge, HiChat CLI) if running

---

## Configuration

### Step 1: Initialize Deployment

```bash
# Create the deployment folder
llmcrawl deploy --init
```

This creates a `llmcrawl-deploy/` folder with:
```
llmcrawl-deploy/
├── docker-compose.yml      # Service orchestration
├── .env                    # Your configuration (edit this!)
├── .env.example            # Reference configuration
├── Dockerfile.*            # Service build files
├── prometheus.yml          # Monitoring config
├── grafana-provisioning/   # Grafana dashboards
├── data/files/             # Default MCP file mount point
└── logs/                   # Service logs
```

**Note:** The `tools/` (authentication, WCD bridge) are accessed via CLI commands:
- `llmcrawl auth` - Internal site authentication
- `llmcrawl wcd-bridge` - Windows Composition Database bridge

### Step 2: Configure Your Settings

```bash
cd llmcrawl-deploy

# Edit .env with your settings
notepad .env        # Windows
# or
nano .env           # Linux/Mac
```

### Required Settings

At minimum, configure your LLM API keys:

```bash
# =============================================================================
# LLM CONFIGURATION (Required - at least one)
# =============================================================================

# Option A: OpenAI Direct
OPENAI_API_KEY=sk-your-openai-key-here

# Option B: Azure OpenAI
AZURE_OPENAI_API_KEY=your-azure-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Option C: Azure with Anthropic (Claude)
AZURE_ANTHROPIC_ENDPOINT=https://your-resource.services.ai.azure.com/anthropic/
```

### Optional Settings

```bash
# LLM Provider Selection
LLM_PROVIDER=azure          # Options: openai, azure

# Available Models (customize as needed)
LLM_MODELS=[{"name":"gpt-4","display_name":"GPT-4","deployment_name":"gpt-4","provider_type":"openai"}]

# Service Ports (change if defaults conflict)
GATEWAY_PORT=8000
HICHAT_PORT=8080

# Logging
LOG_LEVEL=INFO              # Options: DEBUG, INFO, WARNING, ERROR
```

---

## Tool Configuration (Optional)

LLMCrawl includes several tools that can be enabled based on your needs:

### Local File Access (MCP Server)

The Local Access MCP server allows the agent to read and search files on your local machine.

**Configuration:**

Edit `.env` and set the folder you want to expose:

```bash
# Path to your source code or documents folder
# Windows: Use forward slashes or escaped backslashes
MCP_HOST_FOLDER=C:/src
# or
MCP_HOST_FOLDER=C:\\src

# Linux/Mac:
MCP_HOST_FOLDER=/home/user/src
```

The agent will be able to read, list, and search files within this folder.

---

### Azure DevOps Integration

The Azure DevOps MCP server allows the agent to search and read code from Azure DevOps repositories.

**Setup:**

1. **Create a Personal Access Token (PAT)**
   - Go to: `https://dev.azure.com/[your-org]/_usersSettings/tokens`
   - Click "New Token"
   - Required scopes:
     - **Code (Read)** - for reading repository files
     - **Code (Search)** - for searching code (optional)
   - Copy the generated token

2. **Configure in `.env`:**

```bash
AZURE_DEVOPS_PAT=your-pat-token-here

# Optional: Set default org/project/repo
AZURE_DEVOPS_ORG=microsoft
AZURE_DEVOPS_PROJECT=OS
AZURE_DEVOPS_REPO=os.2020
AZURE_DEVOPS_BRANCH=main
```

---

### Internal Site Crawling (Authentication)

To crawl internal sites that require authentication (e.g., www.osgwiki.com), you need to provide authentication cookies.

**Setup:**

1. **Install required dependencies** (one-time setup):

```bash
# Make sure your virtual environment is activated
# (the same venv where you installed llmcrawl)

# Install playwright and other auth tool dependencies
pip install playwright httpx requests
playwright install chromium
```

2. **Run the authentication command:**

```bash
# Authenticate to an internal site
llmcrawl auth https://www.osgwiki.com/wiki/Main_Page
```

3. **What the tool does:**
   - Opens Microsoft Edge with a temporary profile
   - Waits for you to log in to the internal site
   - Extracts authentication cookies after successful login
   - Automatically updates `.env` with the cookies
   - Restarts the crawler container to apply changes
   - Tests that authentication works

4. **Options:**

```bash
# See all options
llmcrawl auth --help

# Skip auto-apply to .env (just save cookies to .auth/ folder)
llmcrawl auth https://www.osgwiki.com --no-apply

# Skip container restart
llmcrawl auth https://www.osgwiki.com --no-restart

# Skip authentication test
llmcrawl auth https://www.osgwiki.com --no-test

# Custom profile name
llmcrawl auth https://internal-site.com --name my_site
```

5. **Cookie Expiration:**
   - Authentication cookies expire after some time (typically hours to days)
   - If crawling starts failing with authentication errors, re-run the command:
     ```bash
     llmcrawl auth https://www.osgwiki.com/wiki/Main_Page
     ```
   - The tool will refresh the cookies and restart the crawler automatically

---

### Windows Composition Database (WCD) Tool

The WCD tool allows querying the Windows Composition Database for component information. This requires a bridge service running on your host machine (because WCD uses Windows-specific commands).

**Prerequisites:**
- Windows host machine
- Access to Windows build shares (e.g., `\\winbuilds\release\...`)

**Setup:**

1. **Start the WCD Bridge service** on your host:

```bash
# Using build share path (recommended)
llmcrawl wcd-bridge --build "\\winbuilds\release\rs_sparc_ctr_exp\29498.1001.251201-1700"

# For a different architecture:
llmcrawl wcd-bridge --build "\\winbuilds\release\..." --arch arm64fre

# See all options
llmcrawl wcd-bridge --help
```

2. **Configure in `.env`:**

```bash
# The bridge runs on port 8005 by default
# Use host.docker.internal to reach the host from Docker containers
WIN_COMP_BRIDGE_URL=http://host.docker.internal:8005
```

3. **Keep the bridge running:**
   - The bridge service must remain running while using WCD queries
   - It runs in a separate terminal window
   - Restart it if you need to switch to a different build

---

## Starting Services

### Start All Services

```bash
# Run from the folder containing llmcrawl-deploy/
# (The command automatically finds ./llmcrawl-deploy)
llmcrawl deploy --up
```

Expected output:
```
🚀 Starting LLMCrawl services...
🐳 Running: docker compose -f docker-compose.yml up --build -d

✅ Services started successfully!

Access points:
  • HiChat Web UI:    http://localhost:8080
  • Gateway API:      http://localhost:8000
  • Gateway Docs:     http://localhost:8000/docs
  • Qdrant Dashboard: http://localhost:6333/dashboard
  • Grafana:          http://localhost:3001
```

### First-Time Startup

The first startup takes longer as Docker:
1. Downloads base images (PostgreSQL, Qdrant, Redis, etc.)
2. Builds the LLMCrawl service images

Subsequent starts are much faster.

---

## Using HiChat Client

### Web Interface

1. Open your browser to: **http://localhost:8080**
2. Select a model from the dropdown
3. Start chatting!

### Features

- **Multi-model support**: Switch between GPT-4, Claude, and other models
- **Stop button**: Cancel long-running requests
- **Chat history**: Maintains context within a conversation
- **Clear chat**: Start fresh with the Clear button

### Direct CLI Access

You can also run HiChat standalone (connects to running gateway):

```bash
hichat --gateway http://localhost:8000
```

---

## Management Commands

### View Service Status

```bash
llmcrawl deploy --status
```

### View Logs

```bash
# All services
llmcrawl deploy --logs

# Specific service
llmcrawl deploy --logs gateway

# Without following (just show recent)
llmcrawl deploy --logs --no-follow
```

### Stop Services

```bash
llmcrawl deploy --down
```

### Restart Services

```bash
# Restart all
llmcrawl deploy --restart

# Restart specific service
llmcrawl deploy --restart gateway
```

### Pull Latest Images

```bash
llmcrawl deploy --pull
```

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

**Solution**: Check your `.env` file:
1. Verify the API key is correct
2. Ensure no extra spaces or quotes
3. Check the key hasn't expired

### Services Not Starting

```bash
# Check service logs
llmcrawl deploy --logs gateway

# Check all container status
docker ps -a
```

### Reset Everything

```bash
# Stop and remove all containers/volumes
llmcrawl deploy --down
docker system prune -a --volumes

# Reinitialize
llmcrawl deploy --init --force
llmcrawl deploy --up
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Initialize deployment | `llmcrawl deploy --init` |
| **Upgrade deployment** | `llmcrawl deploy --upgrade` |
| Start services | `llmcrawl deploy --up` |
| Stop services | `llmcrawl deploy --down` |
| View status | `llmcrawl deploy --status` |
| View logs | `llmcrawl deploy --logs` |
| Restart services | `llmcrawl deploy --restart` |
| Authenticate to internal site | `llmcrawl auth <url>` |
| Start WCD bridge | `llmcrawl wcd-bridge --build <path>` |
| Open HiChat | http://localhost:8080 |
| API Documentation | http://localhost:8000/docs |

---

## Getting Help

- **Documentation**: See `docs/` folder for detailed guides
- **Issues**: Check logs with `llmcrawl deploy --logs`
- **Architecture**: See `docs/ARCHITECTURE.md`
- **Configuration**: See `docs/CONFIGURATION.md`
- **Monitoring**: See `docs/MONITORING.md` for Grafana dashboards and metrics

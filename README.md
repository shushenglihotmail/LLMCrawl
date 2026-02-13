# LLMCrawl - Web RAG System

A production-ready, containerized Python web RAG system that enables LLMs to trigger web crawling, index results, and answer questions with citations. Features conversation memory, intelligent tool calling, and multi-source web scraping.

## 🏗️ Architecture

The system consists of five main services:

- **Gateway Service** (Port 8000): FastAPI orchestrator with OpenAI/Azure OpenAI/Anthropic/Claude Bridge support
- **Crawler Service** (Port 8001): FireCrawl + Playwright fallback + Trafilatura extraction
- **Indexer Service** (Port 8002): LlamaIndex + Vector DB (Qdrant/pgvector) for RAG
- **MCP Server** (Port 8003): Local file operations with semantic search
- **Azure DevOps MCP** (Port 8004): Azure DevOps code search integration

**Host-side services** (run on the host machine, accessed via `host.docker.internal`):

- **WCD Bridge** (Port 8005): Windows Composition Database query bridge
- **Claude Bridge** (Port 8006): Claude Code CLI HTTP bridge for Opus/CLI models

```
┌─────────────────────────────────────────────────────────────┐
│                     Your Browser / HiChat                    │
│                   http://localhost:8080                      │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    Gateway API (8000)                        │
│              LLM Orchestration & Agent                       │
└──────┬──────────────────┼───────────────┬───────────────────┘
       │                  │               │
┌──────▼──────┐   ┌───────▼───────┐  ┌───▼───────────┐
│   Crawler   │   │    Indexer    │  │  MCP Servers  │
│   (8001)    │   │    (8002)     │  │  (8003/8004)  │
└──────┬──────┘   └───────┬───────┘  └───────────────┘
       │                  │
┌──────▼──────────────────▼───────────────────────────────────┐
│                   Data Stores                                │
│  PostgreSQL (5432) │ Qdrant (6333) │ Redis (6379)           │
└─────────────────────────────────────────────────────────────┘

Host-side Bridge Services (accessed via host.docker.internal):
┌─────────────────┐  ┌──────────────────┐
│  WCD Bridge     │  │  Claude Bridge   │
│  (8005)         │  │  (8006)          │
└─────────────────┘  └──────────────────┘
```

📖 **See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for detailed system design and data flows.

## ✨ Key Features

### Web RAG Capabilities
- **Conversation Memory**: Multi-turn conversations with context preservation (24-hour TTL)
- **Intelligent Tool Triggering**: Automatic detection of queries needing fresh data (29+ trigger words)
- **Forced Tool Execution**: Prevents incomplete "I'll fetch..." responses by enforcing tool calls
- **Sequential Browser Rendering**: Stable Playwright execution in Docker
- **FireCrawl Integration**: Redis-backed rate limiting with proper connection handling
- **Internal Site Authentication**: Support for headers, cookies, basic auth, and bearer tokens

### Code Intelligence Agent
- **Multi-Workflow Support**: Understand & Document, Inspect & Analyze, Generate from Examples
- **Flexible Path Input**: Files, folders, wildcards (`*.cpp`), and recursive paths (`folder/**`)
- **Multi-Provider Support**: OpenAI, Azure OpenAI, and Anthropic Claude
- **Web Documentation**: Optionally crawl documentation URLs for context

### Local File Operations (MCP Server)
- **Secure File Access**: Read local files with path validation and security checks
- **Directory Operations**: List files and directories with structured results
- **Semantic Search**: Index and search file content by meaning
- **Volume Mounting**: Configure any local folder as root for file operations

📖 **MCP Server Documentation**: [mcp_servers/local_access_mcp_server/README.md](mcp_servers/local_access_mcp_server/README.md)

### Azure DevOps Code Search (MCP Server)
- **Code Search**: Semantic search across Azure DevOps repositories
- **File Retrieval**: Get file content from specific branches/commits
- **MSAL Authentication**: Interactive OAuth with browser flow + PAT support

📖 **Azure DevOps Documentation**: [mcp_servers/azure_devops_mcp_server/docs/README.md](mcp_servers/azure_devops_mcp_server/docs/README.md)

---

## 🚀 Quick Start

### Option 1: Install from Wheel (Recommended for Users)

📖 **See [docs/INSTALL.md](docs/INSTALL.md)** for complete installation guide.

```bash
# 1. Download and install wheel
pip install llmcrawl-1.0.0-py3-none-any.whl

# 2. Initialize deployment folder
llmcrawl deploy --init

# 3. Configure environment
cd llmcrawl-deploy
cp .env.example .env
# Edit .env with your API keys

# 4. Start services
llmcrawl deploy --up

# 5. Open HiChat client
hichat
# Opens browser to http://localhost:8080
```

### Option 2: Development Setup (For Contributors)

📖 **See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** for complete development guide.

```bash
# Clone repository
git clone <repository-url>
cd LLMCrawl

# Run setup script
# Windows:
.\scripts\setup_dev.ps1

# Linux/Mac:
python scripts/setup_dev.py

# Start development environment
make dev-up
```

---

## 🖥️ HiChat Web Client

A Python-based web client for interacting with the LLMCrawl gateway.

```bash
# Install with client extras
pip install -e ".[client]"

# Run the web client
hichat
# Opens browser to http://localhost:8080
```

### Features
- Modern web UI with markdown and mermaid diagram support
- Multiple workflow support (General Chat, Code Analysis, Build System, File Explorer)
- Model selection from gateway
- Conversation history with save-to-markdown
- Stop button with server-side cancellation

📖 **See [clients/hichat/README.md](clients/hichat/README.md)** for full documentation.

---

## 📋 Configuration

All environment variables are in `deploy/.env`.

📖 **See [docs/CONFIGURATION.md](docs/CONFIGURATION.md)** for complete configuration guide.

### Essential Settings

```bash
# LLM Provider (required)
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com

# Entra ID Authentication (recommended over API keys)
ENTRA_CLIENT_ID=04b07795-8ddb-461a-bbee-02f9e1bf7b46
ENTRA_TENANT_ID=your-tenant-id

# Claude Bridge (optional, for Claude Opus via CLI)
CLAUDE_BRIDGE_URL=http://host.docker.internal:8006

# Vector Database
VECTOR_DB=qdrant  # or pgvector

# Crawling Configuration
ALLOWED_DOMAINS=sec.gov,ft.com,wsj.com,nvidia.com,reuters.com
RESPECT_ROBOTS=true
```

### Authentication for Internal Sites

For internal sites requiring SSO authentication:

```powershell
# Run one-command authentication
python tools/msauth/authenticate.py https://your-internal-site.com
```

📖 **See [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md)** for full authentication guide.

---

## 🩺 Health & Troubleshooting

### Quick Health Check

```bash
# Using CLI
llmcrawl deploy --status

# Using Make
make health
```

### Service Endpoints

| Service        | URL                           | Purpose              |
|----------------|-------------------------------|----------------------|
| Gateway        | http://localhost:8000/health  | API orchestrator     |
| Crawler        | http://localhost:8001/health  | Web crawling         |
| Indexer        | http://localhost:8002/health  | Vector indexing      |
| MCP Server     | http://localhost:8003/health  | File operations      |
| HiChat         | http://localhost:8080         | Web client           |
| WCD Bridge     | http://localhost:8005         | WCD query bridge     |
| Claude Bridge  | http://localhost:8006         | Claude Code CLI      |

📖 **See [docs/DIAGNOSTICS.md](docs/DIAGNOSTICS.md)** for troubleshooting guide.

---

## 📊 Monitoring (Optional)

Start Prometheus and Grafana for visual diagnostics:

```bash
# Start with monitoring profile
llmcrawl deploy --up --profile monitoring
```

### Monitoring Endpoints

| Service    | URL                        |
|------------|----------------------------|
| Prometheus | http://localhost:9090      |
| Grafana    | http://localhost:3001      |

📖 **See [docs/MONITORING.md](docs/MONITORING.md)** for complete monitoring guide.

---

## 📚 Documentation

### Core Documentation
| Document | Description |
|----------|-------------|
| [docs/INSTALL.md](docs/INSTALL.md) | Installation and deployment for users |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Environment variables and settings |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design and data flows |
| [docs/DIAGNOSTICS.md](docs/DIAGNOSTICS.md) | Troubleshooting and debugging |
| [docs/MONITORING.md](docs/MONITORING.md) | Observability, metrics, and dashboards |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Development setup and testing |

### MCP Servers
| Server | Documentation |
|--------|---------------|
| Local File Operations | [mcp_servers/local_access_mcp_server/README.md](mcp_servers/local_access_mcp_server/README.md) |
| Azure DevOps | [mcp_servers/azure_devops_mcp_server/docs/README.md](mcp_servers/azure_devops_mcp_server/docs/README.md) |

### Additional Guides
| Document | Description |
|----------|-------------|
| [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md) | Crawl authenticated internal sites |
| [docs/CRAWL_STRATEGY.md](docs/CRAWL_STRATEGY.md) | How crawling works, limitations |
| [docs/VISUAL_OVERVIEW.md](docs/VISUAL_OVERVIEW.md) | Quick visual guide with diagrams |
| [docs/MULTI_PROVIDER_LLM.md](docs/MULTI_PROVIDER_LLM.md) | Multi-provider LLM configuration (OpenAI, Anthropic, Claude Bridge) |

---

## 📁 Project Structure

```
llmcrawl/
├── gateway/              # Main API gateway service
├── crawler/              # Web crawling service
├── indexer/              # Document indexing service
├── mcp_servers/          # MCP servers (local files, Azure DevOps)
├── clients/hichat/       # Web client
├── tools/                # Host-side bridge services and utilities
├── deploy/               # Docker and deployment configs
├── docs/                 # Documentation
├── scripts/              # Setup and utility scripts
└── tests/                # Test suites
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Install development dependencies: `pip install -r requirements/dev.txt`
4. Run tests: `make test-dev`
5. Run code quality checks: `make pre-commit`
6. Submit a pull request

📖 **See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** for detailed development workflow.

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

**Built with ❤️ by the LLMCrawl team**

*Empowering AI applications with real-time web intelligence*

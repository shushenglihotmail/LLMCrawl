# Development Environment Setup Guide

This guide will help you set up a complete development environment for the LLMCrawl project.

## Prerequisites

- **Python 3.10+** - Required for all services
- **Docker & Docker Compose** - For containerized services
- **Git** - For version control
- **PowerShell** (Windows) - For setup scripts

## Quick Setup

### Option 1: Automated Setup (Recommended)

**Windows (PowerShell):**
```powershell
.\scripts\setup_dev.ps1
```

**Unix/Linux/macOS:**
```bash
python scripts/setup_dev.py
```

### Option 2: Manual Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd LLMCrawl
   ```

2. **Create and activate Python virtual environment:**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # Unix/Linux/macOS
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements/gateway.txt
   pip install -r requirements/crawler.txt
   pip install -r requirements/indexer.txt
   pip install -r requirements/test.txt
   pip install -r requirements/dev.txt
   ```

4. **Install Playwright browsers:**
   ```bash
   playwright install
   playwright install-deps
   ```

5. **Setup pre-commit hooks:**
   ```bash
   pre-commit install
   ```

6. **Configure environment:**
   ```bash
   cd deploy
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

## Configuration

### 1. Environment Variables

Edit the `.env` file with your configuration:

```bash
# Required: OpenAI API Key
OPENAI_API_KEY=your_openai_key_here

# Optional: Azure OpenAI (alternative to OpenAI)
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your_azure_key_here

# Optional: Firecrawl API Key (for better crawling)
FIRECRAWL_API_KEY=your_firecrawl_key_here

# Vector Database (qdrant recommended for development)
VECTOR_DB=qdrant

# Crawling domains (customize as needed)
ALLOWED_DOMAINS=sec.gov,ft.com,wsj.com,nvidia.com,reuters.com,bloomberg.com
```

### 2. API Keys Required

- **OpenAI API Key**: Get from [OpenAI Platform](https://platform.openai.com/api-keys)
- **Firecrawl API Key** (optional): Get from [Firecrawl](https://firecrawl.dev/)
- **Azure OpenAI** (alternative): Configure if using Azure instead of OpenAI

## Development Workflow

### 1. Start Development Environment

```bash
make dev-up
```

This starts all services in development mode with:
- Hot reload enabled
- Debug logging
- Volume mounts for code changes
- All dependencies running

### 2. Verify Services

```bash
make health
```

Check that all services are responding:
- Gateway: http://localhost:8000
- Crawler: http://localhost:8001
- Indexer: http://localhost:8002
- Qdrant Dashboard: http://localhost:6333/dashboard

### 3. Development Commands

```bash
# Start development environment
make dev-up

# View logs
make dev-logs

# Stop development environment
make dev-down

# Rebuild and restart
make dev-rebuild

# Run tests locally
make test-dev

# Run code quality checks
make pre-commit

# Format code
black .
isort .

# Type checking
mypy .
```

### 4. Testing

**Run all tests:**
```bash
make test-dev
```

**Run specific service tests:**
```bash
pytest gateway/tests/ -v
pytest crawler/tests/ -v
pytest indexer/tests/ -v
```

**Run integration tests:**
```bash
make test-integration
```

**Test with coverage:**
```bash
pytest --cov=. --cov-report=html
```

### 5. Code Quality

The project uses pre-commit hooks for code quality:

```bash
# Run all checks
make pre-commit

# Individual tools
black --check .          # Code formatting
isort --check-only .      # Import sorting
flake8 .                  # Linting
mypy .                    # Type checking
```

## Architecture Overview

### Services

1. **Gateway Service** (Port 8000)
   - FastAPI app handling chat requests
   - OpenAI/Azure integration
   - Tool calling orchestration

2. **Crawler Service** (Port 8001)
   - Web crawling with Firecrawl + Playwright
   - Content extraction with Trafilatura
   - Respects robots.txt

3. **Indexer Service** (Port 8002)
   - Document indexing with LlamaIndex
   - Vector storage (Qdrant/pgvector)
   - Semantic search and retrieval

4. **Supporting Services**
   - **Qdrant** (Port 6333) - Vector database
   - **PostgreSQL** (Port 5432) - Alternative vector storage
   - **Redis** (Port 6379) - Caching
   - **Firecrawl** (Port 3002) - Web crawling API

### Development Features

- **Hot Reload**: Code changes automatically restart services
- **Debug Logging**: Detailed logs for development
- **Volume Mounts**: Live code editing without rebuilds
- **Isolated Environment**: All services in Docker containers
- **Health Checks**: Service availability monitoring

## Troubleshooting

### Common Issues

1. **Port conflicts**: Ensure ports 8000-8002, 6333, 5432, 6379 are free
2. **Docker issues**: Try `docker system prune -f` to clean up
3. **Permission issues**: Run setup script as administrator on Windows
4. **Network issues**: Check Docker network with `docker network ls`

### Reset Environment

```bash
# Stop and remove all containers
make dev-down

# Clean up volumes and networks
make clean

# Restart fresh
make dev-up
```

### View Logs

```bash
# All services
make dev-logs

# Specific service
docker-compose logs -f gateway
docker-compose logs -f crawler
docker-compose logs -f indexer
```

## API Testing

### Example Requests

**Basic chat:**
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, what can you help me with?"}'
```

**Web search query:**
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the latest NVIDIA earnings?"}'
```

**Streaming response:**
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Latest Tesla news?", "stream": true}'
```

## IDE Setup

### VS Code

Recommended extensions:
- Python
- Black Formatter
- isort
- Pylance
- Docker
- YAML

Settings for `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.formatting.provider": "black",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true,
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    }
}
```

### PyCharm

1. Open project in PyCharm
2. Configure Python interpreter to use `venv/bin/python`
3. Enable Black formatting in Tools > External Tools
4. Configure run configurations for each service

## Contributing

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes and test: `make test-dev`
3. Run quality checks: `make pre-commit`
4. Commit changes: `git commit -m "Add feature"`
5. Push branch: `git push origin feature/my-feature`
6. Create pull request

## Support

If you encounter issues:

1. Check this guide for common solutions
2. Review service logs: `make dev-logs`
3. Verify configuration in `.env` file
4. Test individual services with health checks
5. Reset environment if needed: `make clean && make dev-up`

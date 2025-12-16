# Development Scripts

This directory contains automated setup and utility scripts for the LLMCrawl development environment.

## Service Management Scripts

### `restart-services.ps1` ⭐ (Most Used)
**Purpose:** Restart services with optional rebuild for code/env changes

**Usage:**
```powershell
# Recreate containers (picks up .env changes)
.\scripts\restart-services.ps1

# Rebuild and restart (picks up code changes)
.\scripts\restart-services.ps1 -Build

# Rebuild specific service(s)
.\scripts\restart-services.ps1 -Service gateway -Build
.\scripts\restart-services.ps1 -Service gateway,crawler -Build

# Full rebuild with no cache (after requirements.txt changes)
.\scripts\restart-services.ps1 -Full

# Rebuild and follow logs
.\scripts\restart-services.ps1 -Build -Logs
```

**Flags:**
| Flag | Description |
|------|-------------|
| `-Service` | Target specific service(s), comma-separated |
| `-Build` | Rebuild images (picks up code changes) |
| `-Full` | Full rebuild with no cache |
| `-Logs` | Follow logs after restart |

### `start-services.ps1`
**Purpose:** Start all services (first time or after stop)

**Usage:**
```powershell
# Start all services
.\scripts\start-services.ps1

# Start with build
.\scripts\start-services.ps1 -Build

# Start only infrastructure (redis, postgres, qdrant)
.\scripts\start-services.ps1 -Infrastructure
```

### `stop-services.ps1`
**Purpose:** Stop services

**Usage:**
```powershell
# Stop (preserve containers)
.\scripts\stop-services.ps1

# Stop and remove containers (keep data)
.\scripts\stop-services.ps1 -Remove

# Stop specific service(s)
.\scripts\stop-services.ps1 -Service gateway,crawler

# Full cleanup including data volumes (WARNING!)
.\scripts\stop-services.ps1 -Remove -Volumes
```

### `service-status.ps1`
**Purpose:** Check status and health of all services

**Usage:**
```powershell
# Show current status
.\scripts\service-status.ps1

# Continuously monitor (refresh every 5s)
.\scripts\service-status.ps1 -Watch
```

## Quick Reference

| Scenario | Command |
|----------|---------|
| Start HiChat client | `.\scripts\start_hichat.ps1` |
| Code change in gateway | `.\scripts\restart-services.ps1 -Service gateway -Build` |
| Changed .env file | `.\scripts\restart-services.ps1` |
| Changed requirements.txt | `.\scripts\restart-services.ps1 -Full` |
| View service health | `.\scripts\service-status.ps1` |
| Stop everything | `.\scripts\stop-services.ps1 -Remove` |
| Start fresh | `.\scripts\start-services.ps1 -Build` |

## Client Scripts

### `start_hichat.ps1`
**Purpose:** Start HiChat web client for development

**Usage:**
```powershell
# Start HiChat with automatic deploy directory detection
.\scripts\start_hichat.ps1
```

This script:
- Automatically locates the deploy directory
- Changes to the HiChat client directory
- Starts HiChat with proper configuration
- Loads environment from `deploy/.env`

## Setup Scripts

### `setup_dev.py` (Cross-platform)
**Purpose:** Complete development environment setup

**Usage:**
```bash
python scripts/setup_dev.py
```

**What it does:**
- Creates Python virtual environment
- Installs all required dependencies
- Sets up Playwright browsers
- Configures pre-commit hooks
- Creates `.env` file from template
- Validates Python version requirements

### `setup_dev.ps1` (Windows PowerShell)
**Purpose:** Windows-specific development environment setup

**Usage:**
```powershell
.\scripts\setup_dev.ps1 [OPTIONS]

OPTIONS:
  -SkipDocker     Skip Docker-related setup
  -Help           Show help message
```

**Examples:**
```powershell
# Full setup
.\scripts\setup_dev.ps1

# Skip Docker setup
.\scripts\setup_dev.ps1 -SkipDocker
```

**What it does:**
- Checks prerequisites (Python, Docker, Docker Compose)
- Creates and configures Python virtual environment
- Installs all dependencies
- Sets up Playwright browsers
- Configures pre-commit hooks
- Creates Docker network for services
- Validates environment configuration

## Health Check Scripts

### `health-check.ps1`
**Purpose:** Run health checks against all services

### `check-metrics.ps1`
**Purpose:** Check Prometheus metrics endpoints

## Test Scripts

### `test-indexing.ps1`
**Purpose:** Test the indexing pipeline

### `test-auth-config.ps1` / `test-internal-auth.ps1`
**Purpose:** Test authentication configuration

## Quick Start Scripts

### `start_dev.sh` (Unix/Linux/macOS)
**Purpose:** Quick start development environment

**Usage:**
```bash
./scripts/start_dev.sh
```

### `start_dev.ps1` (Windows PowerShell)
**Purpose:** Quick start development environment

**Usage:**
```powershell
.\scripts\start_dev.ps1
```

**What both scripts do:**
- Verify `.env` file exists
- Check API key configuration
- Start all development services
- Wait for services to initialize
- Run health checks
- Display service URLs and useful commands

## Service URLs

| Service | URL |
|---------|-----|
| Gateway | http://localhost:8000 |
| Crawler | http://localhost:8001 |
| Indexer | http://localhost:8002 |
| MCP Server | http://localhost:8003 |
| Azure DevOps MCP | http://localhost:8004 |
| Qdrant | http://localhost:6333 |
| Redis | localhost:6379 |
| PostgreSQL | localhost:5432 |

## Troubleshooting

### Common Issues

**Docker command not found:**
```powershell
# Make sure Docker Desktop is running
# Use 'docker compose' (v2) not 'docker-compose' (v1)
```

**Network already exists:**
```powershell
# Remove and recreate
docker network rm webrag-network
docker network create webrag-network
```

**Port already in use:**
```powershell
# Find what's using the port
netstat -ano | findstr :8000

# Kill the process or change port in docker-compose.yml
```

**Service won't start:**
```powershell
# Check logs
docker compose -f deploy/docker-compose.yml logs gateway

# Check if dependencies are up
.\scripts\service-status.ps1
```

### Getting Help

1. Check service status:
   ```powershell
   .\scripts\service-status.ps1
   ```

2. View logs:
   ```powershell
   docker compose -f deploy/docker-compose.yml logs -f gateway
   ```

3. Check the main development guide:
   ```bash
   cat DEVELOPMENT.md
   ```

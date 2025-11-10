# Development Scripts

This directory contains automated setup and utility scripts for the LLMCrawl development environment.

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

## Makefile Integration

The scripts are integrated into the project Makefile for convenience:

```bash
# Setup commands
make setup-dev              # Cross-platform setup (uses setup_dev.py)
make setup-dev-windows       # Windows setup (uses setup_dev.ps1)

# Quick start commands
make quick-start            # Unix/Linux/macOS quick start
make quick-start-windows    # Windows quick start
```

## Prerequisites

### Required
- **Python 3.10+** - All scripts require Python 3.10 or higher
- **Git** - For version control and pre-commit hooks

### Optional (can be skipped)
- **Docker** - For containerized services (can use `-SkipDocker` flag)
- **Docker Compose** - For multi-service orchestration

## Setup Flow

1. **Run setup script** - Installs dependencies and configures environment
2. **Edit `.env` file** - Configure your API keys and settings
3. **Run quick start script** - Start all services and verify setup

## Script Features

### Error Handling
- Validates prerequisites before starting
- Provides clear error messages with solutions
- Exits gracefully on failures

### Cross-Platform Support
- Detects operating system automatically
- Uses appropriate commands and paths
- Handles Windows/Unix path differences

### User Experience
- Colored output for better readability
- Progress indicators for long-running tasks
- Clear instructions for next steps
- Helpful command suggestions

## Troubleshooting

### Common Issues

**Python version errors:**
```bash
# Check Python version
python --version

# Update to Python 3.10+
# See: https://python.org/downloads
```

**Permission errors on Windows:**
```powershell
# Run PowerShell as Administrator
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Docker network conflicts:**
```bash
# Remove existing network
docker network rm webrag-network

# Re-run setup
python scripts/setup_dev.py
```

**Missing dependencies:**
```bash
# Reinstall requirements
pip install -r requirements/dev.txt
```

### Getting Help

1. Run script with help flag (where available):
   ```powershell
   .\scripts\setup_dev.ps1 -Help
   ```

2. Check the main development guide:
   ```bash
   cat DEVELOPMENT.md
   ```

3. View service logs:
   ```bash
   make dev-logs
   ```

## Contributing

When adding new scripts:

1. **Add documentation** to this README
2. **Include error handling** with clear messages
3. **Make cross-platform compatible** where possible
4. **Test on multiple operating systems**
5. **Update Makefile** with new targets
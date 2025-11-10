# PowerShell setup script for LLMCrawl development environment
# Run this script in PowerShell as Administrator if needed

param(
    [switch]$SkipDocker = $false,
    [switch]$Help = $false
)

if ($Help) {
    Write-Host @"
LLMCrawl Development Environment Setup

USAGE:
    .\setup_dev.ps1 [OPTIONS]

OPTIONS:
    -SkipDocker     Skip Docker-related setup
    -Help           Show this help message

EXAMPLES:
    .\setup_dev.ps1                 # Full setup
    .\setup_dev.ps1 -SkipDocker     # Skip Docker setup

"@
    exit 0
}

function Write-Success {
    param($Message)
    Write-Host "✅ $Message" -ForegroundColor Green
}

function Write-Info {
    param($Message)
    Write-Host "ℹ️  $Message" -ForegroundColor Blue
}

function Write-Warning {
    param($Message)
    Write-Host "⚠️  $Message" -ForegroundColor Yellow
}

function Write-Error {
    param($Message)
    Write-Host "❌ $Message" -ForegroundColor Red
}

function Test-CommandExists {
    param($Command)
    try {
        Get-Command $Command -ErrorAction Stop | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

# Change to project root directory (parent of scripts)
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptRoot
Set-Location $projectRoot

Write-Info "Setting up LLMCrawl development environment..."

# Check prerequisites
$prerequisites = @{
    "python" = "Python 3.10+"
    "docker" = "Docker"
    "docker-compose" = "Docker Compose"
}

foreach ($cmd in $prerequisites.Keys) {
    if (Test-CommandExists $cmd) {
        Write-Success "$($prerequisites[$cmd]) found"
    } else {
        Write-Error "$($prerequisites[$cmd]) not found. Please install $cmd first."
        if ($cmd -eq "docker" -and !$SkipDocker) {
            Write-Info "You can skip Docker setup with -SkipDocker flag"
        }
        if ($cmd -ne "docker" -or !$SkipDocker) {
            exit 1
        }
    }
}

# Check Python version
$pythonVersion = python --version 2>&1
if ($pythonVersion -match "Python (\d+)\.(\d+)") {
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        Write-Error "Python 3.10+ is required. Found: $pythonVersion"
        exit 1
    }
    Write-Success "Python version OK: $pythonVersion"
}

# Create virtual environment
Write-Info "Creating Python virtual environment..."
if (!(Test-Path "venv")) {
    python -m venv venv
    Write-Success "Virtual environment created"
} else {
    Write-Info "Virtual environment already exists"
}

# Activate virtual environment and install dependencies
Write-Info "Installing Python dependencies..."
& "venv\Scripts\python.exe" -m pip install --upgrade pip

$requirementFiles = @(
    "requirements\gateway.txt",
    "requirements\crawler.txt", 
    "requirements\indexer.txt",
    "requirements\test.txt",
    "requirements\dev.txt"
)

foreach ($reqFile in $requirementFiles) {
    if (Test-Path $reqFile) {
        Write-Info "Installing from $reqFile..."
        & "venv\Scripts\pip.exe" install -r $reqFile
    }
}

# Install Playwright browsers
Write-Info "Installing Playwright browsers..."
& "venv\Scripts\python.exe" -m playwright install
& "venv\Scripts\python.exe" -m playwright install-deps

# Setup pre-commit
if (Test-Path ".pre-commit-config.yaml") {
    Write-Info "Setting up pre-commit hooks..."
    & "venv\Scripts\python.exe" -m pre_commit install
    Write-Success "Pre-commit hooks installed"
}

# Create .env file
if (!(Test-Path ".env") -and (Test-Path ".env.example")) {
    Write-Info "Creating .env file from example..."
    Copy-Item ".env.example" ".env"
    Write-Warning "Please edit .env file with your API keys!"
}

# Docker setup
if (!$SkipDocker) {
    Write-Info "Setting up Docker environment..."
    
    # Create network if it doesn't exist
    $networkExists = docker network ls --filter name=webrag-network --format "{{.Name}}" | Select-String "webrag-network"
    if (!$networkExists) {
        docker network create webrag-network
        Write-Success "Docker network created"
    }
    
    Write-Info "You can now run 'make dev-up' to start the development environment"
}

Write-Success "Development environment setup complete!"
Write-Host ""
Write-Info "Next steps:"
Write-Host "1. Edit .env file with your API keys"
Write-Host "2. Activate virtual environment: venv\Scripts\activate"
Write-Host "3. Run 'make dev-up' to start development services"
Write-Host "4. Run 'make health' to verify services are running"
Write-Host ""
Write-Info "Available commands:"
Write-Host "  make dev-up      - Start development environment"
Write-Host "  make dev-down    - Stop development environment"  
Write-Host "  make dev-logs    - View development logs"
Write-Host "  make test-dev    - Run tests in local environment"
Write-Host "  make pre-commit  - Run code quality checks"
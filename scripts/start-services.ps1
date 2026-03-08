#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Start LLMCrawl services

.DESCRIPTION
    Starts LLMCrawl services:
    - Docker containers: infrastructure, crawler, indexer, MCP servers
    - Local processes: gateway, memory-service (for local filesystem access)

.PARAMETER Build
    Build Docker images before starting

.PARAMETER Logs
    Follow logs after starting

.PARAMETER Infrastructure
    Start only infrastructure services (redis, postgres, qdrant, playwright)

.PARAMETER DockerOnly
    Start only Docker services, skip local services (gateway, memory)

.EXAMPLE
    .\scripts\start-services.ps1

.EXAMPLE
    .\scripts\start-services.ps1 -Build -Logs
#>

param(
    [switch]$Build,
    [switch]$Logs,
    [switch]$Infrastructure,
    [switch]$DockerOnly
)

$ErrorActionPreference = "Stop"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " Starting LLMCrawl Services" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Get project root
$ProjectRoot = (Get-Item $PSScriptRoot).Parent.FullName
$DeployPath = Join-Path $ProjectRoot "deploy"

if (-not (Test-Path $DeployPath)) {
    Write-Error "Deploy directory not found at $DeployPath"
    exit 1
}

Push-Location $DeployPath

try {
    # Check if .env file exists
    if (-not (Test-Path ".env")) {
        Write-Host "`nWarning: .env file not found. Copy .env.example to .env" -ForegroundColor Yellow
    }

    # Create network if it doesn't exist
    $NetworkExists = docker network ls --format "{{.Name}}" | Where-Object { $_ -eq "webrag-network" }
    if (-not $NetworkExists) {
        Write-Host "`nCreating webrag-network..." -ForegroundColor Yellow
        docker network create webrag-network
    }

    # Build command arguments for Docker services
    $Args = @("up", "-d")

    if ($Build) {
        $Args += "--build"
        Write-Host "`nMode: BUILD + START" -ForegroundColor Yellow
    } else {
        Write-Host "`nMode: START (use -Build to rebuild images)" -ForegroundColor Yellow
    }

    if ($Infrastructure) {
        $Args += @("redis", "postgres", "qdrant", "playwright")
        Write-Host "Target: Infrastructure only" -ForegroundColor White
    }

    Write-Host "`nStarting Docker containers..." -ForegroundColor Cyan
    Write-Host "Executing: docker compose -f docker-compose.dev.yml $($Args -join ' ')" -ForegroundColor Gray
    Write-Host ""

    # Start Docker services
    & docker compose -f docker-compose.dev.yml @Args

    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nFailed to start Docker services. Check docker compose logs for details." -ForegroundColor Red
        exit 1
    }

    Write-Host "`nDocker containers started." -ForegroundColor Green

    # Start local services (gateway and memory) unless Infrastructure only or DockerOnly
    if (-not $Infrastructure -and -not $DockerOnly) {
        Write-Host "`nStarting local services..." -ForegroundColor Cyan

        # Change to project root for local services
        Push-Location $ProjectRoot

        try {
            # Create logs directory
            $LogsDir = Join-Path $DeployPath "logs"
            if (-not (Test-Path $LogsDir)) {
                New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
            }

            # Create memory directory if needed
            $MemoryDataPath = Join-Path $DeployPath "memory"
            if (-not (Test-Path $MemoryDataPath)) {
                New-Item -ItemType Directory -Path $MemoryDataPath -Force | Out-Null
                New-Item -ItemType Directory -Path (Join-Path $MemoryDataPath "daily") -Force | Out-Null
            }

            # Determine Python executable (prefer venv)
            $PythonExe = if (Test-Path "$ProjectRoot\venv\Scripts\python.exe") {
                "$ProjectRoot\venv\Scripts\python.exe"
            } else {
                "python"
            }
            Write-Host "  Using Python: $PythonExe" -ForegroundColor Gray

            # Set environment variables for child processes
            $env:MEMORY_DATA_PATH = $MemoryDataPath
            $env:EMBEDDING_PROVIDER = "local"
            $env:MILVUS_URI = "http://localhost:19530"

            # Start Memory Service
            Write-Host "  Starting Memory Service (port 8007)..." -ForegroundColor White
            $MemoryLogFile = Join-Path $LogsDir "memory-service.log"

            # Start memory service in background
            $MemoryProcess = Start-Process -FilePath $PythonExe `
                -ArgumentList "-m", "uvicorn", "services.memory_service.main:app", "--host", "0.0.0.0", "--port", "8007" `
                -WorkingDirectory $ProjectRoot `
                -RedirectStandardOutput $MemoryLogFile `
                -RedirectStandardError "$MemoryLogFile.err" `
                -PassThru `
                -WindowStyle Hidden

            Write-Host "    PID: $($MemoryProcess.Id)" -ForegroundColor Gray

            # Start Gateway
            Write-Host "  Starting Gateway (port 8000)..." -ForegroundColor White
            $GatewayLogFile = Join-Path $LogsDir "gateway.log"

            # Load .env file if exists (for API keys, etc.)
            $EnvFile = Join-Path $DeployPath ".env"
            if (Test-Path $EnvFile) {
                Get-Content $EnvFile | ForEach-Object {
                    if ($_ -match "^([^#][^=]+)=(.*)$") {
                        Set-Item -Path "env:$($matches[1].Trim())" -Value $matches[2].Trim()
                    }
                }
            }

            # Set gateway environment variables
            $env:GATEWAY_HOST = "0.0.0.0"
            $env:GATEWAY_PORT = "8000"
            $env:CRAWLER_URL = "http://localhost:8001"
            $env:INDEXER_URL = "http://localhost:8002"
            $env:MCP_SERVER_URL = "http://localhost:8003"
            $env:AZURE_DEVOPS_MCP_URL = "http://localhost:8004"
            $env:MEMORY_SERVICE_URL = "http://localhost:8007"
            $env:MEMORY_DATA_PATH = $MemoryDataPath
            $env:MEMORY_AUTO_LOG = "true"
            $env:MEMORY_AUTO_FLUSH = "true"
            $env:ENVIRONMENT = "development"
            $env:LOG_LEVEL = "DEBUG"
            # Override bridge URLs for local gateway (use localhost, not host.docker.internal)
            $env:CLAUDE_BRIDGE_URL = "http://localhost:8006"
            $env:WIN_COMP_BRIDGE_URL = "http://localhost:8005"

            # Start gateway in background
            $GatewayProcess = Start-Process -FilePath $PythonExe `
                -ArgumentList "-m", "uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000" `
                -WorkingDirectory $ProjectRoot `
                -RedirectStandardOutput $GatewayLogFile `
                -RedirectStandardError "$GatewayLogFile.err" `
                -PassThru `
                -WindowStyle Hidden

            Write-Host "    PID: $($GatewayProcess.Id)" -ForegroundColor Gray

            # Save PIDs for stop script
            $PidFile = Join-Path $DeployPath "local-services.pid"
            @{
                gateway = $GatewayProcess.Id
                memory = $MemoryProcess.Id
            } | ConvertTo-Json | Set-Content $PidFile

            Write-Host "`nLocal services started. PIDs saved to deploy/local-services.pid" -ForegroundColor Green
        }
        finally {
            Pop-Location
        }
    }

    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host " Services started successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green

    # Show status
    Write-Host "`nDocker Container Status:" -ForegroundColor Cyan
    docker compose -f docker-compose.dev.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

    Write-Host "`nService URLs:" -ForegroundColor Cyan
    Write-Host "  Gateway (local):      http://localhost:8000" -ForegroundColor White
    Write-Host "  Memory Service (local): http://localhost:8007" -ForegroundColor White
    Write-Host "  Crawler:              http://localhost:8001" -ForegroundColor White
    Write-Host "  Indexer:              http://localhost:8002" -ForegroundColor White
    Write-Host "  MCP Server:           http://localhost:8003" -ForegroundColor White
    Write-Host "  Azure DevOps MCP:     http://localhost:8004" -ForegroundColor White
    Write-Host "  Qdrant:               http://localhost:6333" -ForegroundColor White
    Write-Host "  Redis:                localhost:6379" -ForegroundColor White
    Write-Host "  PostgreSQL:           localhost:5432" -ForegroundColor White

    Write-Host "`nUseful commands:" -ForegroundColor Yellow
    Write-Host "  View gateway logs:  Get-Content deploy/logs/gateway.log -Wait" -ForegroundColor Gray
    Write-Host "  View memory logs:   Get-Content deploy/logs/memory-service.log -Wait" -ForegroundColor Gray
    Write-Host "  Stop:               .\scripts\stop-services.ps1" -ForegroundColor Gray
    Write-Host "  Restart:            .\scripts\restart-services.ps1 -Build" -ForegroundColor Gray
    Write-Host "  Health check:       make health" -ForegroundColor Gray

    # Follow logs if requested
    if ($Logs) {
        Write-Host "`nFollowing Docker logs (Ctrl+C to exit)..." -ForegroundColor Yellow
        docker compose -f docker-compose.dev.yml logs -f crawler indexer mcp-server
    }
}
finally {
    Pop-Location
}

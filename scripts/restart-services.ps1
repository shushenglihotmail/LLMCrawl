#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Restart LLMCrawl services with optional rebuild

.DESCRIPTION
    Restarts LLMCrawl services with full control over rebuild behavior.
    - Docker services: crawler, indexer, mcp-server, azure-devops-mcp-server
    - Local services: gateway, memory-service (run on host for filesystem access)

.PARAMETER Service
    Optional. Restart only specific service(s). Can be comma-separated.
    Docker services: crawler, indexer, mcp-server, azure-devops-mcp-server
    Local services: gateway, memory

.PARAMETER Build
    Rebuild Docker images before starting (picks up code changes)

.PARAMETER Full
    Full rebuild with no cache (use after dependency changes)

.PARAMETER Logs
    Follow logs after restart

.PARAMETER DockerOnly
    Restart only Docker services, skip local services

.EXAMPLE
    .\scripts\restart-services.ps1
    # Restart all services

.EXAMPLE
    .\scripts\restart-services.ps1 -Build
    # Rebuild Docker images and restart all services

.EXAMPLE
    .\scripts\restart-services.ps1 -Service gateway
    # Restart only gateway (local service)

.EXAMPLE
    .\scripts\restart-services.ps1 -Service crawler -Build -Logs
    # Rebuild crawler, restart, then follow logs
#>

param(
    [string[]]$Service,
    [switch]$Build,
    [switch]$Full,
    [switch]$Logs,
    [switch]$DockerOnly
)

$ErrorActionPreference = "Stop"

# Get project root
$ProjectRoot = (Get-Item $PSScriptRoot).Parent.FullName
$DeployPath = Join-Path $ProjectRoot "deploy"

if (-not (Test-Path $DeployPath)) {
    Write-Error "Deploy directory not found at $DeployPath"
    exit 1
}

# Define which services are local vs Docker
$LocalServices = @("gateway", "memory")
$DockerServices = @("crawler", "indexer", "mcp-server", "azure-devops-mcp-server", "firecrawl", "playwright", "redis", "postgres", "qdrant")

Push-Location $DeployPath

try {
    # Parse services - handle both array and comma-separated string
    $Services = @()
    if ($Service) {
        foreach ($s in $Service) {
            # Split each element by comma in case of "gateway,memory" format
            $Services += ($s -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        }
    }

    # Separate local and Docker services
    $LocalToRestart = @()
    $DockerToRestart = @()

    if ($Services.Count -gt 0) {
        foreach ($svc in $Services) {
            if ($LocalServices -contains $svc) {
                $LocalToRestart += $svc
            } elseif ($DockerServices -contains $svc) {
                $DockerToRestart += $svc
            } else {
                Write-Host "Warning: Unknown service '$svc'" -ForegroundColor Yellow
            }
        }
    } else {
        # Restart all
        $LocalToRestart = $LocalServices
        $DockerToRestart = @()  # Empty means all Docker services
    }

    $ServiceDisplay = if ($Services.Count -gt 0) { $Services -join ", " } else { "all services" }

    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host " LLMCrawl Service Manager" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    # Determine operation mode
    if ($Full) {
        Write-Host "`nMode: FULL REBUILD (no cache)" -ForegroundColor Yellow
    } elseif ($Build) {
        Write-Host "`nMode: REBUILD + RESTART" -ForegroundColor Yellow
    } else {
        Write-Host "`nMode: RESTART" -ForegroundColor Yellow
    }
    Write-Host "Target: $ServiceDisplay" -ForegroundColor White

    # Restart local services (unless DockerOnly)
    if (-not $DockerOnly -and $LocalToRestart.Count -gt 0) {
        Write-Host "`nRestarting local services..." -ForegroundColor Cyan

        $PidFile = Join-Path $DeployPath "local-services.pid"
        $Pids = @{}
        if (Test-Path $PidFile) {
            $JsonObj = Get-Content $PidFile | ConvertFrom-Json
            # Convert PSCustomObject to hashtable so we can add/modify properties
            $JsonObj.PSObject.Properties | ForEach-Object { $Pids[$_.Name] = $_.Value }
        }

        # Stop requested local services
        foreach ($svc in $LocalToRestart) {
            $pidKey = if ($svc -eq "memory") { "memory" } else { $svc }
            if ($Pids.$pidKey) {
                Write-Host "  Stopping $svc (PID: $($Pids.$pidKey))..." -ForegroundColor White
                try {
                    Stop-Process -Id $Pids.$pidKey -Force -ErrorAction SilentlyContinue
                } catch { }
            }
        }

        # Create logs directory
        $LogsDir = Join-Path $DeployPath "logs"
        if (-not (Test-Path $LogsDir)) {
            New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
        }

        # Load .env file first to get MEMORY_DATA_PATH and other settings
        $EnvFile = Join-Path $DeployPath ".env"
        if (Test-Path $EnvFile) {
            Get-Content $EnvFile | ForEach-Object {
                if ($_ -match "^([^#][^=]+)=(.*)$") {
                    Set-Item -Path "env:$($matches[1].Trim())" -Value $matches[2].Trim()
                }
            }
        }

        # Determine memory data path (from .env or default)
        $MemoryDataPath = $env:MEMORY_DATA_PATH
        if (-not $MemoryDataPath) {
            $MemoryDataPath = "./memory"
        }
        # Resolve relative paths (relative to deploy folder)
        if (-not [System.IO.Path]::IsPathRooted($MemoryDataPath)) {
            $MemoryDataPath = [System.IO.Path]::GetFullPath((Join-Path $DeployPath $MemoryDataPath))
        }
        Write-Host "  Memory data path: $MemoryDataPath" -ForegroundColor Gray

        # Create memory directory if needed
        if (-not (Test-Path $MemoryDataPath)) {
            New-Item -ItemType Directory -Path $MemoryDataPath -Force | Out-Null
            New-Item -ItemType Directory -Path (Join-Path $MemoryDataPath "daily") -Force | Out-Null
        }

        Push-Location $ProjectRoot

        try {
            # Determine Python executable (prefer venv)
            $PythonExe = if (Test-Path "$ProjectRoot\venv\Scripts\python.exe") {
                "$ProjectRoot\venv\Scripts\python.exe"
            } else {
                "python"
            }
            Write-Host "  Using Python: $PythonExe" -ForegroundColor Gray

            # Start Memory Service if needed
            if ($LocalToRestart -contains "memory") {
                Write-Host "  Starting Memory Service (port 8007)..." -ForegroundColor White
                $MemoryLogFile = Join-Path $LogsDir "memory-service.log"

                # Set environment for child processes
                $env:MEMORY_DATA_PATH = $MemoryDataPath
                $env:EMBEDDING_PROVIDER = "local"
                $env:MILVUS_URI = "http://localhost:19530"

                $MemoryProcess = Start-Process -FilePath $PythonExe `
                    -ArgumentList "-m", "uvicorn", "services.memory_service.main:app", "--host", "0.0.0.0", "--port", "8007" `
                    -WorkingDirectory $ProjectRoot `
                    -RedirectStandardOutput $MemoryLogFile `
                    -RedirectStandardError "$MemoryLogFile.err" `
                    -PassThru `
                    -WindowStyle Hidden

                $Pids.memory = $MemoryProcess.Id
                Write-Host "    PID: $($MemoryProcess.Id)" -ForegroundColor Gray
            }

            # Start Gateway if needed
            if ($LocalToRestart -contains "gateway") {
                Write-Host "  Starting Gateway (port 8000)..." -ForegroundColor White
                $GatewayLogFile = Join-Path $LogsDir "gateway.log"

                # Set environment for child processes
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

                $GatewayProcess = Start-Process -FilePath $PythonExe `
                    -ArgumentList "-m", "uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000" `
                    -WorkingDirectory $ProjectRoot `
                    -RedirectStandardOutput $GatewayLogFile `
                    -RedirectStandardError "$GatewayLogFile.err" `
                    -PassThru `
                    -WindowStyle Hidden

                $Pids.gateway = $GatewayProcess.Id
                Write-Host "    PID: $($GatewayProcess.Id)" -ForegroundColor Gray
            }

            # Save PIDs
            $Pids | ConvertTo-Json | Set-Content $PidFile
            Write-Host "`nLocal services restarted." -ForegroundColor Green
        }
        finally {
            Pop-Location
        }
    }

    # Restart Docker services
    if (-not ($LocalToRestart.Count -gt 0 -and $Services.Count -gt 0 -and $DockerToRestart.Count -eq 0)) {
        Write-Host "`nRestarting Docker containers..." -ForegroundColor Cyan

        # For -Full, we need to run build separately with --no-cache
        if ($Full) {
            $BuildArgs = @("build", "--no-cache")
            if ($DockerToRestart.Count -gt 0) {
                $BuildArgs += $DockerToRestart
            }

            Write-Host "Executing: docker compose -f docker-compose.dev.yml $($BuildArgs -join ' ')" -ForegroundColor Gray
            & docker compose -f docker-compose.dev.yml @BuildArgs

            if ($LASTEXITCODE -ne 0) {
                Write-Host "`nFailed to build services" -ForegroundColor Red
                exit 1
            }
        }

        # Build the up arguments
        $Args = @("up", "-d")

        if ($Full -or $Build) {
            $Args += "--build"
            $Args += "--force-recreate"
        } else {
            $Args += "--force-recreate"
        }

        # Add specific services if specified
        if ($DockerToRestart.Count -gt 0) {
            $Args += $DockerToRestart
        }

        Write-Host "Executing: docker compose -f docker-compose.dev.yml $($Args -join ' ')" -ForegroundColor Gray
        & docker compose -f docker-compose.dev.yml @Args

        if ($LASTEXITCODE -ne 0) {
            Write-Host "`nFailed to restart Docker services" -ForegroundColor Red
            exit 1
        }

        Write-Host "`nDocker containers restarted." -ForegroundColor Green
    }

    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host " Services restarted successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green

    # Show service status
    Write-Host "`nDocker Container Status:" -ForegroundColor Cyan
    docker compose -f docker-compose.dev.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

    Write-Host "`nService URLs:" -ForegroundColor Cyan
    Write-Host "  Gateway (local):      http://localhost:8000" -ForegroundColor White
    Write-Host "  Memory Service (local): http://localhost:8007" -ForegroundColor White
    Write-Host "  Crawler:              http://localhost:8001" -ForegroundColor White
    Write-Host "  Indexer:              http://localhost:8002" -ForegroundColor White
    Write-Host "  MCP Server:           http://localhost:8003" -ForegroundColor White
    Write-Host "  Azure DevOps MCP:     http://localhost:8004" -ForegroundColor White

    Write-Host "`nHealth Check:" -ForegroundColor Cyan
    Write-Host "  make health" -ForegroundColor Gray

    # Follow logs if requested
    if ($Logs) {
        Write-Host "`nFollowing Docker logs (Ctrl+C to exit)..." -ForegroundColor Yellow
        if ($DockerToRestart.Count -gt 0) {
            docker compose -f docker-compose.dev.yml logs -f @DockerToRestart
        } else {
            docker compose -f docker-compose.dev.yml logs -f crawler indexer mcp-server
        }
    }
}
finally {
    Pop-Location
}

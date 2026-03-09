#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Stop LLMCrawl services

.DESCRIPTION
    Stops LLMCrawl services:
    - Docker containers (via docker compose)
    - Local processes (gateway, memory-service)

.PARAMETER Remove
    Remove containers after stopping (keeps volumes)

.PARAMETER Volumes
    Also remove volumes (WARNING: deletes all data!)

.PARAMETER Service
    Stop only specific service(s). Can be comma-separated.

.PARAMETER DockerOnly
    Stop only Docker services, skip local services

.EXAMPLE
    .\scripts\stop-services.ps1
    # Stop all services (containers preserved)

.EXAMPLE
    .\scripts\stop-services.ps1 -Remove
    # Stop and remove containers (keeps data volumes)

.EXAMPLE
    .\scripts\stop-services.ps1 -Service crawler,indexer
    # Stop only crawler and indexer Docker containers

.EXAMPLE
    .\scripts\stop-services.ps1 -Remove -Volumes
    # Full cleanup including data (WARNING!)
#>

param(
    [switch]$Remove,
    [switch]$Volumes,
    [string[]]$Service,
    [switch]$DockerOnly
)

$ErrorActionPreference = "Stop"

Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host " Stopping LLMCrawl Services" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

# Get project root
$ProjectRoot = (Get-Item $PSScriptRoot).Parent.FullName
$DeployPath = Join-Path $ProjectRoot "deploy"

if (-not (Test-Path $DeployPath)) {
    Write-Error "Deploy directory not found at $DeployPath"
    exit 1
}

# Define which services are local vs Docker
$LocalServices = @("gateway", "memory")
$DockerServices = @("crawler", "indexer", "mcp-server", "azure-devops-mcp-server", "firecrawl", "playwright", "redis", "postgres", "qdrant", "milvus")

# Parse services - handle both array and comma-separated string
$RequestedServices = @()
if ($Service) {
    foreach ($s in $Service) {
        $RequestedServices += ($s -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    }
}

# Separate local and Docker services
$LocalToStop = @()
$DockerToStop = @()

if ($RequestedServices.Count -gt 0) {
    foreach ($svc in $RequestedServices) {
        if ($LocalServices -contains $svc) {
            $LocalToStop += $svc
        } elseif ($DockerServices -contains $svc) {
            $DockerToStop += $svc
        } else {
            Write-Host "Warning: Unknown service '$svc'" -ForegroundColor Yellow
        }
    }
} else {
    # Stop all
    $LocalToStop = $LocalServices
    $DockerToStop = @()  # Empty means all Docker services
}

Push-Location $DeployPath

try {
    # Stop local services (unless DockerOnly)
    if (-not $DockerOnly -and ($LocalToStop.Count -gt 0 -or $RequestedServices.Count -eq 0)) {
        Write-Host "`nStopping local services..." -ForegroundColor Cyan

        $PidFile = Join-Path $DeployPath "local-services.pid"
        if (Test-Path $PidFile) {
            $Pids = Get-Content $PidFile | ConvertFrom-Json
            $NewPids = @{}

            # Stop Gateway if requested
            if (($LocalToStop -contains "gateway") -or $RequestedServices.Count -eq 0) {
                if ($Pids.gateway) {
                    Write-Host "  Stopping Gateway (PID: $($Pids.gateway))..." -ForegroundColor White
                    try {
                        $proc = Get-Process -Id $Pids.gateway -ErrorAction SilentlyContinue
                        if ($proc) {
                            Stop-Process -Id $Pids.gateway -Force -ErrorAction SilentlyContinue
                            Write-Host "    Stopped." -ForegroundColor Green
                        } else {
                            Write-Host "    Not running." -ForegroundColor Gray
                        }
                    } catch {
                        Write-Host "    Already stopped." -ForegroundColor Gray
                    }
                }
            } else {
                # Keep gateway PID if not stopping it
                if ($Pids.gateway) { $NewPids.gateway = $Pids.gateway }
            }

            # Stop Memory Service if requested
            if (($LocalToStop -contains "memory") -or $RequestedServices.Count -eq 0) {
                if ($Pids.memory) {
                    Write-Host "  Stopping Memory Service (PID: $($Pids.memory))..." -ForegroundColor White
                    try {
                        $proc = Get-Process -Id $Pids.memory -ErrorAction SilentlyContinue
                        if ($proc) {
                            Stop-Process -Id $Pids.memory -Force -ErrorAction SilentlyContinue
                            Write-Host "    Stopped." -ForegroundColor Green
                        } else {
                            Write-Host "    Not running." -ForegroundColor Gray
                        }
                    } catch {
                        Write-Host "    Already stopped." -ForegroundColor Gray
                    }
                }
            } else {
                # Keep memory PID if not stopping it
                if ($Pids.memory) { $NewPids.memory = $Pids.memory }
            }

            # Update or remove PID file
            if ($NewPids.Count -gt 0) {
                $NewPids | ConvertTo-Json | Set-Content $PidFile
            } else {
                Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
            }
        } else {
            Write-Host "  No local services PID file found." -ForegroundColor Gray

            # Try to find and kill any running uvicorn processes for gateway/memory
            $uvicornProcs = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
                $_.CommandLine -match "gateway\.main:app|memory_service\.main:app"
            }
            if ($uvicornProcs) {
                Write-Host "  Found running uvicorn processes, stopping..." -ForegroundColor Yellow
                $uvicornProcs | Stop-Process -Force -ErrorAction SilentlyContinue
            }
        }

        # Kill any orphan processes still listening on service ports (uvicorn reload spawns children)
        $PortsToClean = @()
        if (($LocalToStop -contains "gateway") -or $RequestedServices.Count -eq 0) { $PortsToClean += 8000 }
        if (($LocalToStop -contains "memory") -or $RequestedServices.Count -eq 0) { $PortsToClean += 8007 }

        foreach ($Port in $PortsToClean) {
            $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
            if ($listeners) {
                Write-Host "  Cleaning up orphan processes on port $Port..." -ForegroundColor Yellow
                foreach ($conn in $listeners) {
                    try {
                        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
                    } catch { }
                }
            }
        }
    }

    if ($Volumes -and -not $Remove) {
        Write-Host "`nError: -Volumes requires -Remove flag" -ForegroundColor Red
        exit 1
    }

    if ($Volumes) {
        Write-Host "`nWARNING: This will delete ALL data volumes!" -ForegroundColor Red
        $confirm = Read-Host "Type 'yes' to confirm"
        if ($confirm -ne 'yes') {
            Write-Host "Cancelled." -ForegroundColor Yellow
            exit 0
        }
    }

    # Only stop Docker containers if needed
    $ShouldStopDocker = ($DockerToStop.Count -gt 0) -or ($RequestedServices.Count -eq 0)

    if ($ShouldStopDocker) {
        Write-Host "`nStopping Docker containers..." -ForegroundColor Cyan

        if ($Remove) {
            $Args = @("down")
            if ($Volumes) {
                $Args += "-v"
                Write-Host "Mode: STOP + REMOVE CONTAINERS + REMOVE VOLUMES" -ForegroundColor Red
            } else {
                Write-Host "Mode: STOP + REMOVE CONTAINERS (volumes preserved)" -ForegroundColor Yellow
            }

            Write-Host "Executing: docker compose -f docker-compose.dev.yml $($Args -join ' ')" -ForegroundColor Gray
            & docker compose -f docker-compose.dev.yml @Args

            Write-Host "`nDocker containers stopped and removed." -ForegroundColor Green
        } else {
            if ($DockerToStop.Count -gt 0) {
                Write-Host "Mode: STOP (containers preserved)" -ForegroundColor Yellow
                Write-Host "Target: $($DockerToStop -join ', ')" -ForegroundColor White
                & docker compose -f docker-compose.dev.yml stop @DockerToStop
            } else {
                Write-Host "Mode: STOP ALL (containers preserved)" -ForegroundColor Yellow
                docker compose -f docker-compose.dev.yml stop
            }

            Write-Host "`nDocker containers stopped (preserved)." -ForegroundColor Green
        }

        if ($LASTEXITCODE -ne 0) {
            Write-Host "`nFailed to stop Docker services. Check docker status." -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "`nNo Docker containers to stop." -ForegroundColor Gray
    }

    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host " All services stopped." -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green

    Write-Host "`nTo restart: .\scripts\restart-services.ps1" -ForegroundColor Gray
}
finally {
    Pop-Location
}

#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Start LLMCrawl services

.DESCRIPTION
    Starts LLMCrawl services using docker compose.
    Creates the network if it doesn't exist.

.PARAMETER Build
    Build images before starting

.PARAMETER Logs
    Follow logs after starting

.PARAMETER Infrastructure
    Start only infrastructure services (redis, postgres, qdrant, playwright)

.EXAMPLE
    .\scripts\start-services.ps1

.EXAMPLE
    .\scripts\start-services.ps1 -Build -Logs
#>

param(
    [switch]$Build,
    [switch]$Logs,
    [switch]$Infrastructure
)

$ErrorActionPreference = "Stop"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " Starting LLMCrawl Services" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Ensure we are in the deploy directory
$DeployPath = Join-Path $PSScriptRoot "../deploy"
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

    # Build command arguments
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

    Write-Host "`nExecuting: docker compose -f docker-compose.yml $($Args -join ' ')" -ForegroundColor Gray
    Write-Host ""

    # Start services
    & docker compose -f docker-compose.yml @Args

    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nFailed to start services. Check docker compose logs for details." -ForegroundColor Red
        exit 1
    }

    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host " Services started successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green

    # Show status
    Write-Host "`nService Status:" -ForegroundColor Cyan
    docker compose -f docker-compose.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

    Write-Host "`nService URLs:" -ForegroundColor Cyan
    Write-Host "  Gateway:           http://localhost:8000" -ForegroundColor White
    Write-Host "  Crawler:           http://localhost:8001" -ForegroundColor White
    Write-Host "  Indexer:           http://localhost:8002" -ForegroundColor White
    Write-Host "  MCP Server:        http://localhost:8003" -ForegroundColor White
    Write-Host "  Azure DevOps MCP:  http://localhost:8004" -ForegroundColor White
    Write-Host "  Qdrant:            http://localhost:6333" -ForegroundColor White
    Write-Host "  Redis:             localhost:6379" -ForegroundColor White
    Write-Host "  PostgreSQL:        localhost:5432" -ForegroundColor White

    Write-Host "`nUseful commands:" -ForegroundColor Yellow
    Write-Host "  View logs:     docker compose -f deploy/docker-compose.yml logs -f gateway" -ForegroundColor Gray
    Write-Host "  Stop:          .\scripts\stop-services.ps1" -ForegroundColor Gray
    Write-Host "  Restart:       .\scripts\restart-services.ps1 -Build" -ForegroundColor Gray

    # Follow logs if requested
    if ($Logs) {
        Write-Host "`nFollowing logs (Ctrl+C to exit)..." -ForegroundColor Yellow
        docker compose -f docker-compose.yml logs -f gateway crawler indexer mcp-server
    }
}
finally {
    Pop-Location
}

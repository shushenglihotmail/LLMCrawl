#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Start all LLMCrawl services in development mode

.DESCRIPTION
    Starts all LLMCrawl services using docker-compose with development configuration.
    Services include: gateway, crawler, indexer, mcp-server, and supporting infrastructure.

.EXAMPLE
    .\scripts\start-services.ps1
#>

Write-Host "Starting LLMCrawl services..." -ForegroundColor Green

# Ensure we are in the deploy directory where docker-compose files are located
$DeployPath = Join-Path $PSScriptRoot "../deploy"
if (-not (Test-Path $DeployPath)) {
    Write-Error "Deploy directory not found at $DeployPath"
    exit 1
}
Push-Location $DeployPath

try {
    # Check if .env file exists
    if (-not (Test-Path ".env")) {
        Write-Host "Warning: .env file not found. Using default configuration." -ForegroundColor Yellow
    }

    # Start services using docker-compose
    docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

    if ($LASTEXITCODE -eq 0) {
        Write-Host "`nServices started successfully!" -ForegroundColor Green
        Write-Host "`nService URLs:" -ForegroundColor Cyan
        Write-Host "  Gateway:    http://localhost:8000" -ForegroundColor White
        Write-Host "  Crawler:    http://localhost:8001" -ForegroundColor White
        Write-Host "  Indexer:    http://localhost:8002" -ForegroundColor White
        Write-Host "  MCP Server: http://localhost:8003" -ForegroundColor White
        Write-Host "  Qdrant:     http://localhost:6333" -ForegroundColor White
        Write-Host "  Redis:      localhost:6379" -ForegroundColor White
        Write-Host "  PostgreSQL: localhost:5432" -ForegroundColor White
        Write-Host "`nTo view logs: docker-compose logs -f" -ForegroundColor Yellow
        Write-Host "To stop services: .\scripts\stop-services.ps1" -ForegroundColor Yellow
    } else {
        Write-Host "`nFailed to start services. Check docker-compose logs for details." -ForegroundColor Red
        exit 1
    }
}
finally {
    Pop-Location
}

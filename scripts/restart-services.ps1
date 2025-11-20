#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Restart all LLMCrawl services

.DESCRIPTION
    Restarts all LLMCrawl services by stopping and starting them.
    Useful after updating .env configuration or code changes that require full restart.

.PARAMETER Service
    Optional. Restart only a specific service (gateway, crawler, indexer, mcp-server)

.EXAMPLE
    .\scripts\restart-services.ps1

.EXAMPLE
    .\scripts\restart-services.ps1 -Service gateway
#>

param(
    [string]$Service
)

Write-Host "Restarting LLMCrawl services..." -ForegroundColor Cyan

if ($Service) {
    Write-Host "Restarting $Service only..." -ForegroundColor Yellow
    docker-compose -f docker-compose.yml -f docker-compose.dev.yml restart $Service

    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n$Service restarted successfully!" -ForegroundColor Green
    } else {
        Write-Host "`nFailed to restart $Service" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "Restarting all services..." -ForegroundColor Yellow
    docker-compose -f docker-compose.yml -f docker-compose.dev.yml restart

    if ($LASTEXITCODE -eq 0) {
        Write-Host "`nAll services restarted successfully!" -ForegroundColor Green
        Write-Host "`nService URLs:" -ForegroundColor Cyan
        Write-Host "  Gateway:    http://localhost:8000" -ForegroundColor White
        Write-Host "  Crawler:    http://localhost:8001" -ForegroundColor White
        Write-Host "  Indexer:    http://localhost:8002" -ForegroundColor White
        Write-Host "  MCP Server: http://localhost:8003" -ForegroundColor White
    } else {
        Write-Host "`nFailed to restart services" -ForegroundColor Red
        exit 1
    }
}

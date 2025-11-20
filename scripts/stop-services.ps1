#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Stop all LLMCrawl services

.DESCRIPTION
    Stops all running LLMCrawl services using docker-compose.
    This preserves data volumes.

.PARAMETER Remove
    If specified, also removes containers and networks (but keeps volumes)

.EXAMPLE
    .\scripts\stop-services.ps1

.EXAMPLE
    .\scripts\stop-services.ps1 -Remove
#>

param(
    [switch]$Remove
)

Write-Host "Stopping LLMCrawl services..." -ForegroundColor Yellow

if ($Remove) {
    # Stop and remove containers and networks
    docker-compose -f docker-compose.yml -f docker-compose.dev.yml down
    Write-Host "Services stopped and containers removed." -ForegroundColor Green
} else {
    # Just stop containers
    docker-compose -f docker-compose.yml -f docker-compose.dev.yml stop
    Write-Host "Services stopped (containers preserved)." -ForegroundColor Green
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nTo restart services: .\scripts\start-services.ps1" -ForegroundColor Yellow
} else {
    Write-Host "`nFailed to stop services. Check docker status." -ForegroundColor Red
    exit 1
}

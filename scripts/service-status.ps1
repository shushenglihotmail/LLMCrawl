#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Check status of all LLMCrawl services

.DESCRIPTION
    Shows the running status and health of all LLMCrawl services.
    Displays container status and health check results.

.EXAMPLE
    .\scripts\service-status.ps1
#>

Write-Host "LLMCrawl Service Status" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Gray

# Check docker-compose services
Write-Host "`nDocker Containers:" -ForegroundColor Yellow
docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps

# Check health endpoints
Write-Host "`n`nService Health Checks:" -ForegroundColor Yellow
Write-Host "-" * 60 -ForegroundColor Gray

$services = @{
    "Gateway"    = "http://localhost:8000/health"
    "Crawler"    = "http://localhost:8001/health"
    "Indexer"    = "http://localhost:8002/health"
    "MCP Server" = "http://localhost:8003/health"
    "Qdrant"     = "http://localhost:6333/health"
}

foreach ($service in $services.GetEnumerator()) {
    try {
        $response = Invoke-RestMethod -Uri $service.Value -TimeoutSec 2 -ErrorAction Stop
        $status = if ($response.status -eq "healthy" -or $response.status -eq "ok") { "✓" } else { "?" }
        Write-Host "  $($service.Key): " -NoNewline
        Write-Host "$status Healthy" -ForegroundColor Green
    } catch {
        Write-Host "  $($service.Key): " -NoNewline
        Write-Host "✗ Unavailable" -ForegroundColor Red
    }
}

Write-Host "`n" -NoNewline
Write-Host "=" * 60 -ForegroundColor Gray
Write-Host "`nTip: View logs with: docker-compose logs -f [service-name]" -ForegroundColor Yellow

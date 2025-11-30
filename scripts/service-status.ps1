#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Check status of all LLMCrawl services

.DESCRIPTION
    Shows the running status and health of all LLMCrawl services.
    Displays container status and health check results.

.PARAMETER Watch
    Continuously monitor status (refresh every 5 seconds)

.EXAMPLE
    .\scripts\service-status.ps1

.EXAMPLE
    .\scripts\service-status.ps1 -Watch
#>

param(
    [switch]$Watch
)

function Show-Status {
    Clear-Host
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host " LLMCrawl Service Status" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray

    # Ensure we are in the deploy directory
    $DeployPath = Join-Path $PSScriptRoot "../deploy"
    if (-not (Test-Path $DeployPath)) {
        Write-Error "Deploy directory not found at $DeployPath"
        return
    }
    Push-Location $DeployPath

    try {
        # Check docker compose services
        Write-Host "`nContainer Status:" -ForegroundColor Yellow
        docker compose -f docker-compose.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
    }
    finally {
        Pop-Location
    }

    # Check health endpoints
    Write-Host "`nHealth Checks:" -ForegroundColor Yellow

    $services = @(
        @{ Name = "Gateway"; Url = "http://localhost:8000/health" }
        @{ Name = "Crawler"; Url = "http://localhost:8001/health" }
        @{ Name = "Indexer"; Url = "http://localhost:8002/health" }
        @{ Name = "MCP Server"; Url = "http://localhost:8003/health" }
        @{ Name = "Azure DevOps MCP"; Url = "http://localhost:8004/health" }
        @{ Name = "Qdrant"; Url = "http://localhost:6333/healthz" }
    )

    foreach ($service in $services) {
        try {
            $response = Invoke-RestMethod -Uri $service.Url -TimeoutSec 2 -ErrorAction Stop
            $status = if ($response.status -eq "healthy" -or $response.status -eq "ok" -or $response.title) { "✓" } else { "?" }
            Write-Host "  $($service.Name.PadRight(18)): " -NoNewline
            Write-Host "$status Healthy" -ForegroundColor Green
        }
        catch {
            Write-Host "  $($service.Name.PadRight(18)): " -NoNewline
            Write-Host "✗ Unavailable" -ForegroundColor Red
        }
    }

    Write-Host "`nUseful Commands:" -ForegroundColor Yellow
    Write-Host "  Restart with rebuild:  .\scripts\restart-services.ps1 -Build" -ForegroundColor Gray
    Write-Host "  View logs:             docker compose -f deploy/docker-compose.yml logs -f gateway" -ForegroundColor Gray
    Write-Host "  Stop all:              .\scripts\stop-services.ps1" -ForegroundColor Gray
}

if ($Watch) {
    Write-Host "Monitoring services (Ctrl+C to exit)..." -ForegroundColor Yellow
    while ($true) {
        Show-Status
        Start-Sleep -Seconds 5
    }
}
else {
    Show-Status
}

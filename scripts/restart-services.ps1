#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Restart LLMCrawl services with optional rebuild

.DESCRIPTION
    Restarts LLMCrawl services with full control over rebuild behavior.
    - Default: Recreate containers to reload env changes
    - With -Build: Rebuild images to pick up code changes
    - With -Full: Full rebuild (no cache) for major changes

.PARAMETER Service
    Optional. Restart only specific service(s). Can be comma-separated.
    Valid services: gateway, crawler, indexer, mcp-server, azure-devops-mcp-server

.PARAMETER Build
    Rebuild images before starting (picks up code changes)

.PARAMETER Full
    Full rebuild with no cache (use after dependency changes)

.PARAMETER Logs
    Follow logs after restart

.EXAMPLE
    .\scripts\restart-services.ps1
    # Recreate containers (picks up .env changes)

.EXAMPLE
    .\scripts\restart-services.ps1 -Build
    # Rebuild all services and restart (picks up code changes)

.EXAMPLE
    .\scripts\restart-services.ps1 -Service gateway -Build
    # Rebuild and restart only gateway

.EXAMPLE
    .\scripts\restart-services.ps1 -Service gateway,crawler -Build -Logs
    # Rebuild gateway and crawler, then follow logs

.EXAMPLE
    .\scripts\restart-services.ps1 -Full
    # Full rebuild with no cache (after requirements.txt changes)
#>

param(
    [string]$Service,
    [switch]$Build,
    [switch]$Full,
    [switch]$Logs
)

$ErrorActionPreference = "Stop"

# Ensure we are in the deploy directory
$DeployPath = Join-Path $PSScriptRoot "../deploy"
if (-not (Test-Path $DeployPath)) {
    Write-Error "Deploy directory not found at $DeployPath"
    exit 1
}
Push-Location $DeployPath

try {
    # Parse services
    $Services = @()
    if ($Service) {
        $Services = $Service -split ',' | ForEach-Object { $_.Trim() }
    }

    $ServiceDisplay = if ($Services.Count -gt 0) { $Services -join ", " } else { "all services" }

    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host " LLMCrawl Service Manager" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    # Determine operation mode
    if ($Full) {
        Write-Host "`nMode: FULL REBUILD (no cache)" -ForegroundColor Yellow
        Write-Host "Target: $ServiceDisplay" -ForegroundColor White
    }
    elseif ($Build) {
        Write-Host "`nMode: REBUILD + RESTART" -ForegroundColor Yellow
        Write-Host "Target: $ServiceDisplay" -ForegroundColor White
    }
    else {
        Write-Host "`nMode: RECREATE (env reload only)" -ForegroundColor Yellow
        Write-Host "Target: $ServiceDisplay" -ForegroundColor White
        Write-Host "Tip: Use -Build to pick up code changes" -ForegroundColor Gray
    }

    # For -Full, we need to run build separately with --no-cache
    # because --no-cache is a build flag, not an up flag
    if ($Full) {
        $BuildArgs = @("build", "--no-cache")
        if ($Services.Count -gt 0) {
            $BuildArgs += $Services
        }

        Write-Host "`nExecuting: docker compose -f docker-compose.dev.yml $($BuildArgs -join ' ')" -ForegroundColor Gray
        Write-Host ""

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
    }
    else {
        $Args += "--force-recreate"
    }

    # Add specific services if specified
    if ($Services.Count -gt 0) {
        $Args += $Services
    }

    Write-Host "`nExecuting: docker compose -f docker-compose.dev.yml $($Args -join ' ')" -ForegroundColor Gray
    Write-Host ""

    # Execute
    & docker compose -f docker-compose.dev.yml @Args

    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nFailed to restart services" -ForegroundColor Red
        exit 1
    }

    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host " Services restarted successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green

    # Show service status
    Write-Host "`nService Status:" -ForegroundColor Cyan
    docker compose -f docker-compose.dev.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

    Write-Host "`nService URLs:" -ForegroundColor Cyan
    Write-Host "  Gateway:           http://localhost:8000" -ForegroundColor White
    Write-Host "  Crawler:           http://localhost:8001" -ForegroundColor White
    Write-Host "  Indexer:           http://localhost:8002" -ForegroundColor White
    Write-Host "  MCP Server:        http://localhost:8003" -ForegroundColor White
    Write-Host "  Azure DevOps MCP:  http://localhost:8004" -ForegroundColor White

    Write-Host "`nHealth Check:" -ForegroundColor Cyan
    Write-Host "  curl http://localhost:8000/health" -ForegroundColor Gray

    # Follow logs if requested
    if ($Logs) {
        Write-Host "`nFollowing logs (Ctrl+C to exit)..." -ForegroundColor Yellow
        if ($Services.Count -gt 0) {
            docker compose -f docker-compose.dev.yml logs -f @Services
        }
        else {
            docker compose -f docker-compose.dev.yml logs -f gateway crawler indexer mcp-server
        }
    }
}
finally {
    Pop-Location
}

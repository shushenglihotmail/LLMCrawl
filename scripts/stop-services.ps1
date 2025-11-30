#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Stop LLMCrawl services

.DESCRIPTION
    Stops LLMCrawl services using docker compose.
    By default preserves containers. Use -Remove to delete containers.

.PARAMETER Remove
    Remove containers after stopping (keeps volumes)

.PARAMETER Volumes
    Also remove volumes (WARNING: deletes all data!)

.PARAMETER Service
    Stop only specific service(s). Can be comma-separated.

.EXAMPLE
    .\scripts\stop-services.ps1
    # Stop all services (containers preserved)

.EXAMPLE
    .\scripts\stop-services.ps1 -Remove
    # Stop and remove containers (keeps data volumes)

.EXAMPLE
    .\scripts\stop-services.ps1 -Service gateway,crawler
    # Stop only gateway and crawler

.EXAMPLE
    .\scripts\stop-services.ps1 -Remove -Volumes
    # Full cleanup including data (WARNING!)
#>

param(
    [switch]$Remove,
    [switch]$Volumes,
    [string]$Service
)

$ErrorActionPreference = "Stop"

Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host " Stopping LLMCrawl Services" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

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

    if ($Remove) {
        $Args = @("down")
        if ($Volumes) {
            $Args += "-v"
            Write-Host "`nMode: STOP + REMOVE CONTAINERS + REMOVE VOLUMES" -ForegroundColor Red
        } else {
            Write-Host "`nMode: STOP + REMOVE CONTAINERS (volumes preserved)" -ForegroundColor Yellow
        }

        Write-Host "Executing: docker compose -f docker-compose.yml $($Args -join ' ')" -ForegroundColor Gray
        & docker compose -f docker-compose.yml @Args

        Write-Host "`nServices stopped and containers removed." -ForegroundColor Green
    } else {
        if ($Services.Count -gt 0) {
            Write-Host "`nMode: STOP (containers preserved)" -ForegroundColor Yellow
            Write-Host "Target: $($Services -join ', ')" -ForegroundColor White
            & docker compose -f docker-compose.yml stop @Services
        } else {
            Write-Host "`nMode: STOP ALL (containers preserved)" -ForegroundColor Yellow
            docker compose -f docker-compose.yml stop
        }

        Write-Host "`nServices stopped (containers preserved)." -ForegroundColor Green
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nFailed to stop services. Check docker status." -ForegroundColor Red
        exit 1
    }

    Write-Host "`nTo restart: .\scripts\restart-services.ps1 -Build" -ForegroundColor Gray
}
finally {
    Pop-Location
}

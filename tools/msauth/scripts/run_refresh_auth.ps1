# Run by scheduled task to refresh authentication
# This script checks and refreshes www.osgwiki.com authentication

$ErrorActionPreference = "Stop"
$WorkingDir = $PSScriptRoot + "\.."

Set-Location $WorkingDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "OSGWiki Auth Refresh - $(Get-Date)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Activate virtual environment if it exists
if (Test-Path ".\venv\Scripts\Activate.ps1") {
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & .\venv\Scripts\Activate.ps1
}

# Check current auth status
Write-Host "`nChecking current authentication status..." -ForegroundColor Yellow
python tools/refresh_auth.py --name www_osgwiki_com --check-only

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Authentication is valid, no refresh needed" -ForegroundColor Green
    exit 0
}

# Auth expired, refresh it
Write-Host "`n⚠️ Authentication expired, attempting refresh..." -ForegroundColor Yellow

# Note: This requires the browser to be accessible
# For truly automated refresh, you'd need to use a service principal or device code flow
python tools/refresh_auth.py --name www_osgwiki_com --force --apply-env

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Authentication refreshed successfully" -ForegroundColor Green

    # Restart crawler if it's running
    Write-Host "`nRestarting crawler service..." -ForegroundColor Yellow
    docker-compose restart crawler

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Crawler restarted" -ForegroundColor Green
    } else {
        Write-Host "⚠️ Failed to restart crawler (may not be running)" -ForegroundColor Yellow
    }

    exit 0
} else {
    Write-Host "`n❌ Failed to refresh authentication" -ForegroundColor Red
    exit 1
}

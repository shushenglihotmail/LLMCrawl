# Quick Auth Status Check
# Usage: .\scripts\check-auth-status.ps1 [site-url]

param(
    [Parameter(Mandatory = $false)]
    [string]$SiteUrl = "https://www.osgwiki.com/wiki/Main_Page"
)

Write-Host "`n=== Authentication Status Check ===" -ForegroundColor Cyan
Write-Host "Target: $SiteUrl`n" -ForegroundColor Yellow

# Check if auth profile exists
# Extract domain from URL for filename
$domain = ([System.Uri]$SiteUrl).Host -replace '\.', '_'
$authFile = Join-Path $PSScriptRoot "..\.auth\$domain.json"

if (-not (Test-Path $authFile)) {
    Write-Host "✗ No auth profile found" -ForegroundColor Red
    Write-Host "  Expected: $authFile" -ForegroundColor Gray
    Write-Host "  Looking in: $(Join-Path $PSScriptRoot '..\.auth')" -ForegroundColor Gray

    # List available auth files
    $authDir = Join-Path $PSScriptRoot "..\.auth"
    if (Test-Path $authDir) {
        $authFiles = Get-ChildItem $authDir -Filter "*.json"
        if ($authFiles) {
            Write-Host "`n  Available auth profiles:" -ForegroundColor Gray
            $authFiles | ForEach-Object { Write-Host "    - $($_.Name)" -ForegroundColor Gray }
        }
    }

    Write-Host "`nRun: python tools/msauth/authenticate.py $SiteUrl" -ForegroundColor Yellow
    exit 1
}

# Check auth file age
$authAge = (Get-Date) - (Get-Item $authFile).LastWriteTime
$hoursOld = [math]::Round($authAge.TotalHours, 1)

Write-Host "Auth Profile Status:" -ForegroundColor Cyan
Write-Host "  File: $authFile" -ForegroundColor Gray
Write-Host "  Age: $hoursOld hours old" -ForegroundColor $(if ($hoursOld -gt 20) { "Yellow" } else { "Green" })

if ($hoursOld -gt 24) {
    Write-Host "  ⚠ Auth likely expired (>24 hours)" -ForegroundColor Red
}
elseif ($hoursOld -gt 20) {
    Write-Host "  ⚠ Auth expiring soon" -ForegroundColor Yellow
}
else {
    Write-Host "  ✓ Auth age looks good" -ForegroundColor Green
}

# Test actual crawl
Write-Host "`nTesting Crawl..." -ForegroundColor Cyan

try {
    $body = @{
        query       = "Test auth"
        seed_urls   = @($SiteUrl)
        max_results = 1
    } | ConvertTo-Json

    $result = Invoke-RestMethod -Uri "http://localhost:8001/crawl" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 30 `
        -ErrorAction Stop

    # API returns "docs" not "documents"
    $docs = $result.docs
    if ($docs -and $docs.Count -gt 0 -and -not $docs[0].error) {
        Write-Host "  ✓ Auth working - content retrieved" -ForegroundColor Green
        Write-Host "  Title: $($docs[0].title)" -ForegroundColor Gray
        Write-Host "  Content length: $($docs[0].markdown.Length) chars" -ForegroundColor Gray
        Write-Host "  Source: $($docs[0].source)" -ForegroundColor Gray
        exit 0
    }
    else {
        Write-Host "  ✗ Auth failed - no content retrieved" -ForegroundColor Red
        if ($docs -and $docs[0].error) {
            Write-Host "  Error: $($docs[0].error)" -ForegroundColor Gray
        }
    }
}
catch {
    Write-Host "  ✗ Crawl request failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Show 401 errors from logs
Write-Host "`nRecent Auth Errors:" -ForegroundColor Cyan
$DeployPath = Join-Path $PSScriptRoot "../deploy"
if (Test-Path $DeployPath) {
    Push-Location $DeployPath
    try {
        $logs = docker-compose -f docker-compose.yml logs --tail=100 crawler 2>$null |
        Select-String -Pattern "401|Unauthorized" |
        Select-Object -Last 3
    }
    finally {
        Pop-Location
    }
}

if ($logs) {
    $logs | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
}
else {
    Write-Host "  (No 401 errors in recent logs)" -ForegroundColor Gray
}

Write-Host "`n=== AUTHENTICATION REFRESH NEEDED ===" -ForegroundColor Red
Write-Host "`nQuick Fix - Run this command:" -ForegroundColor Yellow
Write-Host ""
Write-Host "# Authenticate (browser opens, sign in, press ENTER when done)" -ForegroundColor Cyan
Write-Host "python tools/msauth/authenticate.py $SiteUrl" -ForegroundColor White
Write-Host ""
Write-Host "# The script will automatically:" -ForegroundColor Gray
Write-Host "#   - Extract cookies after you sign in" -ForegroundColor Gray
Write-Host "#   - Update .env with new credentials" -ForegroundColor Gray
Write-Host "#   - Restart crawler container" -ForegroundColor Gray
Write-Host "#   - Test authentication" -ForegroundColor Gray
Write-Host ""

exit 1

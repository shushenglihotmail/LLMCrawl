# Helper script to manually add AppServiceAuthSession cookie to auth file
# Use this when automated capture doesn't work (e.g., Azure App Service Easy Auth)

param(
    [Parameter(Mandatory=$true)]
    [string]$ProfileName,
    
    [Parameter(Mandatory=$true)]
    [string]$CookieValue,
    
    [string]$Domain = "www.osgwiki.com"
)

$ErrorActionPreference = "Stop"

# Paths
$authDir = Join-Path $PSScriptRoot "..\..\.auth"
$authFile = Join-Path $authDir "$ProfileName.json"

# Check if auth file exists
if (-not (Test-Path $authFile)) {
    Write-Host "❌ Auth file not found: $authFile" -ForegroundColor Red
    Write-Host "Run the auth capture tool first:" -ForegroundColor Yellow
    Write-Host "  python tools\msauth\interactive_auth.py https://$Domain/wiki/Main_Page --name $ProfileName" -ForegroundColor Cyan
    exit 1
}

Write-Host "📝 Adding AppServiceAuthSession cookie to profile: $ProfileName" -ForegroundColor Green

# Load the auth file
$auth = Get-Content $authFile | ConvertFrom-Json

# Check if cookie already exists
$existingCookie = $auth.cookies | Where-Object { $_.name -eq "AppServiceAuthSession" -and $_.domain -eq $Domain }

if ($existingCookie) {
    Write-Host "⚠️  AppServiceAuthSession cookie already exists. Updating..." -ForegroundColor Yellow
    # Remove existing cookie
    $auth.cookies = @($auth.cookies | Where-Object { -not ($_.name -eq "AppServiceAuthSession" -and $_.domain -eq $Domain) })
}

# Create the new cookie object
$newCookie = @{
    name = "AppServiceAuthSession"
    value = $CookieValue
    domain = $Domain
    path = "/"
    expires = [DateTimeOffset]::UtcNow.AddDays(1).ToUnixTimeSeconds()
    httpOnly = $true
    secure = $true
    sameSite = "Lax"
}

# Add the cookie
$auth.cookies += $newCookie

# Save back to file
$auth | ConvertTo-Json -Depth 10 | Set-Content $authFile

Write-Host "✅ Cookie added successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "📊 Summary:" -ForegroundColor Cyan
Write-Host "  Profile: $ProfileName"
Write-Host "  Domain: $Domain"
Write-Host "  Total cookies: $($auth.cookies.Count)"
Write-Host ""
Write-Host "📋 Next steps:" -ForegroundColor Cyan
Write-Host "  1. Apply to .env:" -ForegroundColor White
Write-Host "     python tools\msauth\interactive_auth.py --apply $ProfileName" -ForegroundColor Yellow
Write-Host "  2. Restart crawler:" -ForegroundColor White
Write-Host "     docker-compose restart crawler" -ForegroundColor Yellow
Write-Host "  3. Test:" -ForegroundColor White
Write-Host "     curl -X POST http://localhost:8001/crawl -H 'Content-Type: application/json' -d '{`"query`":`"test`",`"seed_urls`":[`"https://$Domain/wiki/Main_Page`"],`"depth`":1}'" -ForegroundColor Yellow

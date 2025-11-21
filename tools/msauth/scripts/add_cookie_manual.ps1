# Helper script to manually add AppServiceAuthSession cookie to auth file
# Use this when automated capture doesn't work (e.g., Azure App Service Easy Auth)
#
# Usage:
#   .\tools\msauth\scripts\add_cookie_manual.ps1                    # Interactive mode
#   .\tools\msauth\scripts\add_cookie_manual.ps1 www_osgwiki_com <cookie_value>  # Direct mode

param(
    [Parameter(Mandatory=$false)]
    [string]$ProfileName,

    [Parameter(Mandatory=$false)]
    [string]$CookieValue
)

$ErrorActionPreference = "Stop"

# Paths
$authDir = Join-Path $PSScriptRoot "..\..\..\.auth"

# Interactive mode if no parameters provided
if (-not $ProfileName) {
    Write-Host "`n=== Manual Cookie Addition ===" -ForegroundColor Cyan
    Write-Host "This script adds AppServiceAuthSession cookie to an existing auth profile`n" -ForegroundColor Gray

    # List available profiles
    if (-not (Test-Path $authDir)) {
        Write-Host "❌ No auth directory found: $authDir" -ForegroundColor Red
        Write-Host "Run the auth capture tool first:" -ForegroundColor Yellow
        Write-Host "  .\venv\Scripts\python.exe tools\msauth\interactive_auth.py https://www.osgwiki.com/wiki/Main_Page" -ForegroundColor White
        exit 1
    }

    $authFiles = Get-ChildItem $authDir -Filter "*.json"
    if ($authFiles.Count -eq 0) {
        Write-Host "❌ No auth profiles found in $authDir" -ForegroundColor Red
        Write-Host "Run the auth capture tool first:" -ForegroundColor Yellow
        Write-Host "  .\venv\Scripts\python.exe tools\msauth\interactive_auth.py https://www.osgwiki.com/wiki/Main_Page" -ForegroundColor White
        exit 1
    }

    Write-Host "Available profiles:" -ForegroundColor Cyan
    for ($i = 0; $i -lt $authFiles.Count; $i++) {
        $profile = $authFiles[$i].BaseName
        $authData = Get-Content $authFiles[$i].FullName | ConvertFrom-Json
        $url = $authData.url
        $cookieCount = $authData.cookies.Count
        Write-Host "  [$($i+1)] $profile" -ForegroundColor White
        Write-Host "      URL: $url" -ForegroundColor Gray
        Write-Host "      Cookies: $cookieCount" -ForegroundColor Gray
    }

    Write-Host ""
    $selection = Read-Host "Select profile number (or press Enter for 1)"
    if ([string]::IsNullOrWhiteSpace($selection)) {
        $selection = "1"
    }

    $index = [int]$selection - 1
    if ($index -lt 0 -or $index -ge $authFiles.Count) {
        Write-Host "❌ Invalid selection" -ForegroundColor Red
        exit 1
    }

    $ProfileName = $authFiles[$index].BaseName
    $authData = Get-Content $authFiles[$index].FullName | ConvertFrom-Json
    $targetUrl = $authData.url
    $Domain = ([System.Uri]$targetUrl).Host

    Write-Host "`n✓ Selected profile: $ProfileName" -ForegroundColor Green
    Write-Host "  Target site: $targetUrl" -ForegroundColor Gray
    Write-Host ""
}

$authFile = Join-Path $authDir "$ProfileName.json"

# Check if auth file exists
if (-not (Test-Path $authFile)) {
    Write-Host "❌ Auth file not found: $authFile" -ForegroundColor Red
    Write-Host "Available profiles:" -ForegroundColor Yellow
    Get-ChildItem $authDir -Filter "*.json" | ForEach-Object { Write-Host "  - $($_.BaseName)" -ForegroundColor Gray }
    exit 1
}

# Load the auth file to get domain if not provided
if (-not $Domain) {
    $authData = Get-Content $authFile | ConvertFrom-Json
    $Domain = ([System.Uri]$authData.url).Host
}

# Interactive cookie value input if not provided
if (-not $CookieValue) {
    Write-Host "=== Get Cookie from Browser ===" -ForegroundColor Cyan
    Write-Host "IMPORTANT: Do these steps QUICKLY (cookie expires fast!)" -ForegroundColor Red
    Write-Host ""
    Write-Host "1. Open your browser and navigate to: $($authData.url)" -ForegroundColor White
    Write-Host "2. Make sure you can see the page content (not login page)" -ForegroundColor White
    Write-Host "3. Press F12 to open DevTools → Application tab → Cookies → $Domain" -ForegroundColor White
    Write-Host "4. Find 'AppServiceAuthSession' cookie" -ForegroundColor White
    Write-Host "5. Double-click the Value column and copy (Ctrl+C)" -ForegroundColor White
    Write-Host "6. Come back HERE and paste immediately!" -ForegroundColor Yellow
    Write-Host ""
    $CookieValue = Read-Host "Paste the AppServiceAuthSession cookie value here"

    if ([string]::IsNullOrWhiteSpace($CookieValue)) {
        Write-Host "❌ No cookie value provided" -ForegroundColor Red
        exit 1
    }

    # Strip the prefix if user copied "AppServiceAuthSession=<value>"
    $CookieValue = $CookieValue -replace '^AppServiceAuthSession=', ''

    Write-Host ""
    Write-Host "✓ Cookie received (length: $($CookieValue.Length) chars)" -ForegroundColor Green
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

# Add the cookie to both places (cookies array and storage_state.cookies)
$auth.cookies += $newCookie

# Also add to storage_state.cookies if it exists (for Playwright)
if ($auth.storage_state -and $auth.storage_state.cookies) {
    # Remove existing AppServiceAuthSession from storage_state if present
    $auth.storage_state.cookies = @($auth.storage_state.cookies | Where-Object {
        -not ($_.name -eq "AppServiceAuthSession" -and $_.domain -eq $Domain)
    })

    # Create storage_state cookie format
    $appServiceCookie = @{
        name = "AppServiceAuthSession"
        value = $CookieValue
        domain = $Domain
        path = "/"
        expires = [DateTimeOffset]::UtcNow.AddDays(1).ToUnixTimeSeconds()
        httpOnly = $true
        secure = $true
        sameSite = "Lax"
    }

    $auth.storage_state.cookies += $appServiceCookie
    Write-Host "✓ Added to storage_state.cookies (for Playwright)" -ForegroundColor Gray
}

# Save back to file
$auth | ConvertTo-Json -Depth 10 | Set-Content $authFile

Write-Host "✅ Cookie added to .auth file successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "📊 Cookie Summary:" -ForegroundColor Cyan
Write-Host "  Profile: $ProfileName" -ForegroundColor White
Write-Host "  Domain: $Domain" -ForegroundColor White
Write-Host "  Cookie length: $($CookieValue.Length) chars" -ForegroundColor White
Write-Host "  Total cookies in profile: $($auth.cookies.Count)" -ForegroundColor White
Write-Host ""

# Automatically apply to .env
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host "📝 Step 1/3: Applying cookie to .env file..." -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
try {
    $pythonPath = Join-Path $PSScriptRoot "..\..\..\venv\Scripts\python.exe"
    $authScript = Join-Path $PSScriptRoot "..\..\interactive_auth.py"

    & $pythonPath $authScript --apply $ProfileName 2>&1 | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Cookie successfully applied to .env" -ForegroundColor Green
        $envApplied = $true
    } else {
        Write-Host "✗ Failed to apply automatically" -ForegroundColor Red
        Write-Host "  Run manually: .\venv\Scripts\python.exe tools\msauth\interactive_auth.py --apply $ProfileName" -ForegroundColor Yellow
        $envApplied = $false
    }
} catch {
    Write-Host "✗ Failed to apply automatically" -ForegroundColor Red
    Write-Host "  Run manually: .\venv\Scripts\python.exe tools\msauth\interactive_auth.py --apply $ProfileName" -ForegroundColor Yellow
    $envApplied = $false
}

if ($envApplied) {
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
    Write-Host "🔄 Step 2/3: Recreating crawler service..." -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
    Write-Host "Recreating crawler to reload .env file with new cookies..." -ForegroundColor Gray
    Write-Host ""

    try {
        $output = docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Crawler recreated successfully" -ForegroundColor Green
            Write-Host ""
            Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
            Write-Host "🧪 Step 3/3: Testing authentication..." -ForegroundColor Cyan
            Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
            Write-Host "Press Enter to test now (or Ctrl+C to skip)" -ForegroundColor Yellow
            Read-Host

            & ".\scripts\check-auth-status.ps1" "https://$Domain"
        } else {
            Write-Host "✗ Failed to recreate crawler" -ForegroundColor Red
            Write-Host "  Run manually: docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "✗ Failed to recreate crawler" -ForegroundColor Red
        Write-Host "  Run manually: docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "📋 Manual Steps Required:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "# Step 1: Apply cookie to .env" -ForegroundColor Cyan
    Write-Host ".\venv\Scripts\python.exe tools\msauth\interactive_auth.py --apply $ProfileName" -ForegroundColor White
    Write-Host ""
    Write-Host "# Step 2: Recreate crawler (loads new .env)" -ForegroundColor Cyan
    Write-Host "docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler" -ForegroundColor White
    Write-Host ""
    Write-Host "# Step 3: Test authentication" -ForegroundColor Cyan
    Write-Host ".\scripts\check-auth-status.ps1 https://$Domain" -ForegroundColor White
    Write-Host ""
}

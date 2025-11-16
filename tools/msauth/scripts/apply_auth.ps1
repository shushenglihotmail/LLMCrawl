# Update .env with authentication from .auth file
param(
    [string]$AuthName = "www_osgwiki_com"
)

$authFile = ".auth/$AuthName.json"
if (-not (Test-Path $authFile)) {
    Write-Error "Auth file not found: $authFile"
    exit 1
}

Write-Host "Loading auth from: $authFile" -ForegroundColor Cyan

# Load auth data
$authData = Get-Content $authFile | ConvertFrom-Json
$storageState = $authData.storage_state | ConvertTo-Json -Compress -Depth 10

Write-Host "Storage state has $($authData.storage_state.cookies.Count) cookies" -ForegroundColor Green

# Read .env
$envContent = Get-Content .env

# Find and update FIRECRAWL_AUTH_STORAGE_STATE
$updated = $false
for ($i = 0; $i -lt $envContent.Count; $i++) {
    if ($envContent[$i] -match "^FIRECRAWL_AUTH_STORAGE_STATE=") {
        $envContent[$i] = "FIRECRAWL_AUTH_STORAGE_STATE=$storageState"
        $updated = $true
        Write-Host "Updated existing FIRECRAWL_AUTH_STORAGE_STATE" -ForegroundColor Green
        break
    }
}

# Add if not found
if (-not $updated) {
    $envContent += "FIRECRAWL_AUTH_STORAGE_STATE=$storageState"
    Write-Host "Added FIRECRAWL_AUTH_STORAGE_STATE to .env" -ForegroundColor Green
}

# Save .env
$envContent | Set-Content .env

Write-Host "`n✅ Authentication configured!" -ForegroundColor Green
Write-Host "The crawler will now use the AppServiceAuthSession cookie." -ForegroundColor Cyan

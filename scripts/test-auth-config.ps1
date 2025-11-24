# Test Authentication Configuration
# This script tests different authentication methods for internal sites

Write-Host "=== Testing FireCrawl Authentication Configuration ===" -ForegroundColor Cyan
Write-Host ""

# Test 1: Check if services are running
Write-Host "1. Checking service health..." -ForegroundColor Yellow
try {
    $gateway = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 5
    Write-Host "   ✓ Gateway: $($gateway.status)" -ForegroundColor Green
} catch {
    Write-Host "   ✗ Gateway not responding" -ForegroundColor Red
    exit 1
}

try {
    $crawler = Invoke-RestMethod -Uri "http://localhost:8001/health" -Method Get -TimeoutSec 5
    Write-Host "   ✓ Crawler: $($crawler.status)" -ForegroundColor Green
} catch {
    Write-Host "   ✗ Crawler not responding" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Test 2: Check current authentication configuration
Write-Host "2. Checking authentication configuration..." -ForegroundColor Yellow
$envFile = Get-Content "deploy/.env" | Where-Object { $_ -match "FIRECRAWL_AUTH" }
if ($envFile) {
    Write-Host "   Current authentication settings:" -ForegroundColor Cyan
    foreach ($line in $envFile) {
        if ($line -notmatch "^#" -and $line.Trim()) {
            # Mask sensitive values
            if ($line -match "PASSWORD|TOKEN|KEY") {
                $parts = $line -split "=", 2
                if ($parts[1] -and $parts[1].Trim()) {
                    Write-Host "   $($parts[0])=***masked***" -ForegroundColor Gray
                } else {
                    Write-Host "   $line" -ForegroundColor Gray
                }
            } else {
                Write-Host "   $line" -ForegroundColor Gray
            }
        }
    }
} else {
    Write-Host "   No authentication configured (using default)" -ForegroundColor Gray
}

Write-Host ""

# Test 3: Test authentication methods
Write-Host "3. Testing authentication method examples..." -ForegroundColor Yellow
Write-Host ""

# Example 1: Headers Authentication
Write-Host "   Example 1: Headers Authentication" -ForegroundColor Cyan
Write-Host "   -------------------------------" -ForegroundColor Cyan
Write-Host '   FIRECRAWL_AUTH_TYPE=headers' -ForegroundColor White
Write-Host '   FIRECRAWL_AUTH_HEADERS={"X-API-Key": "your-key-here"}' -ForegroundColor White
Write-Host "   Use for: API keys, custom authentication tokens" -ForegroundColor Gray
Write-Host ""

# Example 2: Cookies Authentication
Write-Host "   Example 2: Cookies Authentication" -ForegroundColor Cyan
Write-Host "   -------------------------------" -ForegroundColor Cyan
Write-Host '   FIRECRAWL_AUTH_TYPE=cookies' -ForegroundColor White
Write-Host '   FIRECRAWL_AUTH_STORAGE_STATE={"cookies": [...], "origins": [...]}' -ForegroundColor White
Write-Host "   Use for: Session-based auth, web applications, SSO" -ForegroundColor Gray
Write-Host ""

# Example 3: Basic Authentication
Write-Host "   Example 3: Basic Authentication" -ForegroundColor Cyan
Write-Host "   -------------------------------" -ForegroundColor Cyan
Write-Host '   FIRECRAWL_AUTH_TYPE=basic' -ForegroundColor White
Write-Host '   FIRECRAWL_AUTH_USERNAME=admin' -ForegroundColor White
Write-Host '   FIRECRAWL_AUTH_PASSWORD=password' -ForegroundColor White
Write-Host "   Use for: Username/password protected sites" -ForegroundColor Gray
Write-Host ""

# Example 4: Bearer Token
Write-Host "   Example 4: Bearer Token" -ForegroundColor Cyan
Write-Host "   -------------------------------" -ForegroundColor Cyan
Write-Host '   FIRECRAWL_AUTH_TYPE=bearer' -ForegroundColor White
Write-Host '   FIRECRAWL_AUTH_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...' -ForegroundColor White
Write-Host "   Use for: JWT tokens, OAuth2" -ForegroundColor Gray
Write-Host ""

# Test 4: Provide next steps
Write-Host "4. Next Steps:" -ForegroundColor Yellow
Write-Host "   1. Choose authentication method for your internal site" -ForegroundColor White
Write-Host "   2. Update .env file with credentials" -ForegroundColor White
Write-Host "   3. Add internal domain to ALLOWED_DOMAINS" -ForegroundColor White
Write-Host "   4. Restart crawler: docker-compose restart crawler" -ForegroundColor White
Write-Host "   5. Test with: .\scripts\test-internal-auth.ps1 <your-internal-url>" -ForegroundColor White
Write-Host ""

Write-Host "📚 Full Documentation:" -ForegroundColor Cyan
Write-Host "   Quick Start: docs\AUTHENTICATION_QUICKSTART.md" -ForegroundColor White
Write-Host "   Full Guide:  docs\AUTHENTICATION.md" -ForegroundColor White
Write-Host ""

Write-Host "=== Test Complete ===" -ForegroundColor Green

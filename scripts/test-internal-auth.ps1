# Test Internal Site Authentication
# Usage: .\scripts\test-internal-auth.ps1 https://internal-site.com/page

param(
    [Parameter(Mandatory=$true)]
    [string]$Url,

    [Parameter(Mandatory=$false)]
    [string]$Query = ""
)

Write-Host "=== Testing Internal Site Authentication ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Target URL: $Url" -ForegroundColor Yellow
Write-Host ""

# Step 1: Check if crawler is healthy
Write-Host "1. Checking crawler health..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8001/health" -Method Get -TimeoutSec 5
    $crawlerStatus = $health.components | Where-Object { $_.name -eq "crawler" }

    if ($crawlerStatus.status -eq "healthy") {
        Write-Host "   ✓ Crawler is healthy" -ForegroundColor Green
        Write-Host "   Auth type: $($crawlerStatus.details.auth_type)" -ForegroundColor Gray
    } else {
        Write-Host "   ⚠ Crawler status: $($crawlerStatus.status)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ✗ Cannot connect to crawler" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 2: Test crawling the URL
Write-Host "2. Testing crawl request..." -ForegroundColor Yellow

$body = @{
    query = if ($Query) { $Query } else { "Retrieve content from $Url" }
    seed_urls = @($Url)
    max_results = 5
} | ConvertTo-Json

Write-Host "   Request body: $body" -ForegroundColor Gray
Write-Host ""

try {
    $result = Invoke-RestMethod -Uri "http://localhost:8001/crawl" `
                                -Method Post `
                                -ContentType "application/json" `
                                -Body $body `
                                -TimeoutSec 60

    Write-Host "   ✓ Crawl completed" -ForegroundColor Green
    Write-Host "   Documents returned: $($result.documents.Count)" -ForegroundColor Cyan
    Write-Host ""

    if ($result.documents.Count -gt 0) {
        $doc = $result.documents[0]
        Write-Host "   Document Details:" -ForegroundColor Cyan
        Write-Host "   ----------------" -ForegroundColor Cyan
        Write-Host "   URL: $($doc.url)" -ForegroundColor White
        Write-Host "   Title: $($doc.title)" -ForegroundColor White

        if ($doc.error) {
            Write-Host "   ✗ Error: $($doc.error)" -ForegroundColor Red
            Write-Host ""
            Write-Host "   Common Issues:" -ForegroundColor Yellow
            Write-Host "   - 401 Unauthorized: Check credentials/token" -ForegroundColor Gray
            Write-Host "   - 403 Forbidden: Check permissions/IP whitelist" -ForegroundColor Gray
            Write-Host "   - Timeout: Site may be slow or unreachable" -ForegroundColor Gray
        } else {
            $contentLength = $doc.markdown.Length
            $preview = $doc.markdown.Substring(0, [Math]::Min(200, $contentLength))
            Write-Host "   Content Length: $contentLength characters" -ForegroundColor White
            Write-Host "   Preview: $preview..." -ForegroundColor Gray
            Write-Host ""

            if ($contentLength -lt 100) {
                Write-Host "   ⚠ Warning: Content seems very short" -ForegroundColor Yellow
                Write-Host "   This may indicate authentication failed or content is protected" -ForegroundColor Yellow
            } else {
                Write-Host "   ✓ Content successfully extracted" -ForegroundColor Green
            }
        }
    } else {
        Write-Host "   ⚠ No documents returned" -ForegroundColor Yellow
        Write-Host "   This may indicate crawling failed or URL is inaccessible" -ForegroundColor Yellow
    }

} catch {
    Write-Host "   ✗ Crawl failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "   Troubleshooting Steps:" -ForegroundColor Yellow
    Write-Host "   1. Check if URL is accessible from your network" -ForegroundColor Gray
    Write-Host "   2. Verify authentication credentials in .env" -ForegroundColor Gray
    Write-Host "   3. Check crawler logs: docker-compose logs crawler" -ForegroundColor Gray
    Write-Host "   4. Enable debug mode: LOG_LEVEL=DEBUG in .env" -ForegroundColor Gray
    exit 1
}

Write-Host ""

# Step 3: Test via gateway (if query provided)
if ($Query) {
    Write-Host "3. Testing via gateway with query..." -ForegroundColor Yellow

    $chatBody = @{
        message = $Query
        force_refresh = $true
        seed_urls = @($Url)
    } | ConvertTo-Json

    try {
        $chatResult = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/chat" `
                                        -Method Post `
                                        -ContentType "application/json" `
                                        -Body $chatBody `
                                        -TimeoutSec 45

        Write-Host "   ✓ Chat request completed" -ForegroundColor Green
        Write-Host "   Response length: $($chatResult.response.Length) characters" -ForegroundColor Cyan

        if ($chatResult.sources) {
            Write-Host "   Sources: $($chatResult.sources.Count)" -ForegroundColor Cyan
            foreach ($source in $chatResult.sources) {
                Write-Host "     - $($source.url)" -ForegroundColor Gray
            }
        }

        Write-Host ""
        Write-Host "   Response Preview:" -ForegroundColor Cyan
        Write-Host "   ----------------" -ForegroundColor Cyan
        $responsePreview = $chatResult.response.Substring(0, [Math]::Min(500, $chatResult.response.Length))
        Write-Host "   $responsePreview..." -ForegroundColor White

    } catch {
        Write-Host "   ✗ Chat request failed: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== Test Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "- If authentication failed, check credentials in .env" -ForegroundColor White
Write-Host "- View logs: docker-compose logs crawler | Select-String '$Url'" -ForegroundColor White
Write-Host "- See guide: docs\AUTHENTICATION_QUICKSTART.md" -ForegroundColor White

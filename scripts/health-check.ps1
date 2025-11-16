# Health Check Script for LLMCrawl Services
# Usage: .\scripts\health-check.ps1

Write-Host "`n=== LLMCrawl Service Health Check ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n" -ForegroundColor Gray

# Function to check service health
function Check-ServiceHealth {
    param(
        [string]$ServiceName,
        [string]$Url
    )

    Write-Host "=== $ServiceName Health ===" -ForegroundColor Yellow
    try {
        $response = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 5
        $status = $response.status

        if ($status -eq "healthy") {
            Write-Host "✓ Status: $status" -ForegroundColor Green
        } elseif ($status -eq "degraded") {
            Write-Host "⚠ Status: $status" -ForegroundColor Yellow
        } else {
            Write-Host "✗ Status: $status" -ForegroundColor Red
        }

        $response | ConvertTo-Json -Depth 5 | Write-Host -ForegroundColor Gray
    }
    catch {
        Write-Host "✗ Service unreachable: $($_.Exception.Message)" -ForegroundColor Red
    }
    Write-Host ""
}

# Check all services
Check-ServiceHealth -ServiceName "Gateway" -Url "http://localhost:8000/health"
Check-ServiceHealth -ServiceName "Crawler" -Url "http://localhost:8001/health"
Check-ServiceHealth -ServiceName "Indexer" -Url "http://localhost:8002/health"
Check-ServiceHealth -ServiceName "Qdrant" -Url "http://localhost:6333/health"

Write-Host "=== Health Check Complete ===" -ForegroundColor Cyan

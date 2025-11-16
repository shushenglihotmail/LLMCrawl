# Metrics Check Script for LLMCrawl Services
# Usage: .\scripts\check-metrics.ps1

Write-Host "`n=== LLMCrawl Service Metrics Check ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n" -ForegroundColor Gray

# Function to check service metrics
function Check-ServiceMetrics {
    param(
        [string]$ServiceName,
        [string]$Url
    )

    Write-Host "=== $ServiceName Metrics ===" -ForegroundColor Yellow
    try {
        $response = curl.exe -s $Url

        # Extract key metrics
        $requestTotal = $response | Select-String "http_requests_total" | Select-Object -First 3
        $memory = $response | Select-String "process_resident_memory_bytes" | Select-Object -First 1
        $uptime = $response | Select-String "process_start_time_seconds" | Select-Object -First 1

        if ($requestTotal) {
            Write-Host "Request Metrics:" -ForegroundColor Green
            $requestTotal | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
        }

        if ($memory) {
            Write-Host "Memory Usage:" -ForegroundColor Green
            Write-Host "  $memory" -ForegroundColor Gray
        }

        if ($uptime) {
            Write-Host "Process Start Time:" -ForegroundColor Green
            Write-Host "  $uptime" -ForegroundColor Gray
        }

        if (-not $requestTotal -and -not $memory) {
            Write-Host "✗ No metrics available" -ForegroundColor Red
        }
    }
    catch {
        Write-Host "✗ Metrics endpoint unreachable: $($_.Exception.Message)" -ForegroundColor Red
    }
    Write-Host ""
}

# Check all services
Check-ServiceMetrics -ServiceName "Gateway" -Url "http://localhost:8000/metrics"
Check-ServiceMetrics -ServiceName "Crawler" -Url "http://localhost:8001/metrics"
Check-ServiceMetrics -ServiceName "Indexer" -Url "http://localhost:8002/metrics"

Write-Host "=== Metrics Check Complete ===" -ForegroundColor Cyan
Write-Host "`nView full metrics at:" -ForegroundColor Yellow
Write-Host "  Prometheus: http://localhost:9090" -ForegroundColor Cyan
Write-Host "  Grafana:    http://localhost:3001" -ForegroundColor Cyan

# Test Chat with Indexing - LLMCrawl
# This script sends a query that triggers the full crawl→index→retrieve pipeline

Write-Host "`n=== LLMCrawl Indexing Test ===" -ForegroundColor Cyan
Write-Host "This will test the full pipeline: Crawl → Index → Retrieve`n" -ForegroundColor Gray

# Step 1: Check service health
Write-Host "Step 1: Checking service health..." -ForegroundColor Yellow
try {
    $indexerHealth = Invoke-RestMethod -Uri "http://localhost:8002/health" -Method Get
    if ($indexerHealth.status -eq "healthy") {
        Write-Host "✓ Indexer is healthy" -ForegroundColor Green
        Write-Host "  Embedding model: $($indexerHealth.embedding_model.model)" -ForegroundColor Gray
    } else {
        Write-Host "✗ Indexer is $($indexerHealth.status)" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "✗ Cannot reach indexer service" -ForegroundColor Red
    Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Step 2: Check Qdrant collection before
Write-Host "`nStep 2: Checking vector database before query..." -ForegroundColor Yellow
try {
    $qdrantBefore = Invoke-RestMethod -Uri "http://localhost:6333/collections/web_rag_docs" -Method Get
    $vectorsBefore = $qdrantBefore.result.points_count
    Write-Host "✓ Current vectors in database: $vectorsBefore" -ForegroundColor Green
} catch {
    Write-Host "⚠ Could not check Qdrant (may not be critical)" -ForegroundColor Yellow
    $vectorsBefore = 0
}

# Step 3: Send a test query that triggers indexing
Write-Host "`nStep 3: Sending test query..." -ForegroundColor Yellow
Write-Host "Query: 'What are the latest developments in artificial intelligence?'" -ForegroundColor Gray

$body = @{
    message = "What are the latest developments in artificial intelligence?"
    stream = $false
    force_refresh = $false  # Let automatic trigger detection work
} | ConvertTo-Json

Write-Host "`nSending request to gateway..." -ForegroundColor Gray
$startTime = Get-Date

try {
    $response = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/chat" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 60

    $duration = ((Get-Date) - $startTime).TotalSeconds
    Write-Host "✓ Response received in $([math]::Round($duration, 2)) seconds" -ForegroundColor Green
} catch {
    Write-Host "✗ Request failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Step 4: Analyze the response
Write-Host "`nStep 4: Analyzing response..." -ForegroundColor Yellow

# Check if tool was called (indexing was triggered)
if ($response.tool_calls -and $response.tool_calls.Count -gt 0) {
    Write-Host "✓ Crawl and Index was triggered!" -ForegroundColor Green
    Write-Host "`nTool Call Details:" -ForegroundColor Cyan
    $response.tool_calls | ForEach-Object {
        Write-Host "  Function: $($_.function.name)" -ForegroundColor Gray
        Write-Host "  Arguments: $($_.function.arguments)" -ForegroundColor Gray
    }
} else {
    Write-Host "⚠ No tool calls detected" -ForegroundColor Yellow
    Write-Host "  (Query may have used existing data)" -ForegroundColor Gray
}

# Check sources (retrieved from vector DB)
if ($response.sources -and $response.sources.Count -gt 0) {
    Write-Host "`n✓ Retrieved $($response.sources.Count) sources from vector database" -ForegroundColor Green
    Write-Host "`nSources:" -ForegroundColor Cyan
    $response.sources | ForEach-Object {
        Write-Host "  - $($_.url)" -ForegroundColor Gray
        if ($_.published_at) {
            Write-Host "    Published: $($_.published_at)" -ForegroundColor DarkGray
        }
    }
} else {
    Write-Host "`n⚠ No sources returned" -ForegroundColor Yellow
}

# Step 5: Check Qdrant collection after
Write-Host "`nStep 5: Checking vector database after query..." -ForegroundColor Yellow
try {
    $qdrantAfter = Invoke-RestMethod -Uri "http://localhost:6333/collections/web_rag_docs" -Method Get
    $vectorsAfter = $qdrantAfter.result.points_count
    $vectorsAdded = $vectorsAfter - $vectorsBefore

    Write-Host "✓ Vectors in database now: $vectorsAfter" -ForegroundColor Green
    if ($vectorsAdded -gt 0) {
        Write-Host "✓ Added $vectorsAdded new vectors during this query!" -ForegroundColor Green
    } else {
        Write-Host "  (No new vectors added - may have used existing data)" -ForegroundColor Gray
    }
} catch {
    Write-Host "⚠ Could not check Qdrant after query" -ForegroundColor Yellow
}

# Step 6: Display the response
Write-Host "`n=== Assistant Response ===" -ForegroundColor Cyan
Write-Host $response.response -ForegroundColor White

# Summary
Write-Host "`n=== Test Summary ===" -ForegroundColor Cyan
Write-Host "Conversation ID: $($response.conversation_id)" -ForegroundColor Gray
Write-Host "Response time: $([math]::Round($response.duration_ms, 2))ms" -ForegroundColor Gray
Write-Host "Tool calls: $($response.tool_calls.Count)" -ForegroundColor Gray
Write-Host "Sources retrieved: $($response.sources.Count)" -ForegroundColor Gray
Write-Host "`n✓ Indexing test complete!" -ForegroundColor Green

# Provide next steps
Write-Host "`n=== Next Steps ===" -ForegroundColor Yellow
Write-Host "1. Check indexer logs: docker-compose logs indexer | Select-String 'Indexed'" -ForegroundColor Gray
Write-Host "2. Open Qdrant Dashboard: http://localhost:6333/dashboard" -ForegroundColor Gray
Write-Host "3. View Prometheus metrics: http://localhost:9090" -ForegroundColor Gray
Write-Host "4. Try another query with 'latest', 'recent', 'news', etc." -ForegroundColor Gray

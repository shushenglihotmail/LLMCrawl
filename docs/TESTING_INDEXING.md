# Testing the Indexing Service - Quick Guide

This guide shows you how to trigger the indexing service through chat interactions.

## Quick Answer

To trigger the indexing service, ask questions that require **fresh, recent information**. The system automatically detects these queries and:
1. **Crawls** the web for relevant content
2. **Indexes** the content into the vector database (with embeddings)
3. **Retrieves** relevant chunks to answer your question

## Trigger Words

The system automatically triggers crawling and indexing when your message contains:

### Time-Sensitive Keywords
- `latest`, `recent`, `today`, `this week`, `this month`
- `current`, `now`, `just`, `new`, `fresh`, `live`, `breaking`

### Financial/Market Keywords
- `earnings`, `guidance`, `ticker`, `market`, `price`
- `s&p`, `sp500`, `dow`, `nasdaq`, `index`, `stock`
- `close`, `closing`

### Company/News Keywords
- `launched`, `announced`, `filed`, `SEC`
- `10-K`, `10-Q`, `news`, `update`

## Example Queries to Test Indexing

### 1. Using curl (Direct API)

```bash
# Test with a query that triggers indexing
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are the latest NVIDIA earnings?",
    "stream": false
  }'
```

**What happens:**
1. Gateway detects "latest" and "earnings" keywords
2. Calls crawler service to fetch NVIDIA earnings pages
3. Crawler returns cleaned content
4. Gateway calls indexer service to embed and store content
5. Indexer creates vector embeddings using Azure OpenAI (text-embedding-3-large)
6. Content is stored in Qdrant vector database
7. Gateway retrieves relevant chunks and generates response with citations

### 2. Using the Web UI

Start the demo client:
```bash
docker-compose --profile demo up -d
```

Open http://localhost:3000 and try these queries:

**Examples:**
- "What's the latest news on Tesla?"
- "Recent Microsoft earnings report"
- "Latest AI developments this week"
- "What happened with Apple today?"
- "Current S&P 500 performance"

### 3. Using PowerShell Script

Create a test script:

```powershell
# test-chat.ps1
$body = @{
    message = "What are the latest developments in artificial intelligence?"
    stream = $false
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:8000/agent/chat" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body

Write-Host "`nResponse:" -ForegroundColor Cyan
$response.response

Write-Host "`n`nSources:" -ForegroundColor Yellow
$response.sources | ForEach-Object {
    Write-Host "- $($_.url)" -ForegroundColor Gray
}

Write-Host "`n`nTool Calls:" -ForegroundColor Green
$response.tool_calls | ConvertTo-Json -Depth 5
```

Run it:
```powershell
.\test-chat.ps1
```

## Force Refresh (Manual Indexing Trigger)

If you want to force crawling/indexing even for general questions, use `force_refresh: true`:

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me about Python programming",
    "force_refresh": true
  }'
```

This bypasses the keyword detection and always triggers the crawl→index→retrieve pipeline.

## Verify Indexing is Working

### 1. Check Indexer Health
```bash
curl http://localhost:8002/health | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

Expected output:
```json
{
  "status": "healthy",
  "embedding_model": {
    "healthy": true,
    "model": "text-embedding-3-large"
  }
}
```

### 2. Check Qdrant Collections
```bash
curl http://localhost:6333/collections | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

You should see `web_rag_docs` collection.

### 3. Monitor Indexing Activity

**Watch indexer logs:**
```bash
docker-compose logs -f indexer
```

**Check for indexing messages:**
```
INFO: Indexed 5 documents in 3 chunks
INFO: Generated embeddings for 3 chunks
```

### 4. Verify Vector Store

Open Qdrant Dashboard: http://localhost:6333/dashboard

- Click on `web_rag_docs` collection
- Check the point count (should increase after indexing)
- View sample vectors

## Complete End-to-End Test

```powershell
# 1. Check services are healthy
Write-Host "=== Checking Service Health ===" -ForegroundColor Cyan
.\scripts\health-check.ps1

# 2. Send a query that triggers indexing
Write-Host "`n=== Sending Test Query ===" -ForegroundColor Cyan
$body = @{
    message = "What are the latest Tesla earnings?"
    stream = $false
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:8000/agent/chat" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body

# 3. Check if tool was called
Write-Host "`n=== Tool Calls ===" -ForegroundColor Yellow
if ($response.tool_calls.Count -gt 0) {
    Write-Host "✓ Crawl and index was triggered!" -ForegroundColor Green
    $response.tool_calls | ConvertTo-Json -Depth 5
} else {
    Write-Host "✗ No tool calls (may be using cached data)" -ForegroundColor Red
}

# 4. View response and sources
Write-Host "`n=== Response ===" -ForegroundColor Cyan
$response.response

Write-Host "`n=== Sources (from vector DB) ===" -ForegroundColor Yellow
$response.sources | ForEach-Object {
    Write-Host "  - $($_.url)" -ForegroundColor Gray
}

# 5. Check Qdrant collection size
Write-Host "`n=== Vector Database Stats ===" -ForegroundColor Cyan
$qdrant = Invoke-RestMethod -Uri "http://localhost:6333/collections/web_rag_docs"
Write-Host "Total vectors stored: $($qdrant.result.points_count)" -ForegroundColor Green
```

## What Each Component Does

```
User Query: "Latest NVIDIA earnings?"
    ↓
[Gateway] Detects "latest" + "earnings"
    ↓
[Crawler] Fetches nvidia.com/investors, sec.gov, etc.
    ↓ Returns cleaned HTML/markdown
[Indexer] Receives documents
    ↓
[LlamaIndex] Chunks text (1024 token chunks)
    ↓
[Azure OpenAI] Creates embeddings (text-embedding-3-large)
    ↓
[Qdrant] Stores vectors with metadata
    ↓
[Gateway] Queries vector DB for relevant chunks
    ↓
[LLM] Generates response with citations
    ↓
User receives answer with sources
```

## Troubleshooting

### Indexing Not Triggering

**Check 1: Are you using trigger words?**
```powershell
# This WON'T trigger indexing:
$body = @{ message = "Explain machine learning" } | ConvertTo-Json

# This WILL trigger indexing:
$body = @{ message = "Latest machine learning news" } | ConvertTo-Json
```

**Check 2: Use force_refresh:**
```powershell
$body = @{
    message = "Explain machine learning"
    force_refresh = $true
} | ConvertTo-Json
```

**Check 3: Verify embedding model is healthy:**
```bash
curl http://localhost:8002/health
```

### Indexer Shows Errors

**Check Azure OpenAI deployment:**
```bash
# Look for embedding_model.healthy = true
curl http://localhost:8002/health | ConvertFrom-Json
```

**Check environment variables:**
```bash
docker-compose exec indexer env | grep -E "EMBED_MODEL|AZURE"
```

### No Sources in Response

This means:
1. Indexing worked, but no relevant content was found in vector DB
2. Try a more specific query
3. Check if Qdrant has any vectors:
```bash
curl http://localhost:6333/collections/web_rag_docs
```

## Example Session

```
You: What are the latest NVIDIA earnings?

[Behind the scenes:]
✓ Gateway detects "latest" + "earnings"
✓ Crawler fetches 5 pages from nvidia.com, reuters.com
✓ Indexer chunks into 12 segments
✓ Embeddings created (12 vectors, 3072 dimensions each)
✓ Stored in Qdrant collection 'web_rag_docs'
✓ Retrieved top 8 relevant chunks
✓ LLM generates response with citations

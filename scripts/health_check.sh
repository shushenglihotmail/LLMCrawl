#!/bin/bash
# Health check script for LLMCrawl services (Linux/macOS)

echo "🏥 Service Health Check"
echo "======================"
echo ""

# Service endpoints
services=(
    "Gateway:http://localhost:8000/health"
    "Crawler:http://localhost:8001/health"
    "Indexer:http://localhost:8002/health"
    "MCP Server:http://localhost:8003/health"
    "Qdrant:http://localhost:6333/healthz"
    "Firecrawl:http://localhost:3002/v1/scrape"
)

# Check each service
for service in "${services[@]}"; do
    name="${service%%:*}"
    url="${service#*:}"

    # Special handling for services that need POST
    if [[ "$name" == "Firecrawl" ]]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$url" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer fc-development" \
            -d '{"url":"https://example.com"}' 2>/dev/null)
    else
        response=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null)
    fi

    if [[ "$response" == "200" ]]; then
        echo "✅ $name: Healthy"
    elif [[ "$response" == "000" ]]; then
        echo "❌ $name: Not Running"
    else
        echo "⚠️  $name: Responding (HTTP $response)"
    fi
done

echo ""
echo "🐳 Docker Container Status:"
docker ps --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | grep -E "web-rag|NAMES" || echo "Docker not available"

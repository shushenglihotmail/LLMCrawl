#!/bin/bash
# Quick start script for LLMCrawl development environment

# Change to project root directory (parent of scripts)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "🚀 LLMCrawl Development Environment Quick Start"
echo "=============================================="

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "Please run setup first:"
    echo "  Windows: .\scripts\setup_dev.ps1"
    echo "  Unix:    python scripts/setup_dev.py"
    exit 1
fi

# Check if OpenAI API key is configured
if grep -q "your_openai_key_here" .env; then
    echo "⚠️  Please configure your API keys in .env file"
    echo "   Edit .env and add your OPENAI_API_KEY"
fi

echo ""
echo "🔧 Starting development environment..."
make dev-up

echo ""
echo "⏳ Waiting for services to start..."
sleep 10

echo ""
echo "🏥 Checking service health..."
make health

echo ""
echo "✅ Development environment ready!"
echo ""
echo "📍 Service URLs:"
echo "   Gateway:         http://localhost:8000"
echo "   Crawler:         http://localhost:8001"
echo "   Indexer:         http://localhost:8002"
echo "   Qdrant Dashboard: http://localhost:6333/dashboard"
echo ""
echo "🧪 Test the system:"
echo '   curl -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d '"'"'{"message": "Hello!"}'"'"
echo ""
echo "📚 Useful commands:"
echo "   make dev-logs    - View logs"
echo "   make dev-down    - Stop services"
echo "   make test-dev    - Run tests"
echo "   make pre-commit  - Run code quality checks"
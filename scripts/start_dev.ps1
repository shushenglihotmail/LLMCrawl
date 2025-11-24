# PowerShell quick start script for LLMCrawl development environment

# Change to project root directory (parent of scripts)
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptRoot
Set-Location $projectRoot

Write-Host "🚀 LLMCrawl Development Environment Quick Start" -ForegroundColor Cyan
Write-Host "=============================================="

# Check if .env exists
if (!(Test-Path "deploy/.env")) {
    Write-Host "❌ deploy/.env file not found!" -ForegroundColor Red
    Write-Host "Please run setup first:"
    Write-Host "  .\scripts\setup_dev.ps1"
    exit 1
}

# Check if OpenAI API key is configured
$envContent = Get-Content "deploy/.env" -Raw
if ($envContent -match "your_openai_key_here") {
    Write-Host "⚠️  Please configure your API keys in .env file" -ForegroundColor Yellow
    Write-Host "   Edit .env and add your OPENAI_API_KEY"
}

Write-Host ""
Write-Host "🔧 Starting development environment..." -ForegroundColor Green
& make dev-up

Write-Host ""
Write-Host "⏳ Waiting for services to start..." -ForegroundColor Blue
Start-Sleep -Seconds 10

Write-Host ""
Write-Host "🏥 Checking service health..." -ForegroundColor Green
& make health

Write-Host ""
Write-Host "✅ Development environment ready!" -ForegroundColor Green
Write-Host ""
Write-Host "📍 Service URLs:"
Write-Host "   Gateway:         http://localhost:8000"
Write-Host "   Crawler:         http://localhost:8001"
Write-Host "   Indexer:         http://localhost:8002"
Write-Host "   Qdrant Dashboard: http://localhost:6333/dashboard"
Write-Host ""
Write-Host "🧪 Test the system:"
Write-Host '   curl -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d ''{"message": "Hello!"}'''
Write-Host ""
Write-Host "📚 Useful commands:"
Write-Host "   make dev-logs    - View logs"
Write-Host "   make dev-down    - Stop services"
Write-Host "   make test-dev    - Run tests"
Write-Host "   make pre-commit  - Run code quality checks"

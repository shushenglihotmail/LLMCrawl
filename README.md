# Web RAG System

A production-ready, containerized Python web RAG system that enables LLMs to trigger web crawling, index results, and answer questions with citations. Features conversation memory, intelligent tool calling, and multi-source web scraping.

## 🏗️ Architecture

The system consists of four main services with conversation state management:

- **Gateway Service** (Port 8000): FastAPI orchestrator with OpenAI/Azure SDK, conversation history storage, intelligent tool triggering
- **Crawler Service** (Port 8001): FireCrawl + Playwright fallback + Trafilatura extraction with sequential rendering
- **Indexer Service** (Port 8002): LlamaIndex + Vector DB (Qdrant/pgvector) for RAG
- **Demo Client** (Port 3000): Optional web interface with SSE streaming

### Enhanced Tool Calling Pipeline with Conversation Memory

```mermaid
graph TB
    A[User Query + conversation_id] --> B{Load Previous<br/>Conversation?}
    B -->|Yes| C[Retrieve History<br/>from Store]
    B -->|No| D[New Conversation]
    C --> E{Contains Trigger Words<br/>OR Context Suggests<br/>News Query?}
    D --> E
    E -->|Yes| F[Include crawl_and_refresh Tool]
    E -->|No| G[Direct LLM Response]
    F --> H{Force Tool Call?}
    H -->|Explicit Query| I[tool_choice=function]
    H -->|Follow-up| J[tool_choice=auto]
    I --> K[LLM MUST Call Tool]
    J --> K
    K --> L[FireCrawl Search & Crawl]
    L --> M[Playwright Fallback if Needed]
    M --> N[Trafilatura Text Extraction]
    N --> O[LlamaIndex Chunking & Embedding]
    O --> P[Vector DB Storage]
    P --> Q[Semantic Retrieval with Recency Boost]
    Q --> R[LLM Response with Citations]
    R --> S[Store User + Assistant Messages]
    S --> T[Return Response + conversation_id]
    G --> S
```

## ✨ Key Features

- **Conversation Memory**: Multi-turn conversations with context preservation (24-hour TTL)
- **Intelligent Tool Triggering**: Automatic detection of queries needing fresh data (29+ trigger words)
- **Context-Aware Follow-ups**: Recognizes when follow-up questions relate to previous news queries
- **Forced Tool Execution**: Prevents incomplete "I'll fetch..." responses by enforcing tool calls
- **Sequential Browser Rendering**: Stable Playwright execution in Docker (no concurrency issues)
- **FireCrawl Integration**: Redis-backed rate limiting with proper connection handling
- **Flexible Timeouts**: 45-second gateway timeout, 25-second FireCrawl timeout
- **Internal Site Authentication**: Support for headers, cookies, basic auth, and bearer tokens for crawling authenticated internal sites

## 🚀 Quick Start

### 1. Clone and Setup Environment

```bash
git clone <repository-url>
cd LLMCrawl

# Copy environment template
cp .env.example .env
```

### 2. Configure Environment Variables

Edit `.env` file with your API keys and preferences:

```bash
# Required: OpenAI Configuration
OPENAI_API_KEY=your_openai_key_here

# OR: Azure OpenAI Configuration
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your_azure_key_here

# Vector Database (choose one)
VECTOR_DB=qdrant  # or pgvector

# Optional: Firecrawl API Key (for better crawling)
FIRECRAWL_API_KEY=your_firecrawl_key_here

# Crawling Configuration
ALLOWED_DOMAINS=sec.gov,ft.com,wsj.com,nvidia.com,reuters.com,bloomberg.com
RESPECT_ROBOTS=true

# For Internal Sites (optional): See docs/AUTHENTICATION_QUICKSTART.md
# FIRECRAWL_AUTH_TYPE=headers  # or cookies, basic, bearer
# FIRECRAWL_AUTH_HEADERS={"X-API-Key": "your-key"}
```

### 3. Authentication for Internal Sites (Optional)

To crawl internal sites requiring authentication:

```bash
# Quick setup - add to .env:
FIRECRAWL_AUTH_TYPE=headers
FIRECRAWL_AUTH_HEADERS={"X-API-Key": "your-key"}

# OR use cookies:
FIRECRAWL_AUTH_TYPE=cookies
FIRECRAWL_AUTH_COOKIES={"session_id": "abc123"}
```

📚 **See full authentication guide**: [`docs/AUTHENTICATION_QUICKSTART.md`](docs/AUTHENTICATION_QUICKSTART.md)

## 🛠️ Development Environment

For development work, use the automated setup scripts located in the `scripts/` folder:

### Quick Setup (Recommended)

**Windows (PowerShell):**
```powershell
# Complete setup
.\scripts\setup_dev.ps1

# Quick start (after setup)
.\scripts\start_dev.ps1
```

**Unix/Linux/macOS:**
```bash
# Complete setup
python scripts/setup_dev.py

# Quick start (after setup)
./scripts/start_dev.sh
```

**Using Makefile:**
```bash
# Setup development environment
make setup-dev              # Cross-platform
make setup-dev-windows       # Windows specific

# Quick start development environment
make quick-start            # Unix/Linux/macOS
make quick-start-windows    # Windows
```

### VS Code Integration

For VS Code users, open the workspace file for an optimized development experience:

```bash
code LLMCrawl.code-workspace
```

This provides:
- Pre-configured debug configurations for all services
- Integrated tasks for setup and development
- Recommended extensions
- Python environment auto-detection

See `DEVELOPMENT.md` for detailed development setup instructions.

## 🚀 Production Deployment

### 3. Start All Services

```bash
# Start core services
docker-compose up -d

# Or start with demo client
docker-compose --profile demo up -d

# Or start with monitoring
docker-compose --profile monitoring up -d
```

### 4. Verify Deployment

```bash
# Start core services
docker-compose up -d

# Or start with demo client
docker-compose --profile demo up -d

# Or start with monitoring
docker-compose --profile monitoring up -d
```

### 4. Verify Deployment

```bash
# Check all service health
make health

# Or manually check each service
curl http://localhost:8000/health  # Gateway
curl http://localhost:8001/health  # Crawler
curl http://localhost:8002/health  # Indexer
```

### 5. Test the System

```bash
# Test end-to-end functionality
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the latest NVIDIA earnings?"}'
```

## 📋 Detailed Deployment Guide

### Prerequisites

- Docker and Docker Compose installed
- At least 4GB RAM available
- OpenAI API key or Azure OpenAI access
- Internet connection for web crawling

### Service-by-Service Deployment

#### 1. Vector Database Setup

**Option A: Qdrant (Recommended)**
```bash
# Qdrant will start automatically with docker-compose
# Accessible at http://localhost:6333
# Web UI at http://localhost:6333/dashboard
```

**Option B: PostgreSQL with pgvector**
```bash
# Set in .env
VECTOR_DB=pgvector
PG_DSN=postgresql://postgres:password@postgres:5432/rag_db

# PostgreSQL will start automatically
# Accessible at localhost:5432
```

#### 2. Supporting Services

```bash
# Redis (for caching and Firecrawl)
docker-compose up -d redis

# Firecrawl (web crawling service)
docker-compose up -d firecrawl

# Check Firecrawl health
curl http://localhost:3002/health
```

#### 3. Core Application Services

```bash
# Start in dependency order
docker-compose up -d qdrant postgres redis
docker-compose up -d firecrawl
docker-compose up -d indexer
docker-compose up -d crawler
docker-compose up -d gateway

# Verify all services
docker-compose ps
```

#### 4. Optional Services

```bash
# Demo web client
docker-compose --profile demo up -d demo-client

# Monitoring stack (Prometheus + Grafana)
docker-compose --profile monitoring up -d
# Or use: make monitoring-up
```

**Monitoring Access:**
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001 (admin/admin)
- Qdrant Dashboard: http://localhost:6333/dashboard

For detailed monitoring setup and usage, see [docs/MONITORING.md](docs/MONITORING.md).

# Monitoring stack
docker-compose --profile monitoring up -d prometheus grafana
```

### Environment Configuration Details

#### LLM Provider Setup

**OpenAI Configuration:**
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
CHAT_MODEL=gpt-4-turbo-preview
EMBED_MODEL=text-embedding-3-large
```

**Azure OpenAI Configuration:**
```bash
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your_key_here
AZURE_OPENAI_API_VERSION=2024-02-01
CHAT_MODEL=gpt-4-turbo
EMBED_MODEL=text-embedding-3-large
```

#### Crawling Configuration

```bash
# Domains to prioritize for crawling
ALLOWED_DOMAINS=sec.gov,ft.com,wsj.com,nvidia.com,reuters.com,bloomberg.com,techcrunch.com

# Respect robots.txt (recommended: true)
RESPECT_ROBOTS=true

# Crawling limits
MAX_CONCURRENCY=4
REQUEST_TIMEOUT_MS=20000
RATE_LIMIT_PER_MINUTE=60

# User agent for requests
USER_AGENT=WebRAG/1.0 (+https://github.com/yourorg/webrag)
```

#### Vector Database Selection

```bash
# Qdrant (fast, purpose-built for vectors)
VECTOR_DB=qdrant
QDRANT_URL=http://qdrant:6333

# OR PostgreSQL with pgvector (SQL queries + vectors)
VECTOR_DB=pgvector
PG_DSN=postgresql://postgres:password@postgres:5432/rag_db
```

### Health Checks and Monitoring

#### Quick Health Checks

**Using PowerShell Script (Windows - Recommended):**
```powershell
.\scripts\health-check.ps1
```

**Using Make Command (Linux/Mac):**
```bash
make health

# Or check individual services
make health-gateway
make health-crawler
make health-indexer
```

**Using curl Commands Directly:**
```bash
# Check all services
curl http://localhost:8000/health  # Gateway
curl http://localhost:8001/health  # Crawler
curl http://localhost:8002/health  # Indexer
curl http://localhost:6333/health  # Qdrant

# For detailed JSON output (Windows PowerShell)
curl http://localhost:8000/health | ConvertFrom-Json | ConvertTo-Json -Depth 10

# For detailed JSON output (Linux/Mac with jq)
curl http://localhost:8000/health | jq .
```

**Health Check Response Format:**
```json
{
  "status": "healthy",
  "service": "gateway",
  "timestamp": "2025-11-15T10:30:00Z",
  "components": {
    "crawler": "healthy",
    "indexer": "healthy",
    "llm": "healthy"
  }
}
```

#### Prometheus Metrics Monitoring

Start the monitoring stack:

```bash
# Start Prometheus and Grafana
docker-compose --profile monitoring up -d

# Or use Make command (Linux/Mac)
make monitoring-up
```

**Access Monitoring Dashboards:**
- **Prometheus**: http://localhost:9090 - Raw metrics and queries
- **Grafana**: http://localhost:3001 - Visual dashboards (default login: admin/admin)
- **Qdrant Dashboard**: http://localhost:6333/dashboard - Vector database stats

**Check Metrics Endpoints:**

**Using PowerShell Script (Windows - Recommended):**
```powershell
.\scripts\check-metrics.ps1
```

**Using Make Commands (Linux/Mac):**
```bash
make metrics-all        # Summary of all services
make metrics-gateway    # Detailed gateway metrics
make metrics-crawler    # Detailed crawler metrics
make metrics-indexer    # Detailed indexer metrics
```

**Using curl Directly:**
```bash
# Gateway metrics
curl http://localhost:8000/metrics

# Crawler metrics
curl http://localhost:8001/metrics

# Indexer metrics
curl http://localhost:8002/metrics
```

**For Complete Monitoring Guide:** See [docs/MONITORING.md](docs/MONITORING.md)

**Key Metrics to Monitor:**

```promql
# Service availability (1 = up, 0 = down)
up{job="gateway"}
up{job="crawler"}
up{job="indexer"}

# Request rate (requests per second)
rate(http_requests_total[5m])

# Request latency (95th percentile)
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Error rate
rate(http_requests_total{status=~"5.."}[5m])

# Memory usage
process_resident_memory_bytes
```

**Grafana Setup:**

1. Open Grafana at http://localhost:3001
2. Login with admin/admin
3. Prometheus datasource is auto-configured
4. Create dashboards with the queries above

#### Service Logs

```bash
# View service logs
docker-compose logs -f gateway
docker-compose logs -f crawler
docker-compose logs -f indexer

# Monitor resource usage
docker stats
```

### Troubleshooting Deployment

#### Common Issues

1. **Service Won't Start**
   ```bash
   # Check logs
   docker-compose logs service-name

   # Rebuild if needed
   docker-compose build --no-cache service-name
   ```

2. **Port Conflicts**
   ```bash
   # Check what's using ports
   netstat -tulpn | grep :8000

   # Change ports in docker-compose.yml if needed
   ```

3. **Memory Issues**
   ```bash
   # Check available memory
   free -h

   # Reduce concurrent processes in .env
   MAX_CONCURRENCY=2
   ```

4. **API Key Issues**
   ```bash
   # Verify environment variables
   docker-compose exec gateway env | grep -i openai

   # Test API connection
   docker-compose exec gateway python -c "import openai; print('API key works')"
   ```

## 🧪 End-to-End Testing

### Automated Test Suite

```bash
# Run all unit tests
make test

# Run integration tests (requires services to be running)
make test-integration

# Or run tests manually
docker-compose exec gateway python -m pytest tests/ -v
docker-compose exec crawler python -m pytest tests/ -v
docker-compose exec indexer python -m pytest tests/ -v
```

### Manual End-to-End Test

```bash
# 1. Start all services
docker-compose up -d

# 2. Wait for services to be ready (30-60 seconds)
sleep 60

# 3. Run the comprehensive integration test
python tests/integration/test_end_to_end.py
```

### Step-by-Step Verification

#### Test 1: Service Health Checks
```bash
# All should return {"status": "healthy"}
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:6333/health  # Qdrant
```

#### Test 2: Manual Crawling
```bash
curl -X POST http://localhost:8001/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Tesla earnings Q3 2024",
    "seed_urls": ["https://ir.tesla.com"],
    "freshness_days": 30,
    "max_results": 3
  }' | jq .
```

Expected response:
```json
{
  "docs": [
    {
      "url": "https://ir.tesla.com/...",
      "title": "Tesla Q3 2024 Earnings",
      "markdown": "Tesla reported...",
      "published_at": "2024-10-15T...",
      "source": "ir.tesla.com"
    }
  ],
  "query": "Tesla earnings Q3 2024",
  "total_found": 1,
  "processed": 1
}
```

#### Test 3: Manual Indexing
```bash
curl -X POST http://localhost:8002/index \
  -H "Content-Type: application/json" \
  -d '{
    "docs": [{
      "url": "https://example.com/test",
      "title": "Test Document",
      "markdown": "This is test content about artificial intelligence and machine learning.",
      "published_at": "2024-01-15T10:00:00Z"
    }]
  }' | jq .
```

Expected response:
```json
{
  "indexed": 1,
  "chunks": 1,
  "documents": 1,
  "vector_db": "qdrant"
}
```

#### Test 4: Manual Retrieval
```bash
curl -X POST http://localhost:8002/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "artificial intelligence",
    "k": 5,
    "recency_boost_days": 14
  }' | jq .
```

Expected response:
```json
{
  "hits": [
    {
      "url": "https://example.com/test",
      "title": "Test Document",
      "published_at": "2024-01-15T10:00:00Z",
      "snippet": "...artificial intelligence and machine learning...",
      "score": 0.89,
      "boosted_score": 0.95
    }
  ],
  "total_found": 1,
  "query": "artificial intelligence"
}
```

#### Test 5: End-to-End Chat with Tool Calling
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are the latest NVIDIA earnings results?",
    "stream": false
  }' | jq .
```

Expected response structure:
```json
{
  "response": "Based on the latest information:\n\n• NVIDIA reported record Q3 revenue...\n\n**Financial Performance**\nNVIDIA's third quarter showed...(nvidia.com, 2024-11-20)\n\n**Sources:**\n- NVIDIA Q3 Results (investor.nvidia.com, 2024-11-20)",
  "conversation_id": "uuid...",
  "sources": [
    {
      "url": "https://investor.nvidia.com/...",
      "title": "NVIDIA Q3 Results",
      "published_at": "2024-11-20"
    }
  ],
  "tool_calls": [
    {
      "function": {
        "name": "crawl_and_refresh",
        "arguments": "{\"query\":\"NVIDIA earnings latest results\"}"
      }
    }
  ]
}
```

#### Test 6: General Chat (No Tool Calling)
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain how neural networks work in general.",
    "stream": false
  }' | jq .
```

Expected: Response should NOT include tool_calls (empty array).

### Performance Testing

```bash
# Test concurrent requests
for i in {1..5}; do
  curl -X POST http://localhost:8000/api/v1/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "What is machine learning?"}' &
done
wait

# Monitor response times
time curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Latest AI news?"}'
```

## 🎯 Usage Examples

### Example 1: Financial News Query
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are the latest Apple earnings and guidance?",
    "force_refresh": true
  }'
```

**Expected Behavior:**
1. System detects "latest" + "earnings" keywords
2. Calls `crawl_and_refresh` tool automatically
3. Searches for Apple earnings information
4. Crawls from investor.apple.com, SEC filings, financial news
5. Indexes and retrieves most relevant recent content
6. Returns response with inline citations

**Sample Response:**
```
Based on the latest information:

• Apple reported Q4 revenue of $89.5 billion, down 1% year-over-year
• iPhone revenue declined 3% but Services grew 16% to record high
• Company provided cautious guidance for Q1 amid economic uncertainty

**Financial Performance**
Apple's fourth quarter results showed mixed performance (investor.apple.com, 2024-11-01), with total revenue of $89.5 billion compared to $90.1 billion in the prior year. The iPhone segment faced headwinds but Services continued strong growth.

**Guidance and Outlook**
Management provided conservative guidance for Q1 2025 (sec.gov, 2024-11-01), citing macroeconomic uncertainties and foreign exchange impacts.

**Sources:**
- Apple Q4 2024 Results (investor.apple.com, 2024-11-01)
- Apple 10-K Filing (sec.gov, 2024-11-01)
- Apple Earnings Analysis (reuters.com, 2024-11-01)
```

### Example 2: Technology News Query
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Any recent breakthroughs in quantum computing this month?",
    "seed_urls": ["https://arxiv.org", "https://nature.com"]
  }'
```

**Expected Behavior:**
1. Detects "recent breakthroughs" + "this month"
2. Uses seed URLs to prioritize academic sources
3. Crawls recent quantum computing papers and news
4. Applies 30-day freshness filter
5. Returns findings with publication dates

### Example 3: Stock Market Query
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What happened to Tesla stock today? Any news driving the movement?",
    "freshness_days": 1
  }'
```

**Expected Behavior:**
1. Crawls recent Tesla news and stock analysis
2. Looks for same-day content only (freshness_days: 1)
3. Correlates stock movement with news events
4. Provides real-time analysis with citations

### Example 4: Research Paper Query
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are the latest papers on large language models published this week?",
    "seed_urls": ["https://arxiv.org", "https://papers.nips.cc"]
  }'
```

### Example 5: General Knowledge (No Crawling)
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain the concept of transformer architectures in machine learning."
  }'
```

**Expected Behavior:**
1. System recognizes this as general knowledge
2. Does NOT trigger web crawling
3. Returns response from LLM's training data
4. No tool_calls in response

### Example 6: Streaming Response
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Latest developments in autonomous vehicles?",
    "stream": true
  }'
```

**Expected Behavior:**
1. Returns Server-Sent Events (SSE) stream
2. Shows progress: search → crawl → index → retrieve → generate
3. Real-time response generation

### Example 7: Force Refresh
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me about the history of the internet.",
    "force_refresh": true
  }'
```

**Expected Behavior:**
1. Even though query is historical, force_refresh=true triggers crawling
2. Searches for recent articles about internet history
3. Combines fresh sources with general knowledge

## 🌐 Demo Web Interface

### Access the Demo

```bash
# Start with demo profile
docker-compose --profile demo up -d

# Visit http://localhost:3000
```

### Demo Features

- **Interactive Chat Interface**: Clean, modern web UI
- **Real-time Responses**: See responses as they're generated
- **Source Display**: View all sources with publication dates
- **Example Queries**: Pre-built buttons for common use cases
- **Connection Status**: Real-time service health indicator
- **Responsive Design**: Works on desktop and mobile

### Example Queries in Demo

Try these pre-built examples:
- "What are the latest NVIDIA earnings?"
- "Recent Tesla news?"
- "Latest AI developments this week?"
- "Apple stock performance today?"

## 📊 Monitoring and Observability

### Access Monitoring Dashboards

```bash
# Start monitoring services
docker-compose --profile monitoring up -d

# Access dashboards
# Grafana: http://localhost:3001 (admin/admin)
# Prometheus: http://localhost:9090
```

### Key Metrics to Monitor

- **Response Times**: Chat endpoint latency
- **Tool Call Frequency**: How often crawling is triggered
- **Crawling Success Rate**: Percentage of successful crawls
- **Index Throughput**: Documents indexed per minute
- **Vector DB Performance**: Query response times
- **Error Rates**: Failed requests by service

### Custom Alerts

Set up alerts in Grafana for:
- Service downtime
- High error rates (>5%)
- Slow response times (>10s)
- Vector DB storage usage
- Failed crawls rate

## API Examples

### Chat with Auto-Crawling
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are the latest developments in AI chips?",
    "stream": true
  }'
```

### Manual Crawling
```bash
curl -X POST http://localhost:8001/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Tesla earnings Q3 2024",
    "seed_urls": ["https://ir.tesla.com"],
    "freshness_days": 7,
    "depth": 2
  }'
```

### Indexing Documents
```bash
curl -X POST http://localhost:8002/index \
  -H "Content-Type: application/json" \
  -d '{
    "docs": [{
      "url": "https://example.com/article",
      "title": "Example Article",
      "markdown": "# Article Content...",
      "published_at": "2024-01-15"
    }]
  }'
```

## Monitoring

Access monitoring dashboards:
- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9090

## 📚 Contributing

### Development Workflow

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Install development dependencies**
   ```bash
   pip install -r requirements-dev.txt
   pre-commit install
   ```
4. **Make your changes**
5. **Run tests and linting**
   ```bash
   make test
   make lint
   make type-check
   ```
6. **Submit a pull request**

### Code Standards

- **Python**: Follow PEP 8, use black for formatting
- **Type hints**: Required for all public functions
- **Docstrings**: Google-style docstrings for all modules, classes, and functions
- **Tests**: Maintain >80% code coverage
- **Security**: Run `bandit` security scans

### Project Structure

```
llmcrawl/
├── gateway/          # Main API gateway service
│   ├── llm/         # LLM client and prompts
│   ├── routers/     # FastAPI route handlers
│   └── main.py      # Gateway application entry point
├── crawler/          # Web crawling service
│   ├── clients/     # External service clients (Firecrawl)
│   ├── render/      # Browser automation (Playwright)
│   ├── extract/     # Content extraction (Trafilatura)
│   └── main.py      # Crawler application entry point
├── indexer/          # Document indexing service
│   ├── adapters/    # LlamaIndex integration
│   ├── vector/      # Vector database implementations
│   └── main.py      # Indexer application entry point
├── tests/            # Test suites
│   ├── unit/        # Unit tests
│   ├── integration/ # Integration tests
│   └── load/        # Load testing
├── demo/            # Web demo interface
├── docker/          # Docker configurations
├── monitoring/      # Prometheus/Grafana configs
└── docs/            # Additional documentation
    ├── AUTHENTICATION.md           # Full authentication guide
    ├── AUTHENTICATION_QUICKSTART.md # 5-minute setup guide
    ├── CRAWLING_LIMITATIONS.md     # News site extraction issues
    ├── MONITORING.md               # Health checks and metrics
    └── TESTING_INDEXING.md         # Testing guide
```

## 🎯 Roadmap

### Version 1.1 (Next Release)
- [ ] Multi-modal support (images, PDFs)
- [ ] Advanced filtering and search operators
- [ ] Webhook support for real-time updates
- [ ] GraphQL API endpoints
- [ ] Advanced caching strategies

### Version 1.2 (Future)
- [ ] Multi-language support
- [ ] Custom embedding models
- [ ] Advanced summarization techniques
- [ ] Integration with more vector databases
- [ ] Machine learning-powered content classification

### Version 2.0 (Long-term)
- [ ] Multi-agent collaboration
- [ ] Advanced reasoning and planning
- [ ] Custom tool development framework
- [ ] Enterprise authentication and authorization
- [ ] Advanced analytics and insights

## 🤝 Support

### Getting Help

1. **Check the documentation** in this README
2. **Search existing issues** on GitHub
3. **Join our Discord** for community support
4. **Create an issue** for bugs or feature requests

### Issue Templates

When reporting issues, please use our templates:
- **Bug Report**: Include reproduction steps, environment details, and error logs
- **Feature Request**: Describe the use case and expected behavior
- **Performance Issue**: Include performance metrics and system configuration

### Commercial Support

For enterprise deployments and commercial support:
- Email: support@llmcrawl.dev
- Consulting services available
- Custom feature development
- Priority support and SLA options

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

**Built with ❤️ by the LLMCrawl team**

*Empowering AI applications with real-time web intelligence*

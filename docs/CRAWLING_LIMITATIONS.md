# Web Crawling Limitations and Workarounds

## Why Some News Sites Return Minimal Content

### The Problem

When crawling major news websites like CNN, New York Times, Wall Street Journal, etc., you may encounter:
- Very short snippets (just page titles)
- Missing article content
- Only UI elements extracted ("Close icon", navigation text)
- Empty or truncated responses

### Root Causes

#### 1. **JavaScript-Heavy Sites**
Modern news websites render content dynamically with JavaScript:
- Initial HTML contains minimal content
- Articles load via JavaScript after page load
- FireCrawl and traditional scrapers see the "empty shell"

#### 2. **Anti-Scraping Measures**
Major news outlets implement:
- Bot detection (Cloudflare, DataDome, PerimeterX)
- Rate limiting
- CAPTCHA challenges
- IP-based blocking
- User-agent filtering

#### 3. **Paywalls**
Many news sites require:
- Subscriptions (NYT, WSJ, FT)
- Registration
- Cookie consent
- Geographic restrictions

#### 4. **Content Protection**
Sites may use:
- Shadow DOM (hidden content)
- Canvas fingerprinting
- Browser fingerprinting
- Dynamic class names

## What the System Does

### Current Crawling Pipeline

```
User Query → Gateway
    ↓
[1] FireCrawl Search API
    - Searches Google/Bing for relevant URLs
    - Returns top 10 matching URLs
    ↓
[2] FireCrawl Scrape API
    - Attempts to scrape each URL
    - Uses Playwright for JavaScript rendering
    - Extracts text, markdown, metadata
    ↓
[3] Playwright Fallback (if FireCrawl fails)
    - Direct browser rendering
    - Custom extraction logic
    ↓
[4] Trafilatura Extraction
    - Cleans HTML
    - Extracts article content
    - Removes boilerplate
    ↓
[5] Robots.txt Filtering
    - Respects robots.txt rules
    - Filters disallowed URLs
    ↓
[6] Indexing
    - Chunks content (1024 tokens)
    - Creates embeddings
    - Stores in vector database
```

### What Typically Succeeds

✅ **Works Well:**
- Company investor relations pages (SEC filings, earnings)
- Technical documentation sites
- Blog posts and articles
- GitHub repositories
- Wikipedia
- arXiv and research papers
- Press releases
- Government websites

⚠️ **Partial Success:**
- News aggregators (limited content)
- RSS feeds (summaries only)
- Social media (public posts)

❌ **Often Fails:**
- Paywalled news (NYT, WSJ, FT)
- JavaScript-heavy news sites (CNN, MSNBC)
- Sites with aggressive anti-bot measures
- Video/streaming platforms
- Sites requiring login

## Workarounds

### 1. Use Better Sources

Instead of main news pages, try:
- **RSS Feeds**: `https://www.cnn.com/services/rss/`
- **API Endpoints**: Official news APIs
- **Press Release Sites**: PR Newswire, Business Wire
- **Company IR Pages**: Direct earnings reports
- **Alternative News Aggregators**: Google News, Bing News

### 2. Target Specific Article URLs

Instead of:
```
"Get CNN headlines"
```

Try:
```
"Summarize this article: [paste full CNN article URL]"
```

Or use seed_urls:
```json
{
  "message": "What's in this article?",
  "force_refresh": true,
  "seed_urls": ["https://www.cnn.com/2025/11/15/specific-article/index.html"]
}
```

### 3. Use News Aggregators

Try sources that are scraping-friendly:
- **Hacker News**: https://news.ycombinator.com
- **Reddit**: Various news subreddits
- **Google News**: https://news.google.com
- **BBC News**: Often more accessible
- **Reuters**: API-friendly
- **AP News**: Generally accessible

### 4. Query for Secondary Sources

Instead of:
```
"Latest CNN headlines"
```

Try:
```
"Latest tech news from TechCrunch and VentureBeat"
"Recent earnings reports from investor relations pages"
"Today's business news from Reuters and Bloomberg"
```

### 5. Use API Keys (If Available)

Some services provide official APIs:
- **News API**: https://newsapi.org
- **Google News API**
- **Bing News API**
- **Twitter API** (for breaking news)

## Configuration Options

### Adjust Crawling Behavior

In `.env`:

```bash
# Add more allowed domains
ALLOWED_DOMAINS=reuters.com,apnews.com,bbc.com,theguardian.com,axios.com,politico.com

# Disable robots.txt for testing (not recommended for production)
RESPECT_ROBOTS=false

# Increase timeout for slow-loading sites
REQUEST_TIMEOUT_MS=30000

# Change user agent (some sites block generic agents)
USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
```

### Use Force Refresh

Force crawling even when content might be cached:

```powershell
$body = @{
    message = "Latest news from BBC"
    force_refresh = $true
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/chat" -Method Post -ContentType "application/json" -Body $body
```

## Best Practices

### ✅ Do's

1. **Target specific article URLs** when possible
2. **Use company IR pages** for earnings/financial data
3. **Try multiple sources** for the same topic
4. **Use RSS feeds** for news aggregation
5. **Be specific** in your queries (include company names, dates)
6. **Check robots.txt** before adding new domains
7. **Monitor crawler logs** to see what's working

### ❌ Don'ts

1. **Don't scrape paywalled content** without subscription
2. **Don't ignore robots.txt** in production
3. **Don't hammer sites** with high request rates
4. **Don't expect video transcripts** (not supported)
5. **Don't rely on social media** for primary sources
6. **Don't use for time-critical breaking news** (delays inherent)

## Alternative Approaches

### For News Monitoring

Consider integrating:
1. **News API Services**: NewsAPI, Bing News, Google News
2. **RSS Feed Readers**: Dedicated RSS aggregation
3. **Social Media APIs**: Twitter, Reddit for breaking news
4. **Webhooks**: Company announcement services
5. **Email Alerts**: Subscribe to press releases

### For Financial Data

Use official sources:
1. **SEC EDGAR**: Free, comprehensive, reliable
2. **Company IR Pages**: Direct from source
3. **Yahoo Finance**: API-friendly
4. **Alpha Vantage**: Financial data API
5. **IEX Cloud**: Stock market data

### For Research

Use academic/technical sources:
1. **arXiv**: Research papers
2. **PubMed**: Medical research
3. **Google Scholar**: Academic citations
4. **GitHub**: Code and documentation
5. **Technical blogs**: Engineering blogs

## Example Queries That Work Better

### Instead of:
❌ "What are today's CNN headlines?"
❌ "Latest NYT articles"
❌ "Breaking news from major outlets"

### Try:
✅ "Latest NVIDIA earnings report from investor.nvidia.com"
✅ "Recent AI developments from TechCrunch and VentureBeat"
✅ "What's new in Python this week from python.org and Real Python"
✅ "Latest SEC filings for Tesla from sec.gov"
✅ "Recent AWS announcements from aws.amazon.com/blogs"

## Monitoring Crawl Success

### Check Logs

```powershell
# See what was successfully crawled
docker-compose logs crawler | Select-String "Successfully crawled"

# See extraction failures
docker-compose logs crawler | Select-String "No content extracted"

# Check robots.txt blocks
docker-compose logs crawler | Select-String "Crawling blocked"
```

### Inspect Retrieved Content

Look at the `sources` in responses:
- **Good**: Long snippets, published dates, meaningful titles
- **Bad**: Short snippets like "Close icon", missing dates, generic titles

### Check Vector Database

```powershell
# See what's actually indexed
$qdrant = Invoke-RestMethod http://localhost:6333/collections/web_rag_docs
Write-Host "Total vectors: $($qdrant.result.points_count)"
```

## Future Improvements

Potential enhancements to consider:
1. **Headless browser pool**: Better JavaScript handling
2. **Proxy rotation**: Avoid IP blocks
3. **Cookie management**: Handle consent forms
4. **Screenshot extraction**: OCR for visual content
5. **API integrations**: Direct news API access
6. **Selective paywall bypass**: Cached versions, archive.org
7. **Better user agents**: Rotate realistic browser fingerprints

## Summary

**The system CAN crawl CNN and NYT**, but due to:
- Heavy JavaScript requirements
- Anti-scraping measures
- Paywalls

The extracted content is often minimal. For better results, use:
- Direct article URLs (not homepage)
- Alternative news sources (Reuters, BBC, AP)
- Company IR pages for corporate news
- RSS feeds for headlines
- Official APIs where available

The current setup works best for **technical content, company announcements, and scraping-friendly news sources** rather than major paywall publications.

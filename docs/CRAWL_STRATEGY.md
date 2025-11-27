# Crawl Strategy & Limitations

This document describes how LLMCrawl handles web crawling for different site types, including external public sites, authenticated internal sites, and depth crawling. It also covers known limitations and workarounds.

## Table of Contents

- [Overview](#overview)
- [External Sites (Public Internet)](#external-sites-public-internet)
- [Internal Sites (Authenticated)](#internal-sites-authenticated)
- [Depth Crawling](#depth-crawling)
- [Fallback Strategy](#fallback-strategy)
- [Limitations](#limitations)
- [Workarounds](#workarounds)
- [Configuration Reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## Overview

LLMCrawl uses a **hybrid crawling strategy** that combines:
- **FireCrawl**: Fast, scalable scraping service with Playwright support
- **Playwright**: Browser automation for JavaScript rendering and authenticated sessions
- **Trafilatura**: Content extraction and markdown conversion

```
┌─────────────────────────────────────────────────────────────────┐
│                    CRAWL STRATEGY OVERVIEW                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  External Sites (Public):                                       │
│    → FireCrawl /v1/search + /v1/scrape                         │
│    → Playwright fallback if FireCrawl fails                    │
│                                                                 │
│  Internal Sites (Authenticated):                                │
│    → FireCrawl /v1/scrape with Cookie headers                  │
│    → Playwright fallback with storage_state                    │
│                                                                 │
│  Depth Crawling:                                                │
│    → Depth 1: FireCrawl scrapes seed URLs                      │
│    → Link Extraction: Parse markdown for same-domain links     │
│    → Depth 2+: FireCrawl scrapes discovered links              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## External Sites (Public Internet)

For public websites without authentication requirements.

### Strategy

1. **Search Phase** (if no seed URLs):
   - FireCrawl `/v1/search` finds relevant URLs
   - Returns top matches based on query

2. **Scrape Phase**:
   - FireCrawl `/v1/scrape` fetches and renders pages
   - Uses Playwright internally for JavaScript

3. **Fallback**:
   - If FireCrawl fails → Playwright direct rendering
   - Trafilatura extracts clean content

### Request Flow

```
User Query (no seed URLs)
    │
    ▼
┌─────────────────┐
│ FireCrawl       │
│ /v1/search      │ ──→ Find relevant URLs
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ FireCrawl       │
│ /v1/scrape      │ ──→ Fetch & render pages
└─────────────────┘
    │
    ▼ (if fails)
┌─────────────────┐
│ Playwright      │
│ Direct render   │ ──→ Browser automation fallback
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ Trafilatura     │ ──→ Extract clean markdown
└─────────────────┘
```

### Configuration

```bash
# .env
FIRECRAWL_URL=http://firecrawl:3002
FIRECRAWL_AUTH_TYPE=none
RESPECT_ROBOTS=true
```

---

## Internal Sites (Authenticated)

For sites requiring authentication (e.g., osgwiki.com, internal wikis).

### Challenge

FireCrawl's native `/v1/crawl` endpoint has a **known architectural limitation**:
- The async crawl workers don't receive authentication headers
- Link discovery fails on auth-protected sites
- `/v1/batch/scrape` has the same issue (workers don't get cookies)

### Solution: Cookie-Based Authentication

We pass authentication cookies directly in the `/v1/scrape` request headers, which works because `/v1/scrape` is **synchronous** and processes the request directly.

### Authentication Setup

1. **Capture Cookies** using the authentication tool:
   ```powershell
   python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page
   ```

2. **Cookies are saved** to:
   - `.auth/storage_state.json` - Playwright format
   - `deploy/.env` - `FIRECRAWL_AUTH_STORAGE_STATE` env var

3. **Crawler uses cookies** in two ways:
   - FireCrawl: Cookie header in `/v1/scrape` requests
   - Playwright: `storage_state` for browser context

### Request Flow (Authenticated)

```
Seed URL (authenticated site)
    │
    ▼
┌─────────────────────────────────────────┐
│ FireCrawl /v1/scrape                    │
│ Headers: { Cookie: "session=xyz;..." }  │
└─────────────────────────────────────────┘
    │
    ▼ (if fails)
┌─────────────────────────────────────────┐
│ Playwright with storage_state           │
│ (Full browser session with cookies)     │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────┐
│ Trafilatura     │ ──→ Extract clean markdown
└─────────────────┘
```

### Configuration

```bash
# .env
FIRECRAWL_AUTH_TYPE=cookies
FIRECRAWL_AUTH_STORAGE_STATE={"cookies":[{"name":"AppServiceAuthSession","value":"...","domain":".osgwiki.com",...}]}
# Or use file path:
STORAGE_STATE_PATH=/path/to/.auth/storage_state.json
```

### Login Page Filtering

The crawler automatically filters out pages that return login prompts:
- Checks page title for "sign in", "login", "authenticate"
- Checks content for login form indicators
- Logs warning and skips the page

---

## Depth Crawling

For crawling multiple pages starting from seed URLs.

### Why Not Use FireCrawl's Native `/v1/crawl`?

FireCrawl's `/v1/crawl` endpoint supports depth crawling but has limitations:
- ❌ Async workers don't receive Cookie headers
- ❌ Link discovery fails on authenticated sites
- ❌ `/v1/batch/scrape` has the same worker isolation issue

### Our Hybrid Approach

We implemented a custom depth crawling strategy:

1. **Depth 1**: FireCrawl `/v1/scrape` fetches seed URLs (with auth)
2. **Link Extraction**: Parse markdown for same-domain links
3. **Depth 2+**: FireCrawl `/v1/scrape` fetches discovered links (parallel)

### Request Flow (Depth Crawling)

```
Seed URLs + depth=2
    │
    ▼
┌─────────────────────────────────────────┐
│ DEPTH 1: FireCrawl /v1/scrape           │
│ Scrape seed URLs with Cookie auth       │
│ Mark as crawl_depth=1                   │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ LINK EXTRACTION                         │
│ Parse markdown for [text](url) links    │
│ Filter: same-domain, no anchors,        │
│         no duplicates, no seed URLs     │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ DEPTH 2: FireCrawl /v1/scrape           │
│ Scrape discovered links (parallel)      │
│ Filter out login pages                  │
│ Mark as crawl_depth=2                   │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ FALLBACK: Playwright (if FireCrawl      │
│ fails for any URL)                      │
└─────────────────────────────────────────┘
```

### Example: Depth 2 Crawl

Request:
```json
{
  "query": "MBS manifest",
  "seed_urls": ["https://www.osgwiki.com/wiki/Modular_Build_System_(MBS)_project"],
  "depth": 2,
  "max_results": 10
}
```

Result:
```
Depth 1: Scraped 1 seed URL (MBS wiki page)
Link Extraction: Found 111 links, 102 unique same-domain
Depth 2: Scraped 9 discovered links
Total: 10 documents in 30.6 seconds
```

### Link Filtering Logic

When extracting links for depth crawling:

1. **Parse markdown** for `[text](url)` patterns and raw URLs
2. **Same-domain filter**: Only follow links to seed URL domains
3. **Normalize URLs**: Remove fragments/anchors (`#section`)
4. **Deduplicate**: Skip already-seen base URLs
5. **Limit**: Respect `max_results - current_docs`

---

## Fallback Strategy

The crawler has a multi-tier fallback system:

```
┌─────────────────────────────────────────┐
│ Tier 1: FireCrawl /v1/scrape            │
│ Fast, scalable, handles JavaScript      │
└────────────────┬────────────────────────┘
                 │ fails
                 ▼
┌─────────────────────────────────────────┐
│ Tier 2: Playwright Direct               │
│ Full browser, storage_state auth        │
│ + Trafilatura extraction                │
└────────────────┬────────────────────────┘
                 │ fails
                 ▼
┌─────────────────────────────────────────┐
│ Tier 3: Skip URL                        │
│ Log error, continue with other URLs     │
└─────────────────────────────────────────┘
```

### When Fallback Triggers

- FireCrawl HTTP error (5xx, timeout)
- FireCrawl returns empty content
- Network/DNS resolution failure
- Rate limiting

---

## Limitations

### Why Some Sites Return Minimal Content

When crawling major news websites like CNN, New York Times, Wall Street Journal, etc., you may encounter:
- Very short snippets (just page titles)
- Missing article content
- Only UI elements extracted ("Close icon", navigation text)
- Empty or truncated responses

### Root Causes

#### 1. JavaScript-Heavy Sites
Modern news websites render content dynamically with JavaScript:
- Initial HTML contains minimal content
- Articles load via JavaScript after page load
- FireCrawl and traditional scrapers see the "empty shell"

#### 2. Anti-Scraping Measures
Major news outlets implement:
- Bot detection (Cloudflare, DataDome, PerimeterX)
- Rate limiting
- CAPTCHA challenges
- IP-based blocking
- User-agent filtering

#### 3. Paywalls
Many news sites require:
- Subscriptions (NYT, WSJ, FT)
- Registration
- Cookie consent
- Geographic restrictions

#### 4. Content Protection
Sites may use:
- Shadow DOM (hidden content)
- Canvas fingerprinting
- Browser fingerprinting
- Dynamic class names

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
- Internal wikis (with proper auth)

⚠️ **Partial Success:**
- News aggregators (limited content)
- RSS feeds (summaries only)
- Social media (public posts)

❌ **Often Fails:**
- Paywalled news (NYT, WSJ, FT)
- JavaScript-heavy news sites (CNN, MSNBC)
- Sites with aggressive anti-bot measures
- Video/streaming platforms
- Sites requiring interactive login

---

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

Try with seed_urls:
```json
{
  "message": "What's in this article?",
  "force_refresh": true,
  "seed_urls": ["https://www.cnn.com/2025/11/15/specific-article/index.html"]
}
```

### 3. Use Scraping-Friendly Sources

News sources that work better:
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

---

## Configuration Reference

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FIRECRAWL_URL` | FireCrawl service URL | `http://firecrawl:3002` |
| `FIRECRAWL_AUTH_TYPE` | Auth type: `none` or `cookies` | `none` |
| `FIRECRAWL_AUTH_STORAGE_STATE` | JSON with cookies | (empty) |
| `STORAGE_STATE_PATH` | Path to storage_state.json | (empty) |
| `REQUEST_TIMEOUT_MS` | Request timeout in ms | `20000` |
| `MAX_CONCURRENCY` | Parallel scrape limit | `4` |
| `RESPECT_ROBOTS` | Honor robots.txt | `true` |
| `ALLOWED_DOMAINS` | Comma-separated allowed domains | (empty) |

### Crawl Request Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `query` | Search query or topic | (required) |
| `seed_urls` | Starting URLs to crawl | `[]` |
| `depth` | Crawl depth (1=seed only) | `1` |
| `max_results` | Maximum documents | `10` |
| `freshness_days` | Content age limit | `7` |
| `allow_web_search` | Enable FireCrawl search | `true` |

---

## Troubleshooting

### Check Crawler Logs

```powershell
# See crawl activity
docker logs web-rag-crawler-dev 2>&1 | Select-String "FireCrawl|Playwright|depth"

# See authentication
docker logs web-rag-crawler-dev 2>&1 | Select-String "cookie|auth"

# See failures
docker logs web-rag-crawler-dev 2>&1 | Select-String "ERROR|failed|Skipping"
```

### Common Issues

| Symptom | Cause | Solution |
|---------|-------|----------|
| "Sign in" pages returned | Cookies expired | Re-run `authenticate.py` |
| "Name or service not known" | Network issue | Check container network |
| Empty content | JavaScript not rendered | FireCrawl will retry with Playwright |
| Login pages not filtered | New login page pattern | Update filter in `firecrawl.py` |
| Minimal content from news | Anti-scraping/paywall | Use alternative sources |

### Verify Authentication

```powershell
# Quick test
curl -X POST http://localhost:8001/crawl `
  -H "Content-Type: application/json" `
  -d '{"query":"test","seed_urls":["https://www.osgwiki.com/wiki/Main_Page"],"depth":1}'
```

Check response for actual wiki content (not "Sign in to your account").

### Inspect Retrieved Content

Look at the `sources` in responses:
- **Good**: Long snippets, published dates, meaningful titles
- **Bad**: Short snippets like "Close icon", missing dates, generic titles

---

## Best Practices

### ✅ Do's

1. **Target specific article URLs** when possible
2. **Use company IR pages** for earnings/financial data
3. **Try multiple sources** for the same topic
4. **Use RSS feeds** for news aggregation
5. **Be specific** in your queries (include company names, dates)
6. **Check robots.txt** before adding new domains
7. **Monitor crawler logs** to see what's working
8. **Use depth=2** for exploring internal wikis

### ❌ Don'ts

1. **Don't scrape paywalled content** without subscription
2. **Don't ignore robots.txt** in production
3. **Don't hammer sites** with high request rates
4. **Don't expect video transcripts** (not supported)
5. **Don't rely on social media** for primary sources
6. **Don't use for time-critical breaking news** (delays inherent)

---

## Architecture Decisions

### Why FireCrawl for All Scraping?

1. **Performance**: FireCrawl is optimized for concurrent scraping
2. **JavaScript**: Built-in Playwright for dynamic content
3. **Consistency**: Single code path for auth headers
4. **Fallback**: Our Playwright is only for edge cases

### Why Not FireCrawl `/v1/crawl` for Depth?

FireCrawl's native crawl has worker isolation:
- Main API receives Cookie header
- But async workers (BullMQ jobs) don't
- Workers fail auth on protected sites

Our approach sends auth with **every** `/v1/scrape` call.

### Why Not `/v1/batch/scrape`?

Same issue - batch jobs are async:
- API queues URLs to workers
- Workers process independently
- Cookie headers don't propagate

We use parallel `/v1/scrape` calls instead.

---

## See Also

- [AUTHENTICATION.md](AUTHENTICATION.md) - Setting up cookie authentication
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture overview
- [CONFIGURATION.md](CONFIGURATION.md) - Full configuration reference

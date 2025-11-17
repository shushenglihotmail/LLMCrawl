# Authentication Setup for Internal Sites

This guide explains how to set up authentication for crawling internal Microsoft sites like osgwiki.com that use Azure App Service Easy Auth.

## Overview

The authentication process has two methods:
1. **Automated capture** - Works for most sites
2. **Manual cookie addition** - Required for Azure App Service Easy Auth sites (like osgwiki.com)

## Method 1: Automated Capture (Standard Sites)

For most sites with OAuth/SSO authentication:

```powershell
cd C:\src\github\LLMCrawl
.\venv\Scripts\python.exe tools\msauth\interactive_auth.py https://internal-site.com --name mysite
```

This will:
1. Open Microsoft Edge browser
2. Wait for you to complete login
3. Automatically capture all authentication cookies
4. Save to `.auth\mysite.json`

## Method 2: Manual Cookie Addition (Azure App Service Easy Auth)

For sites like www.osgwiki.com where automated capture doesn't work:

### Step 1: Run Initial Auth Capture

```powershell
cd C:\src\github\LLMCrawl
.\venv\Scripts\python.exe tools\msauth\interactive_auth.py https://www.osgwiki.com/wiki/Main_Page --name www_osgwiki_com --timeout 300
```

This will capture most cookies but **NOT** the `AppServiceAuthSession` cookie.

### Step 2: Get AppServiceAuthSession Cookie from Browser

1. **Keep the browser open** after completing login and seeing the wiki content
2. Press `F12` to open Developer Tools
3. Go to the **Network** tab
4. Click on any request to `www.osgwiki.com` in the list (or refresh the page to see requests)
5. In the right panel, find the **Cookies** section (may need to scroll down)
6. Look in the **Request Cookies** for `AppServiceAuthSession`
7. **Copy the entire Value** (it's a long string starting with something like `eyJ0eX...`)

**Alternative method (Application tab):**
- Go to **Application** tab (or **Storage** in Firefox)
- Expand **Cookies** in the left sidebar
- Click on `https://www.osgwiki.com`
- Find `AppServiceAuthSession` and copy the Value

### Step 3: Add Cookie Using Helper Script

```powershell
cd C:\src\github\LLMCrawl
.\tools\msauth\scripts\add_cookie_manual.ps1 -ProfileName www_osgwiki_com -CookieValue "PASTE_COOKIE_VALUE_HERE"
```

Replace `PASTE_COOKIE_VALUE_HERE` with the cookie value you copied.

**Example:**
```powershell
.\tools\msauth\scripts\add_cookie_manual.ps1 -ProfileName www_osgwiki_com -CookieValue "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6Ij..."
```

### Step 4: Apply to Environment

```powershell
.\venv\Scripts\python.exe tools\msauth\interactive_auth.py --apply www_osgwiki_com
```

### Step 5: Restart Crawler

```powershell
docker-compose restart crawler
```

### Step 6: Verify It Works

Test with curl:
```powershell
$body = @{query='test'; seed_urls=@('https://www.osgwiki.com/wiki/Main_Page'); depth=1} | ConvertTo-Json
curl -X POST http://localhost:8001/crawl -H 'Content-Type: application/json' -d $body
```

Or test with HiChat webclient:
```powershell
cd C:\src\github\HiChat
.\bin\hichat-webclient.exe --port 3005
```

Then open http://localhost:3005 and use the Crawl Settings:
- Seed URLs: `https://www.osgwiki.com/wiki/Main_Page`
- Crawl Depth: `3`

## Why Manual Cookie Addition is Needed

Azure App Service Easy Auth sets the `AppServiceAuthSession` cookie with special attributes that prevent Playwright's Chrome DevTools Protocol (CDP) from capturing it:

- Cookie may be partitioned by top-level site
- Browser security features isolate certain cookies from automation tools
- The cookie is only visible in the browser's main cookie store, not in Playwright's context

This is a security feature, not a bug. The manual workaround is the recommended approach for these specific authentication flows.

## Cookie Expiration

The `AppServiceAuthSession` cookie typically expires after 24 hours. When it expires:

1. You'll see 401 Unauthorized errors in crawler logs
2. Repeat the manual cookie capture process (Steps 2-5 above)
3. No need to restart all services, just the crawler

## Troubleshooting

### Cookie Not Found in Browser DevTools

**Using Network Tab (Recommended):**
- Make sure you're logged in and can see the wiki content
- F12 > Network tab
- Refresh the page to capture requests
- Click on any request to www.osgwiki.com
- Look in the Cookies section (Request Cookies)
- The cookie should be there

**Using Application Tab:**
- F12 > Application tab > Cookies > www.osgwiki.com
- The cookie might be under `.osgwiki.com` instead
- Try both domains

### Crawler Still Getting 401 Errors

```powershell
# Check if cookie is in auth file
$auth = Get-Content .auth\www_osgwiki_com.json | ConvertFrom-Json
$auth.cookies | Where-Object { $_.name -eq "AppServiceAuthSession" } | Format-List

# Check if cookie is in .env
Get-Content .env | Select-String -Pattern "FIRECRAWL_AUTH"

# Check crawler logs
docker logs web-rag-crawler-dev --tail 100
```

### Cookie Expired

Run the manual process again to get a fresh cookie value.

## Quick Reference

```powershell
# Complete setup for osgwiki
cd C:\src\github\LLMCrawl

# 1. Initial auth capture
.\venv\Scripts\python.exe tools\msauth\interactive_auth.py https://www.osgwiki.com/wiki/Main_Page --name www_osgwiki_com --timeout 300

# 2. Get cookie from browser F12 > Application > Cookies > www.osgwiki.com > AppServiceAuthSession

# 3. Add cookie manually
.\tools\msauth\scripts\add_cookie_manual.ps1 -ProfileName www_osgwiki_com -CookieValue "YOUR_COOKIE_VALUE"

# 4. Apply and restart
.\venv\Scripts\python.exe tools\msauth\interactive_auth.py --apply www_osgwiki_com
docker-compose restart crawler

# 5. Test
$body = @{query='test'; seed_urls=@('https://www.osgwiki.com/wiki/Main_Page'); depth=1} | ConvertTo-Json
curl -X POST http://localhost:8001/crawl -H 'Content-Type: application/json' -d $body
```

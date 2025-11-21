# Authentication Setup for Internal Sites

This guide explains how to set up authentication for crawling internal Microsoft sites like osgwiki.com that use Azure App Service Easy Auth.

## 🚀 Quick Start - Manual Auth Procedure

**For Azure App Service Easy Auth sites (like osgwiki.com):**

### Step 1: Run Interactive Auth Script
Opens browser for you to sign in manually:
```powershell
.\venv\Scripts\python.exe tools\msauth\interactive_auth.py https://www.osgwiki.com/wiki/Main_Page
```
**What happens:**
- Browser opens → You sign in with Microsoft account
- Press Enter when logged in
- Captures login cookies (but NOT AppServiceAuthSession for Easy Auth sites)

### Step 2: Run Apply Cookie Script
Manually copy the AppServiceAuthSession cookie:
```powershell
.\tools\msauth\scripts\add_cookie_manual.ps1
```
**What happens:**
- Script prompts you to open browser DevTools (F12)
- Navigate to the site → Application → Cookies
- Copy `AppServiceAuthSession` cookie value
- Paste when prompted
- **Script automatically applies to `.env` and recreates crawler** ✅

### Step 3: Verify Auth Works (Optional)
```powershell
.\scripts\check-auth-status.ps1 https://www.osgwiki.com/wiki/Main_Page
```
**What happens:**
- Tests if crawler can access the site
- Shows success/failure with details

---

## ⚠️ Important Notes

**Why two steps?**
- Azure App Service Easy Auth sets `AppServiceAuthSession` cookie ONLY after you access the protected page
- Interactive auth captures login cookies but can't capture this cookie automatically
- You must manually copy it from the browser after successful login

**The `add_cookie_manual.ps1` script is fully automated** - it handles:
- ✅ Adding cookie to `.auth` file
- ✅ Applying to `.env`
- ✅ Force-recreating crawler to reload environment
- ✅ Running authentication test

You only need to copy/paste the cookie value!

---

## Overview

The authentication process has two methods:
1. **Automated capture** - Works for most sites
2. **Manual cookie addition** - Required for Azure App Service Easy Auth sites (like osgwiki.com)

Azure App Service Easy Auth requires a two-step process because the `AppServiceAuthSession` cookie is only set after successfully accessing the protected site.

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

For sites like www.osgwiki.com where automated capture doesn't fully work:

### Quick Method (Interactive)

```powershell
# Run the interactive script
.\tools\msauth\scripts\add_cookie_manual.ps1
```

This will:
1. Show available auth profiles
2. Guide you to get the cookie from browser
3. Automatically apply to `.env`
4. Prompt you to restart crawler
5. Run authentication test

### Step-by-Step Method

If you prefer to understand each step:

### Step 1: Run Initial Auth Capture

```powershell
.\venv\Scripts\python.exe tools\msauth\interactive_auth.py https://www.osgwiki.com/wiki/Main_Page
```

This captures login cookies but **NOT** the `AppServiceAuthSession` cookie (set only after accessing the site).

### Step 2: Get AppServiceAuthSession Cookie from Browser

**IMPORTANT: Do this quickly - the cookie expires fast!**

1. **Navigate to** https://www.osgwiki.com/wiki/Main_Page in your browser
2. **Verify** you can see the wiki content (not a login page)
3. Press `F12` to open Developer Tools
4. Go to **Application** tab → **Cookies** → `https://www.osgwiki.com`
5. Find `AppServiceAuthSession` cookie
6. **Double-click** the Value column and copy (Ctrl+C)
7. **Immediately** proceed to Step 3

**Alternative (Network tab):**
- Go to **Network** tab
- Refresh the page
- Click any request to `www.osgwiki.com`
- Find **Request Cookies** section
- Copy `AppServiceAuthSession` value

### Step 3: Add Cookie Interactively

```powershell
.\tools\msauth\scripts\add_cookie_manual.ps1
```

- Select profile #1 (www_osgwiki_com)
- Paste the cookie value when prompted
- Press Enter to restart crawler
- Press Enter to test authentication

**Or specify directly:**
```powershell
.\tools\msauth\scripts\add_cookie_manual.ps1 www_osgwiki_com "YOUR_COOKIE_VALUE"
```

The script automatically:
- ✅ Adds cookie to both required locations
- ✅ Applies to `.env` file
- ✅ Prompts to restart crawler
- ✅ Runs authentication test

### Verification

Test authentication with the diagnostic script:

```powershell
.\scripts\check-auth-status.ps1 https://www.osgwiki.com/wiki/Main_Page
```

This will:
- ✅ Check auth file age
- ✅ Test actual crawling
- ✅ Show detailed error messages if auth fails
- ✅ Provide next-step commands

**Expected output:**
```
✓ Auth working - content retrieved
Title: Main Page
Content length: 482 chars
Source: playwright+trafilatura
```

### Troubleshooting

**Still getting 401 errors?**

1. **Cookie expired** - Azure App Service cookies expire quickly (10-30 minutes)
   ```powershell
   # Get fresh cookie and re-run
   .\tools\msauth\scripts\add_cookie_manual.ps1
   ```

2. **Crawler not reloading .env** - Need to recreate container, not just restart
   ```powershell
   docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d crawler
   ```

3. **Check what crawler sees:**
   ```powershell
   docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs --tail=20 crawler | Select-String "storage_state|401"
   ```

4. **Wrong cookie count** - Should match your `.auth` file
   - Look for "configured with storage_state authentication (XX cookies)"
   - If count is wrong, recreate container (step 2)

### Cookie Refresh Schedule

Azure App Service cookies expire frequently. Set up regular refresh:

**Option 1: Manual Refresh When Needed**
```powershell
# Check status daily or when crawls fail
.\scripts\check-auth-status.ps1 https://www.osgwiki.com/wiki/Main_Page

# If expired, refresh
.\tools\msauth\scripts\add_cookie_manual.ps1
```

**Option 2: Automated Refresh (Future)**
See `tools\msauth\scripts\schedule_refresh.ps1` for scheduled refresh setup.

---

## Testing After Setup

### Quick Test with curl:
```powershell
$body = @{
    query='test'
    seed_urls=@('https://www.osgwiki.com/wiki/Main_Page')
    max_results=1
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8001/crawl -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json
```

### Test with HiChat Webclient:
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

# 4. Apply and recreate crawler (to reload .env)
.\venv\Scripts\python.exe tools\msauth\interactive_auth.py --apply www_osgwiki_com
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler

# 5. Test
$body = @{query='test'; seed_urls=@('https://www.osgwiki.com/wiki/Main_Page'); depth=1} | ConvertTo-Json
curl -X POST http://localhost:8001/crawl -H 'Content-Type: application/json' -d $body
```

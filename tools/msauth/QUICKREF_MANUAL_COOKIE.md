# Quick Reference: Manual Cookie Addition for OSGWiki

When automated cookie capture doesn't work (Azure App Service Easy Auth sites), follow these steps:

## ⚡ Quick Steps

```powershell
# 1. Initial auth capture (captures most cookies except AppServiceAuthSession)
cd C:\src\github\LLMCrawl
.\venv\Scripts\python.exe tools\msauth\interactive_auth.py https://www.osgwiki.com/wiki/Main_Page --name www_osgwiki_com --timeout 300
```

**Browser Actions:**
- Complete Microsoft login
- Wait for wiki content to load
- Press `F12` → Network tab → Click any www.osgwiki.com request → Cookies section
- Find `AppServiceAuthSession` → Copy the Value
- (Or use Application tab → Cookies → www.osgwiki.com)

```powershell
# 2. Add the missing cookie
.\tools\msauth\scripts\add_cookie_manual.ps1 -ProfileName www_osgwiki_com -CookieValue "PASTE_VALUE_HERE"

# 3. Apply and restart
.\venv\Scripts\python.exe tools\msauth\interactive_auth.py --apply www_osgwiki_com
docker-compose restart crawler
```

## 🧪 Test It Works

```powershell
# Test crawler directly
$body = @{query='test'; seed_urls=@('https://www.osgwiki.com/wiki/Main_Page'); depth=1} | ConvertTo-Json
curl -X POST http://localhost:8001/crawl -H 'Content-Type: application/json' -d $body

# Test via HiChat webclient
cd C:\src\github\HiChat
.\bin\hichat-webclient.exe --port 3005
# Open http://localhost:3005
# Set Seed URLs: https://www.osgwiki.com/wiki/Main_Page
# Set Depth: 3
# Ask: "how to enlist OS repo"
```

## 🔄 Cookie Refresh (Daily)

When the cookie expires (typically after 24 hours):

```powershell
# Get fresh cookie from browser (F12 > Application > Cookies)
.\tools\msauth\scripts\add_cookie_manual.ps1 -ProfileName www_osgwiki_com -CookieValue "NEW_COOKIE_VALUE"
.\venv\Scripts\python.exe tools\msauth\interactive_auth.py --apply www_osgwiki_com
docker-compose restart crawler
```

## 📖 Full Documentation

See [`docs/AUTHENTICATION_SETUP.md`](../AUTHENTICATION_SETUP.md) for detailed explanation and troubleshooting.

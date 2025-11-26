# Authentication for Internal Sites

This guide explains how to set up authentication for crawling internal Microsoft sites like osgwiki.com that use Azure App Service Easy Auth or similar cookie-based authentication.

## ⚠️ Security Warning

**Authentication files contain sensitive credentials - NEVER commit them to git!**

- `.auth/` directory is excluded in `.gitignore`
- Files are **temporary** and expire (typically 8-24 hours)
- Contains your username and session cookies
- Always verify with `git status` before committing

---

## 🚀 Quick Start (One Command)

For sites like **www.osgwiki.com** that use Azure App Service Easy Auth:

```powershell
# Activate virtual environment first
cd C:\src\github\LLMCrawl
.\venv\Scripts\Activate.ps1

# Run the authentication tool
python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page
```

**What happens:**
1. ✅ Edge browser opens with debugging enabled
2. ⏸️ You sign in with Microsoft credentials (complete MFA if prompted)
3. ⏸️ Press ENTER when you see the authenticated content
4. ✅ Cookies are extracted automatically
5. ✅ Credentials saved to `.auth/` directory
6. ✅ Applied to `deploy/.env` file
7. ✅ Crawler container recreated
8. ✅ Authentication tested

**That's it!** The crawler is now authenticated and ready to use.

---

## How It Works

The authentication tool uses **Edge Remote Debugging** to capture cookies:

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Launch Edge with --remote-debugging-port=9222               │
│     (Uses temp profile to avoid conflicts)                      │
├─────────────────────────────────────────────────────────────────┤
│  2. You authenticate in the browser                             │
│     (Microsoft SSO, MFA, etc.)                                  │
├─────────────────────────────────────────────────────────────────┤
│  3. Connect via Chrome DevTools Protocol (CDP)                  │
│     (Bypasses cookie encryption - Edge decrypts for us)         │
├─────────────────────────────────────────────────────────────────┤
│  4. Extract cookies including AppServiceAuthSession             │
│     (Captures HttpOnly cookies that Playwright can't see)       │
├─────────────────────────────────────────────────────────────────┤
│  5. Save to .auth/ and apply to .env                            │
│     (Automatic - no manual copying needed)                      │
├─────────────────────────────────────────────────────────────────┤
│  6. Recreate crawler container & test                           │
│     (Verifies everything works)                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Why this works better than other methods:**
- **Bypasses cookie encryption** - We ask Edge for cookies via CDP, not reading from disk
- **No profile conflicts** - Uses temp profile directory
- **Captures ALL cookies** - Including HttpOnly cookies like `AppServiceAuthSession`
- **Fully automated** - No manual copy/paste required

---

## Command Options

```powershell
# Basic usage
python tools/msauth/authenticate.py <URL>

# Options
python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page \
    --name my_wiki           # Custom profile name
    --no-apply               # Don't apply to .env (just save cookies)
    --no-restart             # Don't restart crawler container
    --no-test                # Don't test authentication
    --port 9223              # Use different debug port
```

### Examples

```powershell
# Standard authentication (recommended)
python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page

# Save cookies only (don't modify .env or restart)
python tools/msauth/authenticate.py https://www.osgwiki.com --no-apply --no-restart

# Custom profile name
python tools/msauth/authenticate.py https://internal-wiki.com --name internal_wiki

# Different target cookie (for non-Azure sites)
python tools/msauth/authenticate.py https://other-site.com --cookie SESSION_ID
```

---

## Troubleshooting

### "Edge not found"
Ensure Microsoft Edge is installed. The script looks for:
- `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`
- `C:\Program Files\Microsoft\Edge\Application\msedge.exe`

### "Connection refused" when extracting cookies
- Make sure no other Edge instances are running
- Close Edge completely (check Task Manager)
- Re-run the authentication script

### "Cookie not found"
- Ensure you're fully logged in (can see the site content, not a login page)
- Wait a few seconds after the page loads before pressing ENTER
- Try refreshing the page in Edge to ensure cookies are set

### "Authentication test failed"
- Crawler might not be running: `cd deploy && docker-compose up -d crawler`
- Wait a few more seconds for crawler to initialize
- Check crawler logs: `docker-compose logs --tail=20 crawler`

### Cookie expires quickly
Azure App Service cookies expire in 8-24 hours. Just re-run the authentication:
```powershell
python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page
```

### "Profile switching" issues
The tool uses a temp profile (`C:\Temp\EdgeDebugProfile`) to avoid this. If you still see issues:
```powershell
# Delete the temp profile and try again
Remove-Item -Recurse C:\Temp\EdgeDebugProfile
python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page
```

---

## Manual Verification

If you want to verify the authentication manually:

### Check saved credentials
```powershell
# View the auth file
Get-Content .auth\www_osgwiki_com.json | ConvertFrom-Json | Select-Object profile_name, created_at
```

### Check .env was updated
```powershell
# Verify FIRECRAWL_AUTH_STORAGE_STATE is set
Get-Content deploy\.env | Select-String "FIRECRAWL_AUTH"
```

### Check crawler loaded cookies
```powershell
# View crawler logs
cd deploy
docker-compose logs --tail=10 crawler | Select-String "cookies"
# Should show: "configured with storage_state authentication (X cookies)"
```

### Test crawling manually
```powershell
$body = @{
    query = 'test'
    seed_urls = @('https://www.osgwiki.com/wiki/Main_Page')
    max_results = 1
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8001/crawl -Method Post -ContentType 'application/json' -Body $body
```

---

## File Locations

| File | Purpose |
|------|---------|
| `tools/msauth/authenticate.py` | Main authentication script |
| `.auth/<name>.json` | Saved credentials (gitignored) |
| `deploy/.env` | Environment config with `FIRECRAWL_AUTH_STORAGE_STATE` |

---

## Re-Authentication

When cookies expire (typically 8-24 hours), simply re-run:

```powershell
python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page
```

The script will:
1. Open Edge for you to sign in again
2. Extract fresh cookies
3. Update `.env`
4. Restart crawler
5. Test that it works

---

## Other Authentication Types

For sites that don't use Azure App Service Easy Auth:

### Bearer Token
```bash
# In deploy/.env
FIRECRAWL_AUTH_TYPE=bearer
FIRECRAWL_AUTH_TOKEN=your-token-here
```

### Basic Auth
```bash
# In deploy/.env
FIRECRAWL_AUTH_TYPE=basic
FIRECRAWL_AUTH_USERNAME=user
FIRECRAWL_AUTH_PASSWORD=pass
```

### Azure AD OAuth (Programmatic)
For fully automated scenarios:
```bash
# In deploy/.env
FIRECRAWL_AUTH_TYPE=azure_ad
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
AZURE_SCOPE=https://graph.microsoft.com/.default
```

---

## Architecture

### Cookie Flow

```
User Browser (Edge with debugging)
         │
         ▼
authenticate.py (extracts via CDP)
         │
         ▼
.auth/site_name.json (saved credentials)
         │
         ▼
deploy/.env (FIRECRAWL_AUTH_STORAGE_STATE)
         │
         ▼
Crawler Container (uses cookies for requests)
         │
         ▼
Internal Site (www.osgwiki.com)
```

### Supported Sites

This authentication method works for:
- ✅ Azure App Service Easy Auth
- ✅ Microsoft Azure AD / Entra ID SSO
- ✅ Sites with Conditional Access policies
- ✅ Multi-factor authentication (MFA)
- ✅ Any cookie-based authentication

---

## Requirements

- **Microsoft Edge** browser installed
- **Python 3.8+** with virtual environment
- **Playwright** package (`pip install playwright`)
- **Docker** for crawler container
- **Managed/compliant device** (for conditional access sites)

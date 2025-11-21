# Authentication Quick Start

Choose your authentication method based on your needs:

## 🎯 Quick Decision Guide

| Your Situation | Use This Method |
|----------------|-----------------|
| **SSO / MFA / Complex Login** | [Interactive Browser Auth](#1-interactive-browser-auth-easiest) |
| **SharePoint / Azure AD** | [Interactive Browser](#1-interactive-browser-auth-easiest) or [Azure AD OAuth](#2-azure-ad-oauth-programmatic) |
| **API Token / Key** | [Bearer Token](#3-bearer-token-simple) |
| **Basic Username/Password** | [Basic Auth](#4-basic-authentication-legacy) |
| **Custom Headers** | [Header Auth](#5-header-authentication-custom) |

---

## 1. Interactive Browser Auth (Easiest)

**Best for:** Any site with SSO, MFA, or complex login flows (including Azure App Service Easy Auth)

### For Azure App Service Easy Auth (e.g., osgwiki.com):

**3-Step Procedure:**

```powershell
# Step 1: Capture login cookies (opens browser for you to sign in)
.\venv\Scripts\python.exe tools\msauth\interactive_auth.py https://www.osgwiki.com/wiki/Main_Page

# Step 2: Add AppServiceAuthSession manually (fully automated after you paste)
.\tools\msauth\scripts\add_cookie_manual.ps1

# Step 3: (Optional) Verify auth works
.\scripts\check-auth-status.ps1 https://www.osgwiki.com/wiki/Main_Page
```

**What happens:**
- **Step 1**: Browser opens → You sign in → Captures login cookies (but NOT AppServiceAuthSession)
- **Step 2**: You copy AppServiceAuthSession from browser DevTools → Script **automatically** applies to `.env`, force-recreates crawler, and tests auth
- **Step 3**: Optional verification that crawler can access the site

**Why manual cookie needed?** Azure App Service Easy Auth sets `AppServiceAuthSession` AFTER you access the page, so interactive_auth.py cannot capture it automatically.

### For standard OAuth/SSO sites:

```powershell
# Step 1: Capture auth via browser
.\venv\Scripts\python.exe tools\msauth\interactive_auth.py https://internal-site.com

# Step 2: Recreate crawler (to reload .env with new cookies)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler

# Step 3: Verify
.\scripts\check-auth-status.ps1 https://internal-site.com
```

**Advantages:**
- ✅ Works with ANY authentication system
- ✅ Handles MFA automatically
- ✅ Interactive prompts guide you
- ✅ Automatic validation
- ✅ No manual configuration
- ✅ Real browser = real authentication

**When to use:**
- Microsoft 365 / SharePoint
- Azure App Service Easy Auth
- Okta / Auth0 SSO
- Multi-factor authentication
- SAML / OAuth flows
- Don't know auth details

---

## 2. Azure AD OAuth (Programmatic)

**Best for:** Automated/scheduled crawls of Azure AD protected resources

### Step 1: Choose Your Authentication Method

### Setup

1. Register app in Azure AD portal
2. Grant permissions (Sites.Read.All, Files.Read.All)
3. Create client secret
4. Add to `.env`:

```bash
FIRECRAWL_AUTH_TYPE=azure_ad
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
AZURE_SCOPE=https://graph.microsoft.com/.default
```

5. Recreate crawler: `docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler`

**Advantages:**
- ✅ Fully automated (no human intervention)
- ✅ Tokens auto-refresh
- ✅ Best for scheduled jobs
- ✅ Audit trail in Azure AD

**When to use:**
- Scheduled/automated crawls
- Service account scenarios
- Need audit logs
- SharePoint API access

📖 [Azure AD Setup Guide](AZURE_AD_SETUP.md) | [Detailed Guide](AZURE_AD_AUTH.md)

---

## 3. Bearer Token (Simple)

**Best for:** APIs with static bearer tokens

```bash
FIRECRAWL_AUTH_TYPE=bearer
FIRECRAWL_AUTH_BEARER_TOKEN=your-api-token-here
```

**When to use:**
- API keys from admin panel
- Long-lived access tokens
- Static credentials

---

## 4. Basic Authentication (Legacy)

**Best for:** Older systems with username/password

```bash
FIRECRAWL_AUTH_TYPE=basic
FIRECRAWL_AUTH_USERNAME=myuser
FIRECRAWL_AUTH_PASSWORD=mypassword
```

**When to use:**
- Legacy systems
- Internal tools
- Simple auth requirements

---

## 5. Header Authentication (Custom)

**Best for:** Custom authentication schemes

```bash
FIRECRAWL_AUTH_TYPE=headers
FIRECRAWL_AUTH_HEADERS={"X-API-Key": "abc123", "X-User-ID": "user@company.com"}
```

**When to use:**
- Custom headers required
- Non-standard auth
- Multiple headers needed

---

## 6. Cookie Authentication (Manual)

**Best for:** When you already have cookies from browser

```bash
FIRECRAWL_AUTH_TYPE=cookies
FIRECRAWL_AUTH_STORAGE_STATE={"cookies": [{"name": "sessionid", "value": "abc123", "domain": "example.com", "path": "/"}], "origins": []}
```

**When to use:**
- Extracted cookies manually from browser
- Testing specific sessions
- Short-term testing

**Note:** Use `interactive_auth.py` instead - it automates cookie capture in the correct format.

**Note:** Use [Interactive Auth](#1-interactive-browser-auth-easiest) instead - it captures cookies automatically!

---

## Comparison Table

| Method | Ease of Use | MFA Support | Auto Refresh | Best For |
|--------|-------------|-------------|--------------|----------|
| **Interactive Browser** | ⭐⭐⭐⭐⭐ Very Easy | ✅ Yes | ❌ No (re-login) | Any complex auth |
| **Azure AD OAuth** | ⭐⭐⭐ Moderate | ✅ Yes | ✅ Yes | Scheduled jobs |
| **Bearer Token** | ⭐⭐⭐⭐ Easy | ❌ No | ❌ No | API tokens |
| **Basic Auth** | ⭐⭐⭐⭐⭐ Very Easy | ❌ No | N/A | Legacy systems |
| **Headers** | ⭐⭐⭐ Moderate | ❌ No | ❌ No | Custom auth |
| **Cookies** | ⭐⭐ Hard | ❌ No | ❌ No | Manual testing |

---

## Real-World Examples

### SharePoint Online

**Option A: Interactive (Easiest)**
```powershell
.\scripts\auth.ps1 login https://company.sharepoint.com
.\scripts\auth.ps1 apply company_sharepoint_com
docker-compose restart crawler
```

**Option B: Azure AD (Automated)**
```bash
FIRECRAWL_AUTH_TYPE=azure_ad
AZURE_TENANT_ID=xxxxx
AZURE_CLIENT_ID=xxxxx
AZURE_CLIENT_SECRET=xxxxx
AZURE_SCOPE=https://graph.microsoft.com/.default
```

### Internal Wiki with SSO

**Use Interactive:**
```powershell
.\scripts\auth.ps1 login https://wiki.company.com
.\scripts\auth.ps1 apply wiki_company_com
docker-compose restart crawler
```

### REST API with Key

**Use Bearer:**
```bash
FIRECRAWL_AUTH_TYPE=bearer
FIRECRAWL_AUTH_BEARER_TOKEN=sk-abc123xyz789
```

### Legacy Intranet

**Use Basic:**
```bash
FIRECRAWL_AUTH_TYPE=basic
FIRECRAWL_AUTH_USERNAME=admin
FIRECRAWL_AUTH_PASSWORD=password123
```

---

## Testing Authentication

### Test Interactive Auth

```powershell
# After applying credentials
.\scripts\test-internal-auth.ps1 https://protected-site.com
```

### Test Azure AD

```powershell
.\scripts\test-azure-ad.ps1
```

### Check Logs

```powershell
# View auth status
docker-compose logs crawler | Select-String "auth"

# Check for failures
docker-compose logs crawler | Select-String "401|403"
```

---

## Common Issues

### ⚠️ Important: Why Use `--force-recreate` Instead of `restart`?

**TL;DR:** After updating `.env` with new cookies, you MUST use `--force-recreate` to reload environment variables.

**Why?**
- `docker-compose restart` = Restart container with OLD environment variables
- `docker-compose up -d --force-recreate` = Recreate container with NEW environment variables from `.env`

**Example:**
```powershell
# ❌ WRONG - Won't load new cookies from .env
docker-compose restart crawler

# ✅ CORRECT - Loads new cookies from .env
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler
```

**When to use each:**
- Use `restart`: When config hasn't changed (e.g., just restarting after crash)
- Use `up -d --force-recreate`: After updating `.env` file with new auth credentials

**The auth scripts now handle this automatically!** But if you manually edit `.env`, remember to use `--force-recreate`.

---

## Common Issues

### Authentication Fails

**Problem:** 401 or 403 errors

**Solutions:**
1. **Expired credentials** → Re-authenticate
   ```powershell
   .\scripts\auth.ps1 login https://site.com
   .\scripts\auth.ps1 apply site_com
   docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler
   ```

2. **Wrong auth type** → Check `.env` for `FIRECRAWL_AUTH_TYPE`

3. **Missing permissions** → Check Azure AD app permissions

### Interactive Auth Browser Doesn't Open

**Problem:** Playwright not installed

**Solution:**
```powershell
pip install playwright
playwright install chromium
```

### Azure AD Token Errors

**Problem:** "AADSTS" errors

**Solutions:**
- Check tenant ID, client ID, secret
- Verify app permissions in Azure portal
- Ensure admin consent granted
- See [Azure AD Troubleshooting](AZURE_AD_AUTH.md#troubleshooting)

### Credentials Expire Quickly

**Problem:** Need to re-auth frequently

**Solutions:**
- **Interactive:** Normal - re-auth when needed
- **Azure AD:** Should auto-refresh - check logs
- **Tokens:** Request longer-lived tokens from admin

---

## Migration Guide

### From Manual Cookies → Interactive Auth

**Before:**
```bash
# Manual cookie extraction
FIRECRAWL_AUTH_TYPE=cookies
FIRECRAWL_AUTH_COOKIES={"FedAuth": "...", "rtFa": "..."}
```

**After:**
```powershell
# Automatic capture
.\scripts\auth.ps1 login https://site.com
.\scripts\auth.ps1 apply site_com
```

### From Basic Auth → Azure AD

**Before:**
```bash
FIRECRAWL_AUTH_TYPE=basic
FIRECRAWL_AUTH_USERNAME=user@company.com
FIRECRAWL_AUTH_PASSWORD=password123
```

**After:**
```bash
FIRECRAWL_AUTH_TYPE=azure_ad
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-secret
AZURE_SCOPE=https://graph.microsoft.com/.default
```

---

## Security Best Practices

### ✅ Do's

1. **Use service accounts** for automated crawls
2. **Grant minimum permissions** in Azure AD
3. **Rotate secrets** regularly
4. **Monitor auth logs** for suspicious activity
5. **Use Interactive Auth** for testing (not production)
6. **Use Azure AD** for production (auto-refresh)

### ❌ Don'ts

1. **Don't commit** `.env` or `.auth/` files
2. **Don't share** credentials between environments
3. **Don't use personal accounts** for service access
4. **Don't hardcode** secrets in code
5. **Don't skip** MFA when available

---

## Quick Commands Reference

```powershell
# Interactive Authentication
.\scripts\auth.ps1 login <url>              # Authenticate
.\scripts\auth.ps1 apply <profile>          # Apply credentials
.\scripts\auth.ps1 list                     # List profiles
.\scripts\auth.ps1 delete <profile>         # Delete profile

# Testing
.\scripts\test-internal-auth.ps1 <url>      # Test auth
.\scripts\test-azure-ad.ps1                 # Test Azure AD

# Debugging
docker-compose logs crawler | Select-String "auth"
docker-compose logs crawler | Select-String "401|403"

# Recreate crawler (after updating .env)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler
```

---

## Next Steps

1. **Choose your method** from the guide above
2. **Follow the instructions** for your chosen method
3. **Test authentication** with test scripts
4. **Monitor logs** for issues

## Further Reading

- [Interactive Authentication Guide](INTERACTIVE_AUTH.md)
- [Azure AD Setup](AZURE_AD_SETUP.md)
- [Azure AD Detailed Guide](AZURE_AD_AUTH.md)
- [Main README](../README.md)

---

**Most users should start with Interactive Browser Auth** - it's the easiest and works with everything! 🚀


2. **Check JSON formatting:**
   ```bash
   # WRONG (missing quotes)
   FIRECRAWL_AUTH_HEADERS={X-API-Key: abc123}

   # RIGHT (proper JSON)
   FIRECRAWL_AUTH_HEADERS={"X-API-Key": "abc123"}
   ```

3. **Enable debug logging:**
   ```bash
   LOG_LEVEL=DEBUG
   ```

4. **Check logs:**
   ```powershell
   docker-compose logs crawler --tail 100
   ```

### Cookies expire quickly?

Get fresh cookies:
1. Clear browser cache
2. Login again
3. Copy new cookies immediately
4. Update `.env`
5. Restart: `docker-compose restart crawler`

### Need more help?

See full guide: `docs/AUTHENTICATION.md`

## Security Reminders

- ✅ Use environment variables (never commit credentials)
- ✅ Use read-only accounts when possible
- ✅ Rotate credentials regularly
- ✅ Monitor access logs
- ❌ Never commit `.env` file to git
- ❌ Don't use production admin accounts

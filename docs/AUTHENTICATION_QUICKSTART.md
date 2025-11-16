# Quick Start: Internal Site Authentication

## 5-Minute Setup Guide

### Step 1: Choose Your Authentication Method

Identify which method your internal site uses:

- **API Key/Custom Headers** → Use `headers` method
- **Session Cookies** → Use `cookies` method
- **Username/Password** → Use `basic` method
- **JWT/OAuth Token** → Use `bearer` method

### Step 2: Get Credentials

#### For Headers Method:
```bash
# Test with curl first
curl -H "X-API-Key: your-key" https://internal-site.com/api
```

#### For Cookies Method:
1. Login to site in browser
2. Open DevTools (F12) → Application → Cookies
3. Copy cookie values (session_id, auth_token, etc.)

#### For Basic Auth:
```bash
# Test with curl
curl -u username:password https://internal-site.com
```

#### For Bearer Token:
```bash
# Test with curl
curl -H "Authorization: Bearer your-token" https://internal-site.com
```

### Step 3: Update `.env` File

Edit `c:\src\github\LLMCrawl\.env`:

#### Example 1: API Key Authentication
```bash
FIRECRAWL_AUTH_TYPE=headers
FIRECRAWL_AUTH_HEADERS={"X-API-Key": "abc123xyz"}
```

#### Example 2: Session Cookies
```bash
FIRECRAWL_AUTH_TYPE=cookies
FIRECRAWL_AUTH_COOKIES={"session_id": "abc123", "csrf_token": "xyz789"}
```

#### Example 3: Basic Auth
```bash
FIRECRAWL_AUTH_TYPE=basic
FIRECRAWL_AUTH_USERNAME=admin
FIRECRAWL_AUTH_PASSWORD=secure_password
```

#### Example 4: Bearer Token
```bash
FIRECRAWL_AUTH_TYPE=bearer
FIRECRAWL_AUTH_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Step 4: Add Domain to Allowed List

```bash
# Add your internal domain
ALLOWED_DOMAINS=internal-site.com,confluence.company.com,sec.gov,reuters.com
```

### Step 5: Restart Services

```powershell
docker-compose restart crawler
```

### Step 6: Test

```powershell
# Test crawling your internal site
$body = @{
    message = "What's on https://internal-site.com/docs?"
    force_refresh = $true
    seed_urls = @("https://internal-site.com/docs")
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/chat" `
                  -Method Post `
                  -ContentType "application/json" `
                  -Body $body
```

### Step 7: Verify

Check logs for authentication:
```powershell
docker-compose logs crawler | Select-String "auth"
```

Look for:
- ✅ "Using [type] authentication"
- ✅ "Successfully crawled X documents"
- ❌ "401" or "403" errors mean authentication failed

## Common Examples

### Corporate Confluence
```bash
FIRECRAWL_AUTH_TYPE=cookies
FIRECRAWL_AUTH_COOKIES={"JSESSIONID": "ABC123", "atlassian.xsrf.token": "xyz"}
ALLOWED_DOMAINS=confluence.company.com
```

### Internal API
```bash
FIRECRAWL_AUTH_TYPE=headers
FIRECRAWL_AUTH_HEADERS={"X-API-Key": "your-key", "X-Tenant": "company"}
ALLOWED_DOMAINS=api.internal.company.com
```

### Staging Environment
```bash
FIRECRAWL_AUTH_TYPE=basic
FIRECRAWL_AUTH_USERNAME=staging_user
FIRECRAWL_AUTH_PASSWORD=staging_pass
ALLOWED_DOMAINS=staging.company.com
```

### GitHub Enterprise
```bash
FIRECRAWL_AUTH_TYPE=bearer
FIRECRAWL_AUTH_TOKEN=ghp_xxxxxxxxxxxx
ALLOWED_DOMAINS=github.company.com
```

## Troubleshooting

### Still getting 401/403 errors?

1. **Test outside FireCrawl first:**
   ```bash
   curl -H "Authorization: Bearer token" https://internal-site.com
   ```

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

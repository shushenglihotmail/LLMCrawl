# Authentication for Internal Sites

## ⚠️ Security Warning

**Authentication files contain sensitive personal information and must NEVER be committed to git!**

- `.auth/` directory is excluded in `.gitignore`
- Files are **temporary** (expire in 8-24 hours)
- Contains your username and session cookies
- Always verify with `git status` before committing

## Supported Authentication Method

LLMCrawl supports **cookie-based authentication** for crawling internal sites that require authentication.

### Cookie-Based Authentication

This method captures browser session state including:
- Cookies (including authentication cookies like `AppServiceAuthSession`)
- localStorage data
- sessionStorage data

**Use cases:**
- Sites with Microsoft SSO (Azure AD, Office 365)
- Sites with Azure App Service Easy Auth
- Sites with Conditional Access policies
- Any site requiring browser-based login

**Configuration:**
```bash
# Set authentication type
FIRECRAWL_AUTH_TYPE=cookies

# Storage state with full browser session (preferred)
FIRECRAWL_AUTH_STORAGE_STATE='{"cookies": [...], "origins": [...]}'
```

## Setup Guide

### Step 1: Capture Authentication

Use the interactive authentication tool to capture credentials from your browser:

```powershell
python tools/interactive_auth.py https://www.osgwiki.com/wiki/Main_Page --name www_osgwiki_com
```

This will:
1. Open Microsoft Edge browser
2. Navigate to the site
3. Wait for you to log in
4. Press Enter when logged in
5. Capture all cookies and session data
6. Save to `.auth/www_osgwiki_com.json`

### Step 2: Apply to Configuration

Apply the captured credentials to your `.env` file:

```powershell
.\tools\apply_auth.ps1
```

This updates the `FIRECRAWL_AUTH_STORAGE_STATE` variable in `.env`.

### Step 3: Test Authentication

Verify authentication works:

```powershell
# Test with HTTP request
python tools/test_auth.py

# Recreate crawler (after updating .env)
cd deploy && docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler

# Test render endpoint
$body = @{url='https://www.osgwiki.com/wiki/Main_Page'} | ConvertTo-Json
curl.exe -X POST http://localhost:8001/render -H 'Content-Type: application/json' -d $body
```

## Session Refresh

Authentication sessions expire periodically. See [AUTH_REFRESH_GUIDE.md](AUTH_REFRESH_GUIDE.md) for:
- Manual refresh procedures
- Automated refresh scripts
- Scheduled task setup
- Troubleshooting

## Architecture

### Cookie Flow

```
Browser (User Login)
    ↓
interactive_auth.py (Playwright)
    ↓
.auth/site_name.json (Storage State)
    ↓
apply_auth.ps1
    ↓
.env (FIRECRAWL_AUTH_STORAGE_STATE)
    ↓
Playwright Renderer (context with storage_state)
    ↓
Authenticated Page Access
```

### Key Components

1. **interactive_auth.py**: Browser automation for credential capture
2. **playwright_runner.py**: Applies storage_state to browser context
3. **firecrawl.py**: Cookie-based HTTP requests
4. **test_auth.py**: Validates current authentication
5. **refresh_auth.py**: Automated session refresh

## Security Considerations

1. **Never commit `.auth/` directory** - Contains sensitive credentials
2. **Protect `.env` file** - Contains authentication configuration
3. **Use managed devices** - Required for Conditional Access compliance
4. **Rotate credentials** - If exposed or compromised
5. **Monitor access** - Watch for unauthorized usage

## Troubleshooting

### Authentication Fails (401)
- Session expired - run refresh
- Device not compliant - use managed work device
- Cookies not applied - check `.env` file

### Credentials Not Captured
- Wait for full page load before pressing Enter
- Verify you see your username on the page
- Check browser console for errors

### Docker Container Issues
- Restart container after config changes
- Rebuild if code changes: `docker-compose up --build -d crawler`

## Example: OSGWiki (www.osgwiki.com)

OSGWiki uses Azure App Service Easy Auth with the following characteristics:
- **Primary Cookie**: `AppServiceAuthSession`
- **Auth Type**: Microsoft SSO (Azure AD)
- **Conditional Access**: Requires managed device
- **Session Duration**: Typically 8-24 hours

**Quick Setup:**
```powershell
# Capture (from managed device)
python tools/interactive_auth.py https://www.osgwiki.com/wiki/Main_Page --name www_osgwiki_com

# Apply
.\tools\apply_auth.ps1

# Test
python tools/test_auth.py

# Recreate crawler (to reload .env)
cd deploy && docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler
```

## Additional Resources

- [AUTH_REFRESH_GUIDE.md](AUTH_REFRESH_GUIDE.md) - Session management and refresh procedures
- [Azure App Service Easy Auth](https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization)
- [Conditional Access Policies](https://learn.microsoft.com/en-us/entra/identity/conditional-access/overview)

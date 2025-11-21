# Authentication Guide for www.osgwiki.com

## Overview

The www.osgwiki.com site uses Azure App Service Easy Auth with cookie-based authentication. The primary authentication cookie is `AppServiceAuthSession`. This cookie will expire periodically, requiring re-authentication.

## Authentication Method

**Cookie-based Authentication (Working)**
- Uses `AppServiceAuthSession` cookie from Azure App Service Easy Auth
- Captures full browser session state including cookies, localStorage, and sessionStorage
- Works with Microsoft SSO and Conditional Access policies
- Must be captured from a compliant managed device

## Quick Reference

### Check if authentication is valid
```powershell
python tools/test_auth.py
```

### Manual refresh (when session expires)
```powershell
# 1. Capture new session interactively
python tools/interactive_auth.py https://www.osgwiki.com/wiki/Main_Page --name www_osgwiki_com

# 2. Apply to .env
.\tools\apply_auth.ps1

# 3. Recreate crawler (to reload .env)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler
```

### Automated refresh
```powershell
# Check and refresh if needed
python tools/refresh_auth.py --name www_osgwiki_com

# Force refresh even if valid
python tools/refresh_auth.py --name www_osgwiki_com --force
```

## Detection Methods

### 1. Test Script
Run the test script to check authentication status:
```powershell
python tools/test_auth.py
```

**Success output:**
```
✅ Authentication successful!
Content length: 35570 bytes
✅ Page appears to be MediaWiki content
```

**Failure output:**
```
❌ Authentication failed (401 Unauthorized)
```

### 2. Monitor Crawler Logs
Watch for 401 errors in crawler logs:
```powershell
docker-compose logs crawler -f | Select-String "401|authentication|expired"
```

## Refresh Options

### Option 1: Manual Interactive Refresh (Recommended)
Most reliable method - uses your browser session:

```powershell
# Step 1: Capture new authentication
python tools/interactive_auth.py https://www.osgwiki.com/wiki/Main_Page --name www_osgwiki_com

# What happens:
# - Opens Microsoft Edge browser
# - Navigate to www.osgwiki.com and login
# - Press Enter when logged in
# - Cookies are captured automatically

# Step 2: Apply to configuration
.\tools\apply_auth.ps1

# Step 3: Recreate services (to reload .env)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler
```

### Option 2: Automated Refresh Script
Uses the same interactive browser but can be scripted:

```powershell
# Check and refresh if expired
python tools/refresh_auth.py --name www_osgwiki_com --apply-env

# Force refresh (ignore current status)
python tools/refresh_auth.py --name www_osgwiki_com --force --apply-env
```

### Option 3: Scheduled Task (Production)
Set up automatic daily checks:

```powershell
# Create scheduled task (runs daily at 2 AM)
.\tools\schedule_refresh.ps1

# Custom schedule
.\tools\schedule_refresh.ps1 -Time "03:00"  # 3 AM

# Manage the task
Get-ScheduledTask -TaskName "LLMCrawl-RefreshOSGWikiAuth"
Start-ScheduledTask -TaskName "LLMCrawl-RefreshOSGWikiAuth"  # Run now
Unregister-ScheduledTask -TaskName "LLMCrawl-RefreshOSGWikiAuth"  # Remove
```

## Session Expiration Timeline

Based on Azure App Service Easy Auth defaults:

- **Typical session duration**: 8-24 hours
- **Can vary** based on:
  - Conditional Access policies
  - Token lifetime policies
  - Device compliance status
  - Organizational settings

**Recommendation**: Check/refresh daily, or when you see 401 errors.

## Troubleshooting

### Issue: 401 Errors After Refresh
**Cause**: Device compliance requirement (must use compliant work device)

**Solution**:
- Run refresh from your Microsoft-managed work device
- Ensure device is Azure AD joined or Intune managed
- If working remotely, ensure you're on VPN if required

### Issue: "Device must be managed" Error
**Cause**: Conditional Access Policy requires managed device

**Solution**:
- This is expected - you must use your work device
- Cannot be bypassed without IT admin exemption

### Issue: Browser Opens but Doesn't Capture Cookies
**Solution**:
1. Wait for full page load
2. Verify you see your username in the page
3. Press Enter only when fully logged in

### Issue: Credentials Not Applied
**Solution**:
```powershell
# Verify .env has AppServiceAuthSession cookie
Select-String -Path .env -Pattern "AppServiceAuthSession"

# Force restart
docker-compose down
docker-compose up -d crawler
```

## Files and Locations

### Authentication Files
- **Captured credentials**: `.auth/www_osgwiki_com.json`
- **Configuration**: `.env` (FIRECRAWL_AUTH_STORAGE_STATE)
- **Test URL**: Set in `.env` as AUTH_TEST_URL

### Tools
- `tools/interactive_auth.py` - Interactive browser capture
- `tools/test_auth.py` - Test current authentication
- `tools/refresh_auth.py` - Automated refresh script
- `tools/apply_auth.ps1` - Apply auth to .env
- `tools/schedule_refresh.ps1` - Create scheduled task
- `tools/run_refresh_auth.ps1` - Scheduled task runner

## Best Practices

1. **Regular Monitoring**
   - Check auth status daily or before important crawls
   - Monitor logs for 401 errors
   - Set up scheduled task for automated checks

2. **Quick Response**
   - Keep refresh commands handy
   - Document when sessions typically expire

3. **Security**
   - Never commit `.auth/` directory to git
   - Keep .env file secure
   - Rotate credentials if exposed

4. **Production**
   - Use scheduled task for automatic refresh
   - Set up monitoring/alerts for 401 errors

## Example Workflow

### Daily Operations
```powershell
# Morning check
python tools/test_auth.py

# If expired, refresh
python tools/refresh_auth.py --name www_osgwiki_com --force
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate crawler

# Continue work
curl -X POST http://localhost:8001/render `
  -H "Content-Type: application/json" `
  -d "{`"url`": `"https://www.osgwiki.com/wiki/Main_Page`"}"
```

### Production Setup (One-time)
```powershell
# 1. Set up scheduled refresh
.\tools\schedule_refresh.ps1 -Time "02:00"

# 2. Test the scheduled task
Start-ScheduledTask -TaskName "LLMCrawl-RefreshOSGWikiAuth"

# 3. Verify it worked
python tools/test_auth.py

# 4. Set up log monitoring (optional)
# Add alert/notification when logs show 401 errors
```

## Additional Resources

- **Azure App Service Easy Auth**: https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization
- **Conditional Access**: https://learn.microsoft.com/en-us/entra/identity/conditional-access/overview
- **Device Compliance**: https://learn.microsoft.com/en-us/mem/intune/protect/device-compliance-get-started

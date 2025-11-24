# Authentication Workflow Improvements (Nov 2025)

## Summary

Improved authentication workflow for Azure App Service Easy Auth sites (like osgwiki.com) with better user experience, automation, and diagnostics.

## What Changed

### 1. New Check Auth Status Script
**File:** `scripts/check-auth-status.ps1`

**Features:**
- ✅ Checks auth file age and validity
- ✅ Tests actual crawling (not just file existence)
- ✅ Shows detailed diagnostics (title, content length, source)
- ✅ Provides copy/paste ready fix commands
- ✅ Fixed bug: API returns `docs` not `documents`

**Usage:**
```powershell
.\scripts\check-auth-status.ps1 https://www.osgwiki.com/wiki/Main_Page
```

### 2. Improved Manual Cookie Script
**File:** `tools/msauth/scripts/add_cookie_manual.ps1`

**New Features:**
- ✅ Fully interactive (no parameters required)
- ✅ Lists available profiles automatically
- ✅ Step-by-step prompts for cookie capture
- ✅ Automatically applies to `.env`
- ✅ Auto-restarts crawler with user confirmation
- ✅ Runs authentication test automatically
- ✅ Adds cookie to BOTH required locations (cookies[] and storage_state.cookies[])
- ✅ Clear "Step X/3" progress indicators
- ✅ Warns about speed (cookies expire fast!)

**Usage:**
```powershell
# Interactive mode (recommended)
.\tools\msauth\scripts\add_cookie_manual.ps1

# Direct mode (still supported)
.\tools\msauth\scripts\add_cookie_manual.ps1 www_osgwiki_com "COOKIE_VALUE"
```

### 3. Updated Interactive Auth Script
**File:** `tools/msauth/interactive_auth.py`

**Improvements:**
- ✅ Detects if AppServiceAuthSession was captured
- ✅ Provides different instructions based on success/failure
- ✅ References new `check-auth-status.ps1` script
- ✅ Clearer next-step commands

### 4. Documentation Updates

**Updated Files:**
- `docs/AUTHENTICATION_SETUP.md` - Added Quick Start, improved troubleshooting
- `docs/AUTHENTICATION_QUICKSTART.md` - Updated with new script names and workflows

**Key Improvements:**
- Clear distinction between standard OAuth and Azure App Service Easy Auth
- Interactive workflow emphasized as primary method
- Better troubleshooting section
- Cookie expiration warnings
- Container recreation vs restart clarification

## Key Learnings

### Docker .env Reload Issue
**Problem:** `docker-compose restart` doesn't reload `.env` changes

**Solution:** Use `docker-compose up -d <service>` to recreate container
```powershell
cd deploy && docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d crawler
```

### API Field Name Bug
**Problem:** `check-auth-status.ps1` was checking `$result.documents` but API returns `$result.docs`

**Fix:** Updated to use correct field name

### Cookie Storage Locations
**Problem:** Cookie must be in BOTH `cookies[]` and `storage_state.cookies[]`

**Fix:** `add_cookie_manual.ps1` now adds to both locations

### Cookie Expiration
**Issue:** Azure App Service cookies expire quickly (10-30 minutes)

**Mitigation:**
- Clear warnings in prompts
- Instructions to capture quickly
- Status check script for validation

## Testing Workflow

Recommended workflow for testing auth:

```powershell
# 1. Check current status
.\scripts\check-auth-status.ps1 https://www.osgwiki.com/wiki/Main_Page

# 2. If expired, refresh (interactive prompts guide you)
.\tools\msauth\scripts\add_cookie_manual.ps1

# 3. Script automatically tests after restart
```

## Future Improvements

Potential enhancements:

1. **Automated Cookie Refresh** - Background task to refresh cookies before expiration
2. **Cookie Lifetime Detection** - Parse cookie expiration from value
3. **Multi-Site Management** - Easier switching between multiple authenticated sites
4. **Credential Vault Integration** - Store cookies more securely
5. **Health Check Endpoint** - Expose auth status via API

## Migration Guide

If you have existing auth setup:

**No action needed!** The improved scripts are backward compatible.

**Optional:** Try the new interactive workflow:
```powershell
.\tools\msauth\scripts\add_cookie_manual.ps1
```

# Microsoft Authentication Tools

Tools for authenticating to Microsoft internal sites (e.g., www.osgwiki.com) that require Microsoft SSO with cookie-based authentication.

## ⚠️ Security Warning

**NEVER commit authentication files to git!**

- `.auth/` directory contains **sensitive credentials** and **personal information**
- These files are **temporary** and **expire** (typically 8-24 hours)
- `.gitignore` is configured to exclude `.auth/` directory
- Always verify `.auth/` is not staged before committing: `git status`

## Overview

These tools capture and manage browser-based authentication sessions for sites protected by:
- Microsoft Azure AD / Entra ID
- Azure App Service Easy Auth
- Conditional Access policies

## Directory Structure

```
tools/msauth/
├── docs/                           # Documentation
│   ├── AUTHENTICATION.md          # Main auth setup guide
│   ├── AUTH_REFRESH_GUIDE.md     # Session refresh procedures
│   └── CLEANUP_SUMMARY.md        # Code cleanup history
├── scripts/                       # PowerShell scripts
│   ├── apply_auth.ps1            # Apply captured auth to .env
│   ├── schedule_refresh.ps1      # Set up scheduled task
│   └── run_refresh_auth.ps1      # Executed by scheduled task
├── interactive_auth.py           # Interactive browser auth capture
├── refresh_auth.py               # Automated session refresh
├── test_auth.py                  # Test current authentication
└── README.md                      # This file
```

## Quick Start

### 1. Capture Authentication

Capture authentication from your browser (must be on compliant managed device):

```powershell
python tools/msauth/interactive_auth.py https://www.osgwiki.com/wiki/Main_Page --name www_osgwiki_com
```

### 2. Apply to Configuration

```powershell
.\tools\msauth\scripts\apply_auth.ps1
```

### 3. Test

```powershell
python tools/msauth/test_auth.py
```

### 4. Restart Services

```powershell
docker-compose restart crawler
```

## Tools

### interactive_auth.py

Captures authentication by opening a browser and saving the session state.

```powershell
# Basic usage
python tools/msauth/interactive_auth.py <URL> --name <site_name>

# Example
python tools/msauth/interactive_auth.py https://www.osgwiki.com/wiki/Main_Page --name www_osgwiki_com

# With timeout
python tools/msauth/interactive_auth.py <URL> --name <site_name> --timeout 300
```

**Output:** Creates `.auth/<site_name>.json` (temporary file with session credentials)

⚠️ **Important:** This file contains your personal credentials and expires in 8-24 hours

### test_auth.py

Tests if current authentication is valid.

```powershell
python tools/msauth/test_auth.py
```

### refresh_auth.py

Automated session refresh with expiration detection.

```powershell
# Check and refresh if expired
python tools/msauth/refresh_auth.py --name www_osgwiki_com

# Force refresh
python tools/msauth/refresh_auth.py --name www_osgwiki_com --force

# Check only (no refresh)
python tools/msauth/refresh_auth.py --name www_osgwiki_com --check-only
```

### apply_auth.ps1

Applies captured authentication to `.env` file.

```powershell
.\tools\msauth\scripts\apply_auth.ps1
```

### schedule_refresh.ps1

Sets up Windows Task Scheduler for automatic daily auth refresh.

```powershell
# Default: runs at 2 AM daily
.\tools\msauth\scripts\schedule_refresh.ps1

# Custom time
.\tools\msauth\scripts\schedule_refresh.ps1 -Time "03:00"
```

### run_refresh_auth.ps1

Script executed by scheduled task. Checks auth status, refreshes if needed, and restarts crawler.

## Authentication Flow

```
1. User logs in via browser on compliant device
   ↓
2. interactive_auth.py captures session (cookies, storage)
   ↓
3. Session saved to .auth/site_name.json
   ↓
4. apply_auth.ps1 updates .env file
   ↓
5. Playwright renderer uses session for authenticated requests
   ↓
6. Session expires after 8-24 hours
   ↓
7. refresh_auth.py detects expiration and repeats process
```

## Security & File Lifecycle

### Temporary Authentication Files

**`.auth/<site_name>.json`** files are **temporary** and contain:
- Personal session cookies (including your username)
- Authentication tokens
- Browser storage state (localStorage, sessionStorage)

**Lifecycle:**
1. **Created**: By `interactive_auth.py` when you log in
2. **Used**: Copied to `.env` by `apply_auth.ps1`
3. **Expires**: After 8-24 hours (Azure App Service Easy Auth default)
4. **Refreshed**: By running `interactive_auth.py` again or using `refresh_auth.py`

### Security Best Practices

✅ **DO:**
- Verify `.gitignore` contains `.auth/` before committing
- Delete `.auth/` files when switching branches
- Refresh credentials regularly (daily for production)
- Run `git status` before committing to check for secrets

❌ **DON'T:**
- Commit `.auth/` directory to git
- Share `.auth/` files with others
- Use credentials from non-compliant devices
- Keep expired credentials around

### Git Protection

The `.gitignore` file is configured to exclude:
```
.auth/
*.auth.json
*_auth.json
```

Verify with: `git check-ignore .auth/www_osgwiki_com.json`

## Requirements

- **Managed Device**: Must run on Microsoft-managed device (Azure AD joined or Intune managed)
- **Compliance**: Device must meet Conditional Access policy requirements
- **Browser**: Microsoft Edge (installed by Playwright)
- **Python**: Python 3.8+
- **PowerShell**: PowerShell 5.1+ or PowerShell Core 7+

## Security

- Never commit `.auth/` directory (contains sensitive session cookies)
- Keep `.env` file secure
- Sessions expire and require re-authentication from compliant device
- Use scheduled refresh for production environments

## Troubleshooting

See [docs/AUTH_REFRESH_GUIDE.md](docs/AUTH_REFRESH_GUIDE.md) for common issues and solutions.

**Common Issues:**

1. **401 Unauthorized**: Session expired - run refresh
2. **Device must be managed**: Must use work device with Intune/Azure AD
3. **Cookies not captured**: Press Enter only after fully logged in

## Adding Authentication for New Sites

1. Run interactive_auth.py with the site URL and a unique name
2. Run apply_auth.ps1 to update configuration
3. Test with test_auth.py
4. Document any site-specific requirements

## Future Extensions

This directory can be extended with:
- Other Microsoft authentication methods
- Support for different Microsoft cloud environments (GCC, DoD, etc.)
- Additional internal Microsoft sites
- Multi-site authentication management

## References

- [Azure App Service Easy Auth](https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization)
- [Conditional Access](https://learn.microsoft.com/en-us/entra/identity/conditional-access/overview)
- [Device Compliance](https://learn.microsoft.com/en-us/mem/intune/protect/device-compliance-get-started)

# Microsoft Authentication Tools

Tools for authenticating to Microsoft internal sites (e.g., www.osgwiki.com) that require Microsoft SSO with cookie-based authentication.

## ⚠️ Security Warning

**NEVER commit authentication files to git!**

- `.auth/` directory contains **sensitive credentials** and **personal information**
- These files are **temporary** and **expire** (typically 8-24 hours)
- `.gitignore` is configured to exclude `.auth/` directory
- Always verify `.auth/` is not staged before committing: `git status`

---

## Quick Start

```powershell
# Activate virtual environment
cd C:\src\github\LLMCrawl
.\venv\Scripts\Activate.ps1

# Run authentication (fully automated)
python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page
```

This single command will:
1. ✅ Launch Edge with debugging enabled
2. ⏸️ Wait for you to sign in
3. ✅ Extract authentication cookies
4. ✅ Save to `.auth/` directory
5. ✅ Apply to `deploy/.env`
6. ✅ Restart crawler container
7. ✅ Test authentication

**That's it!** See [docs/AUTHENTICATION.md](../../docs/AUTHENTICATION.md) for full documentation.

---

## Files

| File | Purpose |
|------|---------|
| `authenticate.py` | **Main authentication script** - use this |
| `test_auth.py` | Test if current authentication works |

---

## How It Works

The tool uses **Edge Remote Debugging** to capture cookies:

1. Launches Edge with `--remote-debugging-port=9222`
2. You authenticate in the browser (SSO, MFA, etc.)
3. Connects via Chrome DevTools Protocol (CDP)
4. Extracts cookies (including HttpOnly like `AppServiceAuthSession`)
5. Saves and applies credentials automatically

This bypasses cookie encryption issues because Edge decrypts cookies for CDP access.

---

## Supported Authentication

- ✅ Azure App Service Easy Auth
- ✅ Microsoft Azure AD / Entra ID
- ✅ Conditional Access policies
- ✅ Multi-factor authentication (MFA)
- ✅ Any cookie-based authentication

---

## Re-Authentication

When cookies expire (8-24 hours), simply re-run:

```powershell
python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page
```

---

## Documentation

Full documentation: [docs/AUTHENTICATION.md](../../docs/AUTHENTICATION.md)

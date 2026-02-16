# Authentication Guide

This guide covers all authentication methods in LLMCrawl: internal site authentication for web crawling and Entra ID authentication for Azure AI services.

## Table of Contents

- [Overview](#overview)
- [Internal Site Authentication (Cookie-Based)](#internal-site-authentication-cookie-based)
  - [Quick Start](#quick-start)
  - [How It Works](#how-it-works)
  - [Command Options](#command-options)
  - [Other Authentication Types](#other-authentication-types)
  - [Re-Authentication](#re-authentication)
  - [Troubleshooting](#troubleshooting-internal-auth)
- [Entra ID Authentication (Azure AI)](#entra-id-authentication-azure-ai)
  - [Quick Start Setup](#quick-start-setup)
  - [Azure AD App Registration](#azure-ad-app-registration)
  - [Configuration](#entra-id-configuration)
  - [Usage](#entra-id-usage)
  - [API Endpoints](#api-endpoints)
  - [Troubleshooting](#troubleshooting-entra-id)
  - [Security Considerations](#security-considerations)

---

## Overview

LLMCrawl supports two types of authentication:

1. **Internal Site Authentication** - For crawling internal sites (wikis, intranets) that require SSO/cookie-based authentication
2. **Entra ID Authentication** - For accessing Azure AI services (Azure OpenAI, Azure Anthropic) with OAuth tokens instead of API keys

---

## Internal Site Authentication (Cookie-Based)

For crawling internal sites like osgwiki.com that use Azure App Service Easy Auth or similar cookie-based authentication.

### Security Warning

**Authentication files contain sensitive credentials - NEVER commit them to git!**

- `.auth/` directory is excluded in `.gitignore`
- Files are **temporary** and expire (typically 8-24 hours)
- Always verify with `git status` before committing

### Quick Start

For sites using Azure App Service Easy Auth:

```powershell
# Using the CLI command (from wheel installation)
llmcrawl auth https://www.osgwiki.com/wiki/Main_Page

# Or using the Python script (from source)
python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page
```

**What happens:**
1. Edge browser opens with debugging enabled
2. You sign in with Microsoft credentials (complete MFA if prompted)
3. Press ENTER when you see the authenticated content
4. Cookies are extracted automatically
5. Credentials saved to `.auth/` directory
6. Applied to `deploy/.env` file
7. Crawler container recreated
8. Authentication tested

### How It Works

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

**Cookie Flow:**

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

### Command Options

#### Using the CLI (Wheel Installation)

```powershell
# Basic usage
llmcrawl auth <URL>

# Options
llmcrawl auth https://www.osgwiki.com/wiki/Main_Page `
    --name my_wiki           # Custom profile name
    --dir /path/to/deploy    # Specify deployment directory
    --no-apply               # Don't apply to .env (just save cookies)
    --no-restart             # Don't restart crawler container
    --no-test                # Don't test authentication
    --port 9223              # Use different debug port
```

#### Using the Python Script (Development)

```powershell
python tools/msauth/authenticate.py <URL>

# With options
python tools/msauth/authenticate.py https://www.osgwiki.com/wiki/Main_Page `
    --name my_wiki           # Custom profile name
    --no-apply               # Don't apply to .env
    --no-restart             # Don't restart crawler container
```

### Other Authentication Types

For sites that don't use Azure App Service Easy Auth:

#### Bearer Token
```bash
# In deploy/.env
FIRECRAWL_AUTH_TYPE=bearer
FIRECRAWL_AUTH_TOKEN=your-token-here
```

#### Basic Auth
```bash
# In deploy/.env
FIRECRAWL_AUTH_TYPE=basic
FIRECRAWL_AUTH_USERNAME=user
FIRECRAWL_AUTH_PASSWORD=pass
```

#### Azure AD OAuth (Programmatic)
```bash
# In deploy/.env
FIRECRAWL_AUTH_TYPE=azure_ad
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
AZURE_SCOPE=https://graph.microsoft.com/.default
```

### Re-Authentication

When cookies expire (typically 8-24 hours), simply re-run:

```powershell
llmcrawl auth https://www.osgwiki.com/wiki/Main_Page
```

### Troubleshooting Internal Auth

| Problem | Solution |
|---------|----------|
| ".env file not found" | Use `--dir` flag to specify deployment folder |
| "Edge not found" | Ensure Microsoft Edge is installed |
| "Connection refused" | Close all Edge instances, check Task Manager |
| "Cookie not found" | Ensure you're fully logged in before pressing ENTER |
| "Authentication test failed" | Check if crawler is running, view crawler logs |
| Cookie expires quickly | Re-run authentication (8-24 hour expiry is normal) |

**Supported Sites:**
- Azure App Service Easy Auth
- Microsoft Azure AD / Entra ID SSO
- Sites with Conditional Access policies
- Multi-factor authentication (MFA)
- Any cookie-based authentication

---

## Entra ID Authentication (Azure AI)

For accessing Azure AI services (Azure OpenAI, Azure Anthropic) using Entra ID OAuth tokens instead of API keys.

### Quick Start Setup

**Step 1: Create Azure AD App Registration (5 minutes)**

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to: **Azure Active Directory** → **App registrations** → **New registration**
3. Configure:
   ```
   Name: LLMCrawl-Desktop-Client
   Supported account types: Accounts in this organizational directory only
   Redirect URI: Public client/native (mobile & desktop) → http://localhost
   ```
4. Click **Register**
5. Copy these values:
   - Application (client) ID
   - Directory (tenant) ID

**Step 2: Configure App Permissions**

1. In your app registration, go to: **API permissions**
2. Click **Add a permission** → **APIs my organization uses**
3. Search for your Azure Foundry resource name
4. Select appropriate permissions (e.g., `user_impersonation`)
5. Click **Add permissions**
6. (Optional but recommended) Click **Grant admin consent**

**Step 3: Enable Public Client Flows**

1. Go to: **Authentication** tab
2. Under **Advanced settings** → **Allow public client flows**
3. Set **Enable mobile and desktop flows** to **Yes**
4. Click **Save**

**Step 4: Configure Environment Variables**

```bash
# Required for Entra ID auth
ENTRA_CLIENT_ID=<paste-application-client-id-here>
ENTRA_TENANT_ID=<paste-directory-tenant-id-here>
AZURE_FOUNDRY_SCOPE=https://ai.azure.com/.default

# Azure endpoints
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_ANTHROPIC_ENDPOINT=https://your-resource.services.ai.azure.com/anthropic/

# Leave API keys empty to use bearer tokens
AZURE_OPENAI_API_KEY=
```

### Azure AD App Registration

For detailed app registration:

1. Go to [Azure Portal](https://portal.azure.com) → Azure Active Directory → App registrations
2. Click "New registration"
3. Configure:
   - **Name**: LLMCrawl Desktop Client
   - **Supported account types**: Choose based on your needs
     - "Accounts in this organizational directory only" (single tenant)
     - "Accounts in any organizational directory" (multi-tenant)
   - **Redirect URI**: Public client/native → `http://localhost`
4. After registration:
   - Note the **Application (client) ID** → `ENTRA_CLIENT_ID`
   - Note the **Directory (tenant) ID** → `ENTRA_TENANT_ID`
   - Go to "Authentication" → Enable "Mobile and desktop flows"
   - Go to "API permissions" → Add Azure Foundry scope

### Entra ID Configuration

**HiChat Client Configuration:**

```bash
# Required for MSAL authentication
ENTRA_CLIENT_ID=<your-application-client-id>
ENTRA_TENANT_ID=<your-tenant-id-or-common>
AZURE_FOUNDRY_SCOPE=https://ai.azure.com/.default

# Gateway URL
LLMCRAWL_GATEWAY_URL=http://localhost:8000
```

**Tenant ID options:**
- Your specific tenant ID (for single-tenant apps)
- `common` (for multi-tenant apps)
- `organizations` (any organizational Azure AD account)
- `consumers` (personal Microsoft accounts)

**Gateway Configuration (Optional):**

For JWT validation in production:

```bash
JWT_VALIDATION_ENABLED=true
ENTRA_TENANT_ID=<your-tenant-id>
ENTRA_CLIENT_ID=<azure-foundry-resource-app-id>
```

### Entra ID Usage

**Starting HiChat with Authentication:**

```bash
# Enable authentication with flag
python clients/hichat/main.py --enable-auth

# Or set environment variable (auto-enables auth)
export ENTRA_CLIENT_ID=<your-client-id>
python clients/hichat/main.py
```

**First-Time Sign-In:**
1. HiChat opens your default browser
2. Sign in with Microsoft credentials
3. Complete MFA if required
4. Browser closes automatically
5. Token cached at `~/.llmcrawl/token_cache.bin`

**Silent Sign-In:**
After first sign-in, tokens refresh silently. No browser pop-up unless token can't be refreshed.

**Sign Out:**
```bash
# Via API
curl -X POST http://localhost:8080/api/auth/logout

# Or delete token cache
rm ~/.llmcrawl/token_cache.bin
```

### API Endpoints

HiChat exposes these authentication endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/auth/status` | GET | Current authentication status |
| `/api/auth/login` | POST | Trigger interactive login |
| `/api/auth/logout` | POST | Sign out and clear cache |
| `/api/auth/refresh` | POST | Silent token refresh |

**Status Response Example:**
```json
{
  "enabled": true,
  "authenticated": true,
  "account": {
    "username": "user@example.com",
    "name": "John Doe"
  }
}
```

### Troubleshooting Entra ID

| Problem | Solution |
|---------|----------|
| Browser doesn't open | System falls back to Device Code Flow - follow URL in terminal |
| "Token has expired" | Sign in again (HiChat prompts automatically) |
| "Invalid token" | Check `ENTRA_TENANT_ID` and `ENTRA_CLIENT_ID` match app registration |
| "Failed to fetch signing keys" | Check internet connectivity |
| Token not passed to Azure | Check gateway logs for "Including bearer token" |

### Security Considerations

**Token Storage:**
- Tokens stored at `~/.llmcrawl/token_cache.bin`
- File permissions restricted to user (handled by MSAL)
- Tokens encrypted by MSAL library

**Best Practices:**
- Enable JWT validation in production (`JWT_VALIDATION_ENABLED=true`)
- Use HTTPS for all services in production
- Request minimal scopes needed
- Don't hardcode tokens in code or config files

---

## File Locations

| File | Purpose |
|------|---------|
| `tools/msauth/authenticate.py` | Internal site authentication script |
| `.auth/<name>.json` | Saved cookies (gitignored) |
| `deploy/.env` | Environment config with auth settings |
| `~/.llmcrawl/token_cache.bin` | MSAL token cache (Entra ID) |

---

## Related Documentation

- **[INSTALL.md](INSTALL.md)** - Installation guide
- **[CONFIGURATION.md](CONFIGURATION.md)** - Full configuration reference
- **[DIAGNOSTICS.md](DIAGNOSTICS.md)** - Troubleshooting guide

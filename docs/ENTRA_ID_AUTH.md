# Entra ID Authentication for Azure Foundry

## Overview

This document explains how to set up and use Entra ID (Azure AD) authentication with Azure Foundry service in LLMCrawl.

## Architecture

The authentication flow works as follows:

1. **HiChat Client** (Desktop/Web)
   - Uses MSAL (Microsoft Authentication Library) to authenticate users
   - Opens system browser for interactive sign-in
   - Handles MFA, Conditional Access, and device compliance automatically
   - Caches tokens locally for silent refresh

2. **Gateway Service**
   - Receives bearer token from HiChat client
   - Optional: Validates JWT token against Entra ID
   - Passes token to LLM client

3. **LLM Client**
   - Includes bearer token in requests to Azure Foundry
   - Supports both OpenAI and Anthropic providers

## Prerequisites

### Azure AD App Registration

You need to register an application in Azure AD:

1. Go to [Azure Portal](https://portal.azure.com) → Azure Active Directory → App registrations
2. Click "New registration"
3. Configure:
   - **Name**: LLMCrawl Desktop Client (or your preferred name)
   - **Supported account types**:
     - "Accounts in this organizational directory only" (single tenant)
     - OR "Accounts in any organizational directory" (multi-tenant)
   - **Redirect URI**:
     - Type: **Public client/native (mobile & desktop)**
     - URI: `http://localhost`
4. Click "Register"

### App Configuration

After registration:

1. Note the **Application (client) ID** - you'll need this for `ENTRA_CLIENT_ID`
2. Note the **Directory (tenant) ID** - you'll need this for `ENTRA_TENANT_ID`
3. Go to "Authentication" tab
   - Ensure "Public client flows" → "Enable mobile and desktop flows" is set to **Yes**
4. Go to "API permissions" tab
   - Add the Azure Foundry API scope (e.g., `https://ai.azure.com/.default`)
   - Click "Add a permission" → "APIs my organization uses"
   - Search for your Azure Foundry resource
   - Select the appropriate permissions
   - Click "Add permissions"
   - (Optional) Click "Grant admin consent" if required

## Configuration

### HiChat Client Configuration

Add these environment variables to your `.env` file or set them in your environment:

```bash
# Required for MSAL authentication
ENTRA_CLIENT_ID=<your-application-client-id>
ENTRA_TENANT_ID=<your-tenant-id-or-common>
AZURE_FOUNDRY_SCOPE=https://ai.azure.com/.default

# Gateway URL (default: http://localhost:8000)
LLMCRAWL_GATEWAY_URL=http://localhost:8000
```

**Important Notes:**
- `ENTRA_TENANT_ID` can be:
  - Your specific tenant ID (for single-tenant apps)
  - `common` (for multi-tenant apps, allows any Azure AD account)
  - `organizations` (allows any organizational Azure AD account)
  - `consumers` (allows personal Microsoft accounts)
- `AZURE_FOUNDRY_SCOPE` should match the API scope for your Azure Foundry resource
  - Common format: `https://ai.azure.com/.default`
  - Or the specific App ID URI from your Foundry resource registration

### Gateway Configuration (Optional)

If you want to validate JWT tokens at the gateway (recommended for production):

```bash
# Enable JWT validation
JWT_VALIDATION_ENABLED=true
ENTRA_TENANT_ID=<your-tenant-id>
ENTRA_CLIENT_ID=<azure-foundry-resource-app-id>
```

If you just want to pass tokens through without validation (simpler, for development):

```bash
# Disable JWT validation (default)
JWT_VALIDATION_ENABLED=false
```

## Usage

### Starting HiChat with Authentication

```bash
# Enable authentication with --enable-auth flag
python clients/hichat/main.py --enable-auth

# Or set ENTRA_CLIENT_ID environment variable (auto-enables auth)
export ENTRA_CLIENT_ID=<your-client-id>
export AZURE_FOUNDRY_SCOPE=<your-scope>
python clients/hichat/main.py
```

### First-Time Sign-In

On first launch:

1. HiChat will automatically open your default browser
2. You'll be redirected to Microsoft sign-in page
3. Enter your credentials
4. Complete MFA if required
5. Browser will close automatically
6. HiChat will receive the token and cache it locally

Token cache location: `~/.llmcrawl/token_cache.bin`

### Silent Sign-In

After the first sign-in:
- Tokens are cached locally
- HiChat will silently refresh tokens when they expire
- No browser pop-up unless token can't be refreshed (e.g., password changed, MFA policy changed)

### Manual Sign-Out

To sign out and clear cached tokens:

```bash
# Via API (if HiChat is running)
curl -X POST http://localhost:8080/api/auth/logout

# Or delete token cache manually
rm ~/.llmcrawl/token_cache.bin
```

## API Endpoints

HiChat exposes these authentication endpoints:

### GET /api/auth/status
Get current authentication status.

**Response:**
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

### POST /api/auth/login
Trigger interactive login flow (opens browser).

**Response:**
```json
{
  "success": true,
  "account": {
    "username": "user@example.com",
    "name": "John Doe"
  }
}
```

### POST /api/auth/logout
Sign out and clear token cache.

**Response:**
```json
{
  "success": true
}
```

### POST /api/auth/refresh
Attempt silent token refresh.

**Response (success):**
```json
{
  "success": true,
  "refreshed": true
}
```

**Response (needs login):**
```json
{
  "success": false,
  "requiresLogin": true
}
```

## Troubleshooting

### Browser doesn't open for sign-in

If the interactive flow fails to open a browser, the tool will automatically fall back to **Device Code Flow**:

1. You'll see a code and URL in the terminal
2. Navigate to https://microsoft.com/devicelogin in any browser
3. Enter the code
4. Complete sign-in
5. Return to HiChat - it will automatically receive the token

### Token validation errors

If using JWT validation (`JWT_VALIDATION_ENABLED=true`):

**Error: "Token has expired"**
- Token expired and couldn't be refreshed silently
- Solution: Sign in again (HiChat will prompt automatically)

**Error: "Invalid token"**
- Token signature doesn't match
- Wrong tenant/audience configuration
- Solution: Check `ENTRA_TENANT_ID` and `ENTRA_CLIENT_ID` match your app registration

**Error: "Failed to fetch signing keys"**
- Network issue reaching Microsoft's JWKS endpoint
- Solution: Check internet connectivity, retry

### Token not being passed to Azure Foundry

Check gateway logs for:
```
INFO: Using Entra ID bearer token for LLM authentication
```

If you don't see this:
1. Verify HiChat is including the token: Check logs for "Including bearer token in gateway request"
2. Verify gateway is receiving it: Check logs for "Extracted bearer token"
3. Check Authorization header is set correctly

## Security Considerations

### Token Storage
- Tokens are stored locally in `~/.llmcrawl/token_cache.bin`
- File permissions should be restricted to the user (automatically handled by MSAL)
- Tokens are encrypted by MSAL library

### Token Scope
- Request minimal scopes needed for Azure Foundry
- Use `.default` scope to get all permissions assigned to the app registration
- Don't hardcode tokens in code or configuration files

### JWT Validation
- Enable JWT validation in production (`JWT_VALIDATION_ENABLED=true`)
- This validates:
  - Token signature (using Microsoft's JWKS)
  - Token expiration
  - Token audience (matches your resource)
  - Token issuer (matches your tenant)

### HTTPS
- In production, use HTTPS for all services
- Tokens should never be sent over unencrypted connections
- Update `LLMCRAWL_GATEWAY_URL` to use `https://`

## Advanced Configuration

### Multi-Tenant Support

To support users from any Azure AD tenant:

```bash
ENTRA_TENANT_ID=common
```

### Custom Token Caching

To use a custom token cache location:

```python
from clients.hichat.msal_auth import MSALAuthClient
from pathlib import Path

auth_client = MSALAuthClient(
    client_id="<your-client-id>",
    authority="https://login.microsoftonline.com/<tenant-id>",
    scopes=["<your-scope>"],
    cache_file=Path("/custom/path/token_cache.bin")
)
```

### Programmatic Token Management

```python
from clients.hichat.msal_auth import create_auth_client_from_env

# Create client
auth_client = create_auth_client_from_env()

# Get token (interactive if needed)
token = auth_client.get_token()

# Get account info
account = auth_client.get_account_info()
print(f"Signed in as: {account['username']}")

# Sign out
auth_client.sign_out()
```

## References

- [Microsoft Authentication Library (MSAL) for Python](https://github.com/AzureAD/microsoft-authentication-library-for-python)
- [Azure AD App Registration Documentation](https://learn.microsoft.com/en-us/azure/active-directory/develop/quickstart-register-app)
- [Azure AI Foundry Authentication](https://learn.microsoft.com/en-us/azure/ai-studio/concepts/authentication)

# Quick Start: Entra ID Authentication Setup

This guide will help you quickly set up Entra ID authentication for LLMCrawl with Azure Foundry.

## Prerequisites

- Azure subscription with access to Azure AD
- Azure AI Foundry resource provisioned
- Admin access to create app registrations

## Step 1: Create Azure AD App Registration (5 minutes)

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to: **Azure Active Directory** → **App registrations** → **New registration**
3. Configure:
   ```
   Name: LLMCrawl-Desktop-Client
   Supported account types: Accounts in this organizational directory only
   Redirect URI: Public client/native (mobile & desktop) → http://localhost
   ```
4. Click **Register**
5. **Copy these values** (you'll need them):
   - Application (client) ID
   - Directory (tenant) ID

## Step 2: Configure App Permissions

1. In your app registration, go to: **API permissions**
2. Click **Add a permission** → **APIs my organization uses**
3. Search for your Azure Foundry resource name
4. Select appropriate permissions (e.g., `user_impersonation`)
5. Click **Add permissions**
6. (Optional but recommended) Click **Grant admin consent**

## Step 3: Enable Public Client Flows

1. Go to: **Authentication** tab
2. Under **Advanced settings** → **Allow public client flows**
3. Set **Enable mobile and desktop flows** to **Yes**
4. Click **Save**

## Step 4: Configure Environment Variables

Create or update your `.env` file:

```bash
# Required for Entra ID auth
ENTRA_CLIENT_ID=<paste-application-client-id-here>
ENTRA_TENANT_ID=<paste-directory-tenant-id-here>
AZURE_FOUNDRY_SCOPE=https://ai.azure.com/.default

# Azure endpoints
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_ANTHROPIC_ENDPOINT=https://your-resource.services.ai.azure.com/anthropic/

# Remove or leave empty (deprecated)
AZURE_OPENAI_API_KEY=

# Gateway URL
LLMCRAWL_GATEWAY_URL=http://localhost:8000
```

## Step 5: Install Dependencies

```bash
cd clients/hichat
pip install -r requirements.txt
```

## Step 6: Start Services

### Terminal 1 - Gateway Service
```bash
cd LLMCrawl
python -m gateway.main
```

### Terminal 2 - HiChat Client (with auth enabled)
```bash
cd LLMCrawl
python clients/hichat/main.py --enable-auth
```

## Step 7: First Login

1. HiChat will automatically open your browser
2. Sign in with your Azure AD credentials
3. Complete MFA if prompted
4. Browser will close automatically
5. You're now authenticated!

Token is cached in `~/.llmcrawl/token_cache.bin` for future sessions.

## Verification

Check the logs:
- HiChat should show: `Signed in from cache: user@example.com` (after first login)
- Gateway should show: `Using Entra ID bearer token for LLM authentication`

## Troubleshooting

### "ENTRA_CLIENT_ID environment variable is required"
- Make sure your `.env` file is in the correct location
- Verify the variable names are correct

### Browser doesn't open
- The system will fallback to device code flow
- Follow the URL and code shown in terminal
- Sign in at https://microsoft.com/devicelogin

### "Invalid token" or "Token has expired"
- Run: `rm ~/.llmcrawl/token_cache.bin`
- Restart HiChat to re-authenticate

## Next Steps

- See [ENTRA_ID_AUTH.md](./ENTRA_ID_AUTH.md) for detailed documentation
- Configure JWT validation for production
- Set up multi-tenant support if needed

## Common Issues

**Q: Can I still use API keys?**
A: API keys are deprecated but still work as a fallback. However, Entra ID is the recommended and more secure approach.

**Q: Do I need to sign in every time?**
A: No! After the first sign-in, tokens are cached and refreshed automatically.

**Q: Can multiple users use the same client?**
A: Each user will have their own cached token. Use `POST /api/auth/logout` to switch users.

**Q: Is this secure?**
A: Yes! MSAL handles token storage securely, and bearer tokens are only sent over HTTPS in production.

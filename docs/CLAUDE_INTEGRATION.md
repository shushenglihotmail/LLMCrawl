# Claude Code Integration Guide

## Overview

LLMCrawl now supports direct integration with Claude Code models using Entra ID SSO authentication. This allows you to use Claude models alongside your existing Azure Foundry models.

## Architecture

The Claude integration adds a parallel authentication flow to the existing Azure Foundry authentication:

```
┌─────────────────────────────────────────────────────────┐
│                    HiChat Client                         │
│  ┌─────────────────┐      ┌──────────────────┐         │
│  │ Azure Foundry   │      │   Claude Code    │         │
│  │ Authentication  │      │  Authentication  │         │
│  │   (MSAL)        │      │  (OAuth PKCE)    │         │
│  └────────┬────────┘      └────────┬─────────┘         │
│           │                        │                     │
│           ▼                        ▼                     │
│   Bearer Token (Azure)    Bearer Token (Claude)         │
└───────────┼────────────────────────┼─────────────────────┘
            │                        │
            │   X-Provider-Auth      │
            ▼                        ▼
┌─────────────────────────────────────────────────────────┐
│              Gateway Service (Port 8000)                 │
│  ┌──────────────────────────────────────────┐           │
│  │         Token Context Middleware         │           │
│  │  - Extracts Bearer token                 │           │
│  │  - Identifies provider (azure/claude)    │           │
│  └──────────────────┬───────────────────────┘           │
│                     ▼                                    │
│  ┌──────────────────────────────────────────┐           │
│  │          LLM Client Router               │           │
│  │  - Routes based on provider_type         │           │
│  └──┬───────────────────────────────────┬───┘           │
│     │                                   │                │
│     ▼                                   ▼                │
│  Azure Foundry                   Claude API              │
│  (Anthropic via Azure)           (api.anthropic.com)     │
└─────────────────────────────────────────────────────────┘
```

## Features

- **Separate Authentication**: Claude uses its own OAuth 2.0 PKCE flow, independent of Azure Foundry
- **SSO Support**: Authenticate via company SSO through console.anthropic.com
- **Automatic Model Discovery**: Claude models are automatically added to the model dropdown after authentication
- **Token Management**: Tokens are cached locally and automatically refreshed
- **Visual Indicators**: UI shows authentication status with color-coded button

## Configuration

### Environment Variables

Claude authentication settings are configured in the **HiChat client** (not the gateway), since the client performs the OAuth flow.

Create or update `clients/hichat/.env` with these settings:

```env
# Gateway URL
LLMCRAWL_GATEWAY_URL=http://localhost:8000

# Azure Foundry Authentication
ENTRA_CLIENT_ID=04b07795-8ddb-461a-bbee-02f9e1bf7b46
ENTRA_TENANT_ID=72f988bf-86f1-41af-91ab-2d7cd011db47
AZURE_FOUNDRY_SCOPE=https://cognitiveservices.azure.com/.default

# Claude Code Authentication (HiChat client settings)
CLAUDE_CLIENT_ID=9d1c250a-e61b-44d9-88ed-5944d1962f5e  # Official Claude CLI client ID
CLAUDE_REDIRECT_PORT=54545  # Localhost port for OAuth redirect
CLAUDE_SCOPES=org:create_api_key user:profile user:inference

# HiChat Server Settings
HICHAT_PORT=8080
```

**Note**: An `.env.example` file is provided in `clients/hichat/` for reference.

### Model Configuration

Add Claude models to the `LLM_MODELS` configuration in **`deploy/.env`** (gateway configuration):

```json
LLM_MODELS=[
  {
    "name": "gpt-4o",
    "display_name": "GPT-4o",
    "deployment_name": "gpt-4o",
    "provider_type": "openai"
  },
  {
    "name": "claude-sonnet-4",
    "display_name": "Claude Sonnet 4",
    "deployment_name": "claude-sonnet-4-20250514",
    "provider_type": "claude",
    "max_output_tokens": 64000
  }
]
```

**Important**: Set `provider_type` to `"claude"` for Claude models (not `"anthropic"`, which is for Azure Foundry's Anthropic endpoint).

### Configuration Separation

Understanding where each configuration lives:
Configure HiChat Client

Create or ensure `clients/hichat/.env` exists with the Claude OAuth settings:

```bash
cd clients/hichat
# Copy from example if needed
cp .env.example .env
# Edit .env to match your settings
```

**Note**: The `.env` file should be in `clients/hichat/.env` (same directory as `main.py`). This works regardless of where you run the command from.

### 2. Start HiChat

```bash
cd clients/hichat
python main.py
```

### 3. Authenticate with Claude

1. Click the **"⚡ Use Claude"** button in the HiChat header
2. Your browser will open to console.anthropic.com
3. Sign in with your company SSO credentials
4. After successful authentication:
   - The button will change to **"✓ Claude Active"** (green)
   - Claude models will appear in the model dropdown
   - You can now select and use Claude models

### 4
### 2. Authenticate with Claude

1. Click the **"⚡ Use Claude"** button in the HiChat header
2. Your browser will open to console.anthropic.com
3. Sign in with your company SSO credentials
4. After successful authentication:
   - The button will change to **"✓ Claude Active"** (green)
   - Claude models will appear in the model dropdown
   - You can now select and use Claude models

### 3. Select a Claude Model

After authentication, Claude models will be available in the model dropdown, separated from Azure models by a divider line.

### 5. Start Chatting

Select a Claude model and start sending messages. The system will automatically:
- Use your Claude authentication token
- Route requests to the Claude API
- Handle tool calling and RAG operations

### 6. Sign Out (Optional)

Click the **"✓ Claude Active"** button again to sign out from Claude. This will:
- Clear cached tokens
- Remove Claude models from the dropdown
- Preserve your Azure Foundry authentication

## Token Management

### Token Caching

Claude tokens are cached in `~/.llmcrawl/claude_tokens.json` and include:
- **Access Token**: Short-lived (1 hour), used for API calls
- **Refresh Token**: Long-lived, used to obtain new access tokens

### Automatic Refresh

The system automatically refreshes expired access tokens using the refresh token. You won't need to re-authenticate unless:
- The refresh token expires (typically 14-30 days)
- Company SSO policies require re-authentication
- You explicitly sign out

### Token Security

- Tokens are stored locally on your machine only
- Never shared with the gateway service beyond the active request
- Each request includes the token in the Authorization header
- Gateway validates and uses tokens only for that specific request

## How It Works: Authentication Flow

### Initial Authentication

```
1. User clicks "Use Claude" button
2. HiChat generates PKCE challenge (code_verifier + code_challenge)
3. Browser opens to console.anthropic.com with challenge
4. User signs in with company SSO
5. Anthropic redirects to localhost:54545 with auth code
6. HiChat exchanges code for tokens using PKCE verifier
7. Tokens saved locally and returned to UI
```

### Making API Calls

```
1. User selects Claude model and sends message
2. HiChat checks token validity
   - If expired: Refresh using refresh_token
   - If refresh fails: Re-authenticate with browser
3. Include Bearer token in request to gateway
4. Add X-Provider-Auth: claude header to identify provider
5. Gateway middleware extracts token and provider
6. LLM client routes to _claude_chat_completion
7. Call Claude API with Bearer token
8. Return response to user
```

## Comparison: Azure Foundry vs Claude

| Feature | Azure Foundry (Anthropic) | Claude Code (Direct) |
|---------|---------------------------|----------------------|
| **Authentication** | MSAL (Microsoft) | OAuth PKCE (Anthropic) |
| **Provider Type** | `anthropic` | `claude` |
| **Endpoint** | Azure AI Foundry | api.anthropic.com |
| **Token Source** | Azure AD | Claude Console |
| **Models** | Azure-hosted Anthropic | Latest Claude models |
| **Use Case** | Enterprise Azure integration | Direct Claude access |

## Troubleshooting

### Authentication Fails

**Symptom**: Browser opens but authentication fails with error

**Solutions**:
1. Check that your company allows access to console.anthropic.com
2. Verify CLAUDE_CLIENT_ID matches the official Claude CLI client ID
3. Ensure port 54545 is not blocked by firewall
4. Try clearing cached tokens: `rm ~/.llmcrawl/claude_tokens.json`

### Models Not Appearing

**Symptom**: After authentication, Claude models don't show in dropdown

**Solutions**:
1. Check browser console for JavaScript errors
2. Verify `LLM_MODELS` configuration includes `provider_type: "claude"`
3. Refresh the page and re-authenticate
4. Check HiChat server logs for errors

### 401 Authentication Error

**Symptom**: "Claude authentication failed" error when making requests

**Solutions**:
1. Re-authenticate by clicking "Use Claude" button
2. Check if token expired (happens after ~1 hour without refresh)
3. Verify network can reach api.anthropic.com
4. Check gateway logs for token validation errors

### Token Refresh Fails

**Symptom**: Prompted to re-authenticate frequently

**Solutions**:
1. This may be due to company SSO policies requiring fresh login
2. Check if refresh token expired (typically 14-30 days)
3. Verify CLAUDE_SCOPES includes all necessary permissions
4. Contact IT if company policies are too restrictive

## API Reference

### HiChat Claude Auth Endpoints

#### GET `/api/claude/auth/status`
Returns Claude authentication status

**Response**:
```json
{
  "enabled": true,
  "authenticated": true
}
```

#### POST `/api/claude/auth/login`
Triggers Claude OAuth browser flow

**Response**:
```json
{
  "success": true,
  "message": "Successfully authenticated with Claude Code"
}
```

#### POST `/api/claude/auth/logout`
Signs out from Claude (clears cached tokens)

**Response**:
```json
{
  "success": true
}
```

#### GET `/api/claude/models`
Returns available Claude models

**Response**:
```json
{
  "models": [
    {
      "name": "claude-sonnet-4",
      "display_name": "Claude Sonnet 4",
      "provider_type": "claude",
      "max_output_tokens": 64000
    }
  ]
}
```

## Files Modified

### New Files
- `clients/hichat/claude_auth.py` - Claude OAuth PKCE authentication client
- `docs/CLAUDE_INTEGRATION.md` - This documentation

### Modified Files
- `deploy/.env` - Added Claude configuration variables
- `clients/hichat/main.py` - Added Claude auth endpoints and token handling
- `clients/hichat/static/index.html` - Added "Use Claude" button
- `clients/hichat/static/styles.css` - Added Claude button styles
- `clients/hichat/static/app.js` - Added Claude auth UI logic
- `clients/hichat/requirements.txt` - Added requests library
- `gateway/utils/token_context.py` - Extended to support multiple providers
- `gateway/main.py` - Updated middleware to handle X-Provider-Auth header
- `gateway/llm/client.py` - Added _claude_chat_completion method

## Security Considerations

1. **Token Storage**: Tokens are stored in plaintext on local filesystem. Consider encrypting for production use.

2. **Token Transmission**: Tokens are sent over HTTPS to gateway. Ensure TLS is properly configured in production.

3. **Token Scope**: Claude OAuth scopes grant significant permissions. Review and restrict as needed.

4. **Client ID**: Using the official Claude CLI client ID means token rotation affects all users. Consider registering your own OAuth app for production.

5. **CORS**: Gateway allows all origins by default. Restrict in production to specific domains.

## Best Practices

1. **Environment Separation**: Use different Claude OAuth apps for dev/staging/production

2. **Token Rotation**: Implement token rotation policy aligned with company security requirements

3. **Logging**: Monitor authentication logs for suspicious activity

4. **Rate Limiting**: Implement rate limiting on Claude auth endpoints to prevent abuse

5. **Error Handling**: Always handle token expiration gracefully and prompt for re-authentication

## Future Enhancements

- [ ] Custom OAuth app registration (instead of using Claude CLI app)
- [ ] Token encryption at rest
- [ ] Multi-user support with user-specific token storage
- [ ] Claude streaming support
- [ ] Admin dashboard for token management
- [ ] Integration with company identity provider (beyond SSO)

## Support

For issues related to:
- **Claude Authentication**: Check console.anthropic.com documentation
- **OAuth Flow**: Review OAuth 2.0 PKCE specification
- **LLMCrawl Integration**: File an issue in the LLMCrawl repository
- **Company SSO**: Contact your IT department

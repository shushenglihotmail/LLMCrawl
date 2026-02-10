# Troubleshooting Azure Authentication Issues

## "Invalid OAuth Request - Missing state parameter" Error

This error occurs when the Azure AD app registration is not properly configured for public client authentication flows.

### Root Cause

MSAL's interactive authentication requires specific redirect URI configuration. When these aren't set up correctly in Azure AD, the OAuth flow fails with state parameter errors.

### Solution: Configure Azure AD App Registration

#### 1. Open Azure Portal

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** > **App registrations**
3. Find your app (Client ID: from `ENTRA_CLIENT_ID` in `.env`)

#### 2. Configure Redirect URIs

1. Go to **Authentication** section
2. Click **+ Add a platform**
3. Select **Mobile and desktop applications**
4. Add these redirect URIs:
   ```
   http://localhost
   http://localhost:8765
   ```
5. Click **Configure**

#### 3. Enable Public Client Flows

1. Still in **Authentication** section
2. Scroll down to **Advanced settings**
3. Find **Allow public client flows**
4. Set to **Yes**
5. Click **Save**

#### 4. Verify API Permissions

1. Go to **API permissions** section
2. Ensure the Azure Foundry scope is added:
   - Click **+ Add a permission**
   - Choose **APIs my organization uses**
   - Search for your Azure Foundry resource
   - Select **Delegated permissions**
   - Add the scope (e.g., `user_impersonation` or `.default`)
3. Click **Grant admin consent for [Your Organization]** (if you have admin rights)

### Alternative: Use Different Authentication Method

If you can't modify the Azure AD app registration, you can use device code flow instead:

**Option 1: Modify code to use device code flow**

Edit the authentication call to allow device code:
```python
token = auth_client.get_token(
    force_interactive=False,
    allow_device_code=True  # Enable device code fallback
)
```

**Option 2: Use environment variable**
```env
# In .env file
AUTH_METHOD=device_code
```

Device code flow doesn't require browser redirects and works in restricted environments.

## HiChat Won't Stop (Ctrl+C doesn't work)

This happens when authentication is blocking the server.

### Fixed in Latest Version

The latest code changes prevent blocking:
1. Server starts even if auth config is missing
2. Authentication is deferred to first request
3. Ctrl+C now properly interrupts authentication flows

### If Still Stuck

**Immediate fix:**
1. Close the browser window showing the sign-in page
2. In terminal, press Ctrl+C multiple times
3. If still stuck, close the terminal window

**Prevention:**
1. Update to latest code (includes fixes above)
2. Configure Azure AD properly (see above)
3. Use device code flow as fallback

## Testing Authentication Setup

### Test 1: Verify Environment Variables

```bash
cd clients/hichat
python -c "
from dotenv import load_dotenv
import os
load_dotenv()
print('ENTRA_CLIENT_ID:', os.getenv('ENTRA_CLIENT_ID'))
print('ENTRA_TENANT_ID:', os.getenv('ENTRA_TENANT_ID'))
print('AZURE_FOUNDRY_SCOPE:', os.getenv('AZURE_FOUNDRY_SCOPE'))
"
```

All three should print values (not `None`).

### Test 2: Test MSAL Authentication Directly

```bash
cd clients/hichat
python -c "
import logging
logging.basicConfig(level=logging.INFO)
from msal_auth import create_auth_client_from_env

try:
    client = create_auth_client_from_env()
    print('✓ Auth client created successfully')

    # Try silent token acquisition only (won't open browser)
    result = client.acquire_token_silent()
    if result:
        print('✓ Found cached token')
    else:
        print('ℹ No cached token (will need to sign in)')
except Exception as e:
    print(f'✗ Error: {e}')
"
```

### Test 3: Test Interactive Authentication

```bash
cd clients/hichat
python msal_auth.py
```

This will:
1. Try to open browser for sign-in
2. Show any authentication errors
3. If successful, display token info

## Common Error Messages and Solutions

### "ENTRA_CLIENT_ID environment variable is required"

**Solution:** Create `clients/hichat/.env` file with required variables:
```env
ENTRA_CLIENT_ID=<your-app-client-id>
ENTRA_TENANT_ID=<your-tenant-id>
AZURE_FOUNDRY_SCOPE=https://cognitiveservices.azure.com/.default
```

### "AADSTS65001: The user or administrator has not consented"

**Solution:**
1. Admin needs to grant consent in Azure portal
2. Or users need to consent individually on first sign-in
3. See step 4 in "Configure Azure AD App Registration" above

### "AADSTS7000218: The request body must contain the following parameter: 'client_assertion' or 'client_secret'"

**Solution:** Your app is configured as Confidential Client but should be Public Client:
1. Go to Azure portal > App registration > Authentication
2. Enable "Allow public client flows" = Yes
3. Save changes

### Browser opens but shows error page

**Solution:**
1. Check Azure app configuration (steps above)
2. Verify redirect URIs are exactly: `http://localhost:8765`
3. Ensure app type is "Mobile and desktop applications"

### "Connection refused" or "Cannot connect to localhost"

**Solution:**
1. Port 8765 might be blocked by firewall
2. Check Windows Defender Firewall settings
3. Try running as administrator

## Getting Help

### Check Logs

HiChat logs authentication details. Look for:
```
INFO - Starting interactive authentication flow
INFO - A browser window will open...
ERROR - Authentication failed: [error details]
```

### Information to Provide

When asking for help, include:
1. Full error message from browser
2. Log output from terminal
3. Azure AD app registration configuration (screenshot of Authentication page)
4. Contents of `.env` file (REDACT actual client IDs)

### Contact

- **Azure AD Issues**: Contact your Azure administrator
- **HiChat Issues**: File an issue in LLMCrawl repository
- **MSAL Library**: Check [MSAL Python documentation](https://github.com/AzureAD/microsoft-authentication-library-for-python)

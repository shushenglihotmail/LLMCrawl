# Authentication for Internal Sites

This guide explains how to configure FireCrawl to crawl internal sites that require authentication.

## Table of Contents
- [Authentication Methods](#authentication-methods)
- [Configuration](#configuration)
- [Headers-Based Authentication](#headers-based-authentication)
- [Cookie-Based Authentication](#cookie-based-authentication)
- [Basic Authentication](#basic-authentication)
- [OAuth/Token Authentication](#oauthtoken-authentication)
- [Custom Authentication](#custom-authentication)
- [Testing Authentication](#testing-authentication)
- [Troubleshooting](#troubleshooting)

## Authentication Methods

FireCrawl supports several authentication methods for accessing protected content:

1. **HTTP Headers** - Custom headers (API keys, tokens)
2. **Cookies** - Session cookies
3. **Basic Auth** - Username/password in Authorization header
4. **Bearer Tokens** - JWT or OAuth tokens
5. **Custom Scripts** - JavaScript for complex authentication flows

## Configuration

### 1. Environment Variables

Add authentication configuration to your `.env` file:

```bash
# FireCrawl Authentication
FIRECRAWL_AUTH_TYPE=headers  # headers, cookies, basic, bearer, custom
FIRECRAWL_AUTH_HEADERS={}    # JSON string of custom headers
FIRECRAWL_AUTH_COOKIES={}    # JSON string of cookies
FIRECRAWL_AUTH_USERNAME=     # For basic auth
FIRECRAWL_AUTH_PASSWORD=     # For basic auth
FIRECRAWL_AUTH_TOKEN=        # For bearer token auth
```

### 2. Update FireCrawl Client

Modify `crawler/clients/firecrawl.py` to support authentication:

```python
# Add to __init__ method
self.auth_type = os.getenv("FIRECRAWL_AUTH_TYPE", "none")
self.auth_headers = self._parse_json_env("FIRECRAWL_AUTH_HEADERS", {})
self.auth_cookies = self._parse_json_env("FIRECRAWL_AUTH_COOKIES", {})
self.auth_username = os.getenv("FIRECRAWL_AUTH_USERNAME", "")
self.auth_password = os.getenv("FIRECRAWL_AUTH_PASSWORD", "")
self.auth_token = os.getenv("FIRECRAWL_AUTH_TOKEN", "")

def _parse_json_env(self, key: str, default: dict) -> dict:
    """Parse JSON from environment variable."""
    import json
    value = os.getenv(key, "")
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in {key}")
        return default
```

## Headers-Based Authentication

Best for: API keys, custom authentication tokens, internal service authentication

### Configuration

```bash
# .env
FIRECRAWL_AUTH_TYPE=headers
FIRECRAWL_AUTH_HEADERS='{"X-API-Key": "your-api-key", "X-Custom-Header": "value"}'
```

### Implementation

Update `_crawl_single_url` method:

```python
async def _crawl_single_url(self, url_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    url = url_data.get("url")
    if not url:
        return None

    try:
        crawl_params = {
            "url": url,
            "formats": ["markdown", "html"],
            "onlyMainContent": True,
            "includeTags": ["title", "meta"],
            "excludeTags": ["script", "style", "nav", "footer"],
            "waitFor": 1000,
        }

        # Add authentication headers
        if self.auth_type == "headers" and self.auth_headers:
            crawl_params["headers"] = self.auth_headers

        response = await self.client.post(
            urljoin(self.base_url, "/v1/scrape"),
            json=crawl_params
        )
        # ... rest of the method
```

### Example Use Cases

**Corporate Intranet:**
```bash
FIRECRAWL_AUTH_TYPE=headers
FIRECRAWL_AUTH_HEADERS='{"X-Employee-Token": "emp_abc123xyz", "X-Department": "engineering"}'
```

**Internal Wiki:**
```bash
FIRECRAWL_AUTH_TYPE=headers
FIRECRAWL_AUTH_HEADERS='{"Authorization": "ApiKey your-wiki-api-key"}'
```

**Custom SSO System:**
```bash
FIRECRAWL_AUTH_TYPE=headers
FIRECRAWL_AUTH_HEADERS='{"X-SSO-Token": "token123", "X-Tenant": "company-name"}'
```

## Cookie-Based Authentication

Best for: Session-based authentication, web applications requiring login

### Configuration

```bash
# .env
FIRECRAWL_AUTH_TYPE=cookies
FIRECRAWL_AUTH_COOKIES='{"session_id": "abc123", "auth_token": "xyz789"}'
```

### How to Get Cookies

1. **Using Browser DevTools:**
   - Login to your internal site
   - Open DevTools (F12) → Application/Storage tab
   - Copy cookies under "Cookies" section

2. **Using curl:**
   ```bash
   curl -i https://internal-site.com/login -d "username=user&password=pass"
   # Look for Set-Cookie headers
   ```

3. **Using Python:**
   ```python
   import requests
   response = requests.post('https://internal-site.com/login',
                           data={'username': 'user', 'password': 'pass'})
   print(response.cookies.get_dict())
   ```

### Implementation

```python
async def _crawl_single_url(self, url_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    crawl_params = {
        "url": url,
        # ... other params
    }

    # Add authentication cookies
    if self.auth_type == "cookies" and self.auth_cookies:
        crawl_params["cookies"] = self.auth_cookies

    response = await self.client.post(
        urljoin(self.base_url, "/v1/scrape"),
        json=crawl_params
    )
    # ... rest of the method
```

### Example Use Cases

**Confluence/Jira:**
```bash
FIRECRAWL_AUTH_TYPE=cookies
FIRECRAWL_AUTH_COOKIES='{"JSESSIONID": "12345ABC", "atlassian.xsrf.token": "xyz"}'
```

**SharePoint:**
```bash
FIRECRAWL_AUTH_TYPE=cookies
FIRECRAWL_AUTH_COOKIES='{"FedAuth": "token1", "rtFa": "token2"}'
```

## Basic Authentication

Best for: Simple username/password protected sites, staging environments

### Configuration

```bash
# .env
FIRECRAWL_AUTH_TYPE=basic
FIRECRAWL_AUTH_USERNAME=admin
FIRECRAWL_AUTH_PASSWORD=secure_password
```

### Implementation

```python
async def _crawl_single_url(self, url_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    crawl_params = {
        "url": url,
        # ... other params
    }

    # Add Basic Authentication
    if self.auth_type == "basic" and self.auth_username and self.auth_password:
        import base64
        credentials = f"{self.auth_username}:{self.auth_password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        crawl_params["headers"] = {
            "Authorization": f"Basic {encoded}"
        }

    response = await self.client.post(
        urljoin(self.base_url, "/v1/scrape"),
        json=crawl_params
    )
    # ... rest of the method
```

### Example Use Cases

**Staging Environment:**
```bash
FIRECRAWL_AUTH_TYPE=basic
FIRECRAWL_AUTH_USERNAME=staging_user
FIRECRAWL_AUTH_PASSWORD=staging_pass
```

**Internal Documentation:**
```bash
FIRECRAWL_AUTH_TYPE=basic
FIRECRAWL_AUTH_USERNAME=docs_reader
FIRECRAWL_AUTH_PASSWORD=ReadOnly123
```

## OAuth/Token Authentication

Best for: Modern APIs, OAuth2 protected resources, JWT-based systems

### Configuration

```bash
# .env
FIRECRAWL_AUTH_TYPE=bearer
FIRECRAWL_AUTH_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Implementation

```python
async def _crawl_single_url(self, url_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    crawl_params = {
        "url": url,
        # ... other params
    }

    # Add Bearer Token
    if self.auth_type == "bearer" and self.auth_token:
        crawl_params["headers"] = {
            "Authorization": f"Bearer {self.auth_token}"
        }

    response = await self.client.post(
        urljoin(self.base_url, "/v1/scrape"),
        json=crawl_params
    )
    # ... rest of the method
```

### Token Refresh

For tokens that expire, implement refresh logic:

```python
class FirecrawlClient:
    def __init__(self):
        # ... existing init code
        self.token_expiry = None
        self.refresh_token = os.getenv("FIRECRAWL_REFRESH_TOKEN", "")

    async def _ensure_valid_token(self):
        """Refresh token if expired."""
        if self.token_expiry and datetime.now() > self.token_expiry:
            await self._refresh_auth_token()

    async def _refresh_auth_token(self):
        """Refresh the authentication token."""
        if not self.refresh_token:
            return

        try:
            # Call your token refresh endpoint
            response = await self.client.post(
                "https://auth-server.com/refresh",
                json={"refresh_token": self.refresh_token}
            )
            data = response.json()
            self.auth_token = data["access_token"]
            self.token_expiry = datetime.now() + timedelta(seconds=data["expires_in"])
            logger.info("Successfully refreshed auth token")
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
```

### Example Use Cases

**GitHub API:**
```bash
FIRECRAWL_AUTH_TYPE=bearer
FIRECRAWL_AUTH_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

**Okta-Protected App:**
```bash
FIRECRAWL_AUTH_TYPE=bearer
FIRECRAWL_AUTH_TOKEN=eyJraWQiOiJ...
```

## Custom Authentication

Best for: Complex authentication flows, JavaScript-heavy login pages, 2FA systems

### Using Playwright Actions

FireCrawl supports custom actions via Playwright for complex authentication:

```bash
# .env
FIRECRAWL_AUTH_TYPE=custom
FIRECRAWL_AUTH_SCRIPT=./scripts/auth_login.js
```

### Example Authentication Script

Create `scripts/auth_login.js`:

```javascript
// auth_login.js - Login automation for internal site
module.exports = async (page) => {
  // Navigate to login page
  await page.goto('https://internal-site.com/login');

  // Fill login form
  await page.fill('input[name="username"]', process.env.AUTH_USERNAME);
  await page.fill('input[name="password"]', process.env.AUTH_PASSWORD);

  // Click login button
  await page.click('button[type="submit"]');

  // Wait for navigation
  await page.waitForNavigation();

  // Wait for authentication to complete
  await page.waitForSelector('.logged-in-indicator');

  // Return cookies for reuse
  const cookies = await page.context().cookies();
  return cookies;
};
```

### Implementation in Python

```python
async def _get_authenticated_cookies(self) -> Dict[str, str]:
    """Get cookies by running authentication script."""
    if not self.auth_script:
        return {}

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            # Run custom authentication script
            await page.goto(self.auth_url)
            await page.evaluate(open(self.auth_script).read())

            # Get cookies after authentication
            cookies = await page.context().cookies()
            await browser.close()

            return {c['name']: c['value'] for c in cookies}
    except Exception as e:
        logger.error(f"Custom authentication failed: {e}")
        return {}
```

### Example Use Cases

**SAML/SSO Authentication:**
```javascript
// Handle SAML redirect flow
await page.goto('https://internal-app.com');
await page.waitForURL('**/saml/login');
await page.fill('#username', process.env.SSO_USER);
await page.fill('#password', process.env.SSO_PASS);
await page.click('#login-button');
await page.waitForURL('https://internal-app.com/**');
```

**2FA with TOTP:**
```javascript
const speakeasy = require('speakeasy');

// Enter credentials
await page.fill('#username', process.env.AUTH_USERNAME);
await page.fill('#password', process.env.AUTH_PASSWORD);
await page.click('#login');

// Generate TOTP code
const token = speakeasy.totp({
  secret: process.env.TOTP_SECRET,
  encoding: 'base32'
});

// Enter 2FA code
await page.fill('#totp-code', token);
await page.click('#verify');
```

## Testing Authentication

### 1. Test Manually First

Before configuring FireCrawl, test authentication manually:

```bash
# Test with curl
curl -H "Authorization: Bearer your-token" \
     https://internal-site.com/api/content

# Test with cookies
curl -b "session_id=abc123" \
     https://internal-site.com/protected-page

# Test basic auth
curl -u username:password \
     https://internal-site.com/secure-docs
```

### 2. Test FireCrawl Directly

Test FireCrawl's scrape endpoint with authentication:

```bash
curl -X POST http://localhost:3002/v1/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://internal-site.com/protected",
    "headers": {
      "Authorization": "Bearer your-token"
    }
  }'
```

### 3. Test via Crawler Service

Test through the crawler API:

```powershell
$body = @{
    urls = @("https://internal-site.com/page1")
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8001/crawl" `
                  -Method Post `
                  -ContentType "application/json" `
                  -Body $body
```

### 4. Verify in Logs

Check logs for authentication issues:

```bash
# Check crawler logs
docker-compose logs crawler | grep -i "auth\|401\|403"

# Check FireCrawl logs
docker-compose logs firecrawl | grep -i "auth\|401\|403"
```

## Troubleshooting

### Common Issues

#### 1. 401 Unauthorized

**Symptom:** Getting 401 errors in logs

**Solutions:**
- Verify token/credentials are correct
- Check if token has expired
- Ensure headers are properly formatted
- Verify the authentication endpoint is correct

```bash
# Debug: Log the exact headers being sent
logger.info(f"Auth headers: {crawl_params.get('headers')}")
```

#### 2. 403 Forbidden

**Symptom:** Getting 403 errors despite authentication

**Solutions:**
- Check if user/token has required permissions
- Verify IP whitelist (if applicable)
- Check rate limits
- Ensure correct user-agent

```bash
# Add user-agent to headers
FIRECRAWL_AUTH_HEADERS='{"Authorization": "Bearer token", "User-Agent": "Mozilla/5.0"}'
```

#### 3. Cookies Not Working

**Symptom:** Session expires immediately

**Solutions:**
- Include all required cookies (session, csrf, etc.)
- Check cookie domain and path settings
- Verify cookie expiration
- Ensure cookies are being sent with requests

```python
# Debug: Log cookies being used
logger.info(f"Cookies: {crawl_params.get('cookies')}")
```

#### 4. CSRF Token Issues

**Symptom:** POST requests fail with CSRF error

**Solutions:**
- Extract CSRF token from page
- Include in headers or cookies
- Some sites require both cookie and header

```bash
# Include CSRF token
FIRECRAWL_AUTH_HEADERS='{"X-CSRF-Token": "token123"}'
FIRECRAWL_AUTH_COOKIES='{"csrf_token": "token123", "session_id": "abc"}'
```

#### 5. SSO/SAML Redirects

**Symptom:** Gets redirected to login page

**Solutions:**
- Use Playwright custom script for SSO flow
- Capture cookies after successful SSO login
- Some SSO requires JavaScript execution

### Debug Mode

Enable debug logging to see authentication details:

```bash
# .env
LOG_LEVEL=DEBUG
FIRECRAWL_DEBUG=true
```

Add debug logging to FireCrawl client:

```python
if os.getenv("FIRECRAWL_DEBUG", "").lower() == "true":
    logger.debug(f"Auth type: {self.auth_type}")
    logger.debug(f"Auth headers: {crawl_params.get('headers')}")
    logger.debug(f"Auth cookies: {crawl_params.get('cookies')}")
```

### Security Considerations

1. **Never commit credentials** to version control
2. **Use environment variables** for all secrets
3. **Rotate tokens regularly**
4. **Use least privilege** - only grant necessary permissions
5. **Monitor authentication logs** for suspicious activity
6. **Use HTTPS** for all internal sites
7. **Consider using secrets management** (AWS Secrets Manager, HashiCorp Vault)

### Example: Complete Setup for Internal Confluence

```bash
# .env
FIRECRAWL_AUTH_TYPE=cookies
FIRECRAWL_AUTH_COOKIES='{"JSESSIONID": "E4B2C1234567890", "atlassian.xsrf.token": "abc123xyz"}'

# Allow Confluence domain
ALLOWED_DOMAINS=confluence.company.com,sec.gov,reuters.com
```

Test query:
```powershell
$body = @{
    message = "What are the latest engineering docs from Confluence?"
    force_refresh = $true
    seed_urls = @("https://confluence.company.com/display/ENG/")
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/chat" `
                  -Method Post `
                  -ContentType "application/json" `
                  -Body $body
```

## Next Steps

1. **Identify your authentication method** (headers, cookies, basic, bearer, custom)
2. **Get credentials/tokens** (API key, session cookies, JWT, etc.)
3. **Configure `.env` file** with authentication settings
4. **Update FireCrawl client** with authentication logic
5. **Test manually** with curl or Postman
6. **Test via crawler API**
7. **Verify in end-to-end flow**
8. **Monitor logs** for issues

## Additional Resources

- [FireCrawl Documentation](https://docs.firecrawl.dev/)
- [Playwright Authentication](https://playwright.dev/docs/auth)
- [HTTP Authentication RFC](https://datatracker.ietf.org/doc/html/rfc7617)
- [OAuth 2.0 Specification](https://oauth.net/2/)

## Support

If you encounter issues not covered in this guide:
1. Check FireCrawl logs: `docker-compose logs firecrawl`
2. Check crawler logs: `docker-compose logs crawler`
3. Enable debug mode for detailed logging
4. Verify authentication works outside of FireCrawl first

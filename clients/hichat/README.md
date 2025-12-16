# HiChat Python Web Client

A lightweight Python web client for interacting with LLMCrawl gateway service.

## Features

- Modern web UI with markdown rendering
- Mermaid diagram support
- Multiple workflow support (General Chat, Code Analysis, Build System, File Explorer)
- Model selection from gateway
- Conversation history with save-to-markdown
- Fullscreen mode
- **Stop button** - Cancel ongoing requests with server-side cancellation support

## Installation

```bash
# From this directory
pip install -r requirements.txt

# Or install from LLMCrawl root
pip install -e ".[client]"
```

## Usage

```bash
# Start with defaults (port 8080, gateway http://localhost:8000)
python main.py

# With custom deploy directory (for development)
python main.py --deploy-dir ../../deploy

# Custom port
python main.py --port 3000

# Custom gateway URL
python main.py --gateway http://my-gateway:8000

# Don't auto-open browser
python main.py --no-browser

# All options
python main.py --deploy-dir ../../deploy --port 8080 --gateway http://localhost:8000 --host 0.0.0.0
```

## Environment Variables

HiChat automatically loads environment variables from a `.env` file in one of these locations (in order):
1. Custom deploy directory (if `--deploy-dir` specified)
2. Current working directory (`./env`)
3. llmcrawl-deploy folder (`./llmcrawl-deploy/.env`) - for wheel package deployment
4. User's home directory (`~/.llmcrawl/.env`)

### Configuration Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HICHAT_PORT` | 8080 | Web server port |
| `LLMCRAWL_GATEWAY_URL` | http://localhost:8000 | Gateway service URL |
| `ENTRA_CLIENT_ID` | (required) | Azure Entra ID client ID for authentication |
| `ENTRA_TENANT_ID` | (required) | Azure Entra ID tenant ID |
| `AZURE_FOUNDRY_SCOPE` | (required) | Azure Foundry API scope |

### Development Setup

For development from source, use the helper script:

```bash
# From repository root
.\scripts\start_hichat.ps1
```

This script automatically:
- Locates the deploy directory
- Changes to the HiChat directory
- Starts HiChat with `--deploy-dir` pointing to deploy folder

Or run manually:
```bash
cd clients/hichat
python main.py --deploy-dir ../../deploy
```

### Production Deployment (Wheel Package)

For production deployment using the wheel package:

1. **Option 1**: Place `.env` in `llmcrawl-deploy` folder (recommended):
```bash
mkdir -p llmcrawl-deploy
cp /path/to/deploy/.env llmcrawl-deploy/
hichat
```

2. **Option 2**: Create `.env` file in user's home directory:
```bash
mkdir -p ~/.llmcrawl
cat > ~/.llmcrawl/.env << EOF
ENTRA_CLIENT_ID=04b07795-8ddb-461a-bbee-02f9e1bf7b46
ENTRA_TENANT_ID=your-tenant-id
AZURE_FOUNDRY_SCOPE=https://cognitiveservices.azure.com/user_impersonation
EOF
hichat
```

3. **Option 3**: Use `--deploy-dir` flag:
```bash
hichat --deploy-dir /path/to/llmcrawl-deploy
```

4. **Option 4**: Place `.env` in current directory:
```bash
cd /path/to/deployment
cp /path/to/deploy/.env .
hichat
```

The client will automatically load the first `.env` file found.

## Requirements

- Python 3.9+
- LLMCrawl gateway running (see main LLMCrawl documentation)

## Architecture

```
┌─────────────────┐         ┌──────────────────┐
│   Browser UI    │◄───────►│  Python Server   │
│  (index.html)   │  HTTP   │    (main.py)     │
└─────────────────┘         └────────┬─────────┘
                                     │
                                     │ HTTP Proxy
                                     ▼
                            ┌──────────────────┐
                            │ LLMCrawl Gateway │
                            │    :8000         │
                            └──────────────────┘
```

The Python server:
1. Serves static files (HTML, CSS, JS)
2. Provides `/api/config` and `/api/models` endpoints
3. Proxies `/api/agent/execute` to the gateway's `/agent/chat`
4. Proxies `/api/agent/cancel/{conversation_id}` for request cancellation
5. Proxies `/api/agent/status/{conversation_id}` for status polling

## Stop Button Feature

During an ongoing request (while "Thinking..." is displayed), the "Clear Chat" button becomes a red "Stop" button. When clicked:

1. Client aborts the HTTP request
2. Sends cancel request to gateway (`POST /agent/cancel/{conversation_id}`)
3. Gateway marks the request as cancelled
4. Agent checks cancellation flag at checkpoints (before each tool execution)
5. Client polls status endpoint until agent is fully stopped
6. UI resets and button returns to "Clear Chat"

This ensures that both client and server-side operations are properly stopped, preventing duplicate requests and resource waste.

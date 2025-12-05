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

# Custom port
python main.py --port 3000

# Custom gateway URL
python main.py --gateway http://my-gateway:8000

# Don't auto-open browser
python main.py --no-browser

# All options
python main.py --port 8080 --gateway http://localhost:8000 --host 0.0.0.0
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HICHAT_PORT` | 8080 | Web server port |
| `LLMCRAWL_GATEWAY_URL` | http://localhost:8000 | Gateway service URL |

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

# HiChat Python Web Client

A lightweight Python web client for interacting with LLMCrawl gateway service.

## Features

- Modern web UI with markdown rendering
- Mermaid diagram support
- Multiple workflow support (General Chat, Code Analysis, Build System, File Explorer)
- Model selection from gateway
- Conversation history with save-to-markdown
- Fullscreen mode

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

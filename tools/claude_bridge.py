"""
Claude Bridge Service - HTTP bridge to Claude Code CLI.

Runs on the Windows host and accepts HTTP requests from the Docker-based
gateway, piping them through the Claude Code CLI subprocess.  This bypasses
the product-scoped API key restriction (the CLI is authorised to send
requests to Anthropic, even though direct API calls with the same key fail).

Architecture:
    Gateway (Docker/Linux) --HTTP--> Claude Bridge (Host/Windows:8006)
                                         --> subprocess --> claude.exe

Same pattern as the Windows Composition Bridge (port 8005).

Endpoints:
    POST /chat     - Chat completion via Claude CLI subprocess
    GET  /models   - List available models (via Anthropic API)
    GET  /health   - Health check
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("claude_bridge")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BRIDGE_PORT = int(os.getenv("CLAUDE_BRIDGE_PORT", "8006"))

# Per-model max output token defaults (Claude CLI doesn't accept max_tokens)
MODEL_TOKEN_LIMITS: Dict[str, int] = {
    "claude-opus-4-6": 32000,
    "claude-opus-4-5-20251101": 32000,
    "claude-opus-4-1-20250805": 32000,
    "claude-opus-4-20250514": 32000,
    "claude-sonnet-4-5-20250929": 64000,
    "claude-sonnet-4-20250514": 64000,
    "claude-haiku-4-5-20251001": 64000,
    "claude-3-5-haiku-20241022": 8192,
    "claude-3-haiku-20240307": 4096,
}

# Model alias mapping (short names → full names)
MODEL_ALIASES: Dict[str, str] = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-5-20250929",
    "haiku": "claude-haiku-4-5-20251001",
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


class ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    system_prompt: Optional[str] = None  # optional override


class ChatResponse(BaseModel):
    content: str
    role: str = "assistant"
    model: str
    finish_reason: str = "end_turn"
    usage: Dict[str, Any] = {}
    session_id: Optional[str] = None
    cost_usd: Optional[float] = None


class ModelInfo(BaseModel):
    name: str
    display_name: str
    max_output_tokens: int


# ---------------------------------------------------------------------------
# Claude CLI helpers
# ---------------------------------------------------------------------------

_claude_cli_path: Optional[str] = None


def find_claude_cli() -> Optional[str]:
    """Locate the Claude Code CLI executable."""
    global _claude_cli_path
    if _claude_cli_path:
        return _claude_cli_path

    candidates = [
        shutil.which("claude"),
        os.path.expanduser(r"~\.claude-cli\currentVersion\claude.exe"),
        os.path.expanduser(r"~\.claude-cli\2.1.2\claude.exe"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            _claude_cli_path = c
            return c
    return None


def get_api_key() -> Optional[str]:
    """Read primaryApiKey from ~/.claude.json (works for /v1/models listing)."""
    try:
        config_path = Path.home() / ".claude.json"
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return data.get("primaryApiKey")
    except Exception as e:
        logger.warning(f"Could not read ~/.claude.json: {e}")
    return None


def build_prompt(messages: List[ChatMessage]) -> tuple[Optional[str], str]:
    """
    Convert an OpenAI-style message list to (system_prompt, prompt_text).

    The Claude CLI -p flag expects a single text prompt.  Multi-turn history
    is serialised into a structured text block so Claude understands context.
    """
    system_parts: list[str] = []
    conversation_parts: list[str] = []

    for msg in messages:
        if msg.role == "system":
            if msg.content:
                system_parts.append(msg.content)
        elif msg.role == "user":
            conversation_parts.append(f"Human: {msg.content or ''}")
        elif msg.role == "assistant":
            text = msg.content or ""
            if msg.tool_calls:
                # Include tool calls as context
                for tc in msg.tool_calls:
                    fn = tc.get("function", {})
                    text += f"\n[Tool call: {fn.get('name', '?')}({fn.get('arguments', '')})]"
            conversation_parts.append(f"Assistant: {text}")
        elif msg.role == "tool":
            tid = msg.tool_call_id or "unknown"
            conversation_parts.append(f"Tool result (id={tid}): {msg.content or ''}")

    system_text = "\n".join(system_parts) if system_parts else None

    # Single user message → use it directly without the "Human:" prefix
    if len(conversation_parts) == 1 and conversation_parts[0].startswith("Human: "):
        prompt = conversation_parts[0][len("Human: ") :]
    else:
        prompt = "\n\n".join(conversation_parts)

    return system_text, prompt


def resolve_model(model: Optional[str]) -> Optional[str]:
    """Resolve model aliases, return None to let CLI use its default."""
    if not model:
        return None
    lower = model.lower()
    if lower in MODEL_ALIASES:
        return MODEL_ALIASES[lower]
    return model


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    cli = find_claude_cli()
    if cli:
        logger.info(f"Claude CLI found: {cli}")
    else:
        logger.error("Claude CLI not found! Bridge will not work.")
    yield


app = FastAPI(
    title="Claude Bridge",
    description="HTTP bridge from Docker gateway to Claude Code CLI",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    cli = find_claude_cli()
    return {
        "status": "healthy" if cli else "unhealthy",
        "cli_path": cli,
        "port": BRIDGE_PORT,
    }


@app.get("/models", response_model=List[ModelInfo])
async def list_models():
    """List available Claude models using the Anthropic API."""
    api_key = get_api_key()
    if not api_key:
        raise HTTPException(500, "No API key found in ~/.claude.json")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/models",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        models: list[ModelInfo] = []
        for m in data.get("data", []):
            mid = m.get("id", "")
            # Build a friendly display name
            display = mid.replace("-", " ").title()
            max_tokens = MODEL_TOKEN_LIMITS.get(mid, 8192)
            models.append(
                ModelInfo(name=mid, display_name=display, max_output_tokens=max_tokens)
            )

        # Sort by name
        models.sort(key=lambda m: m.name)
        return models

    except httpx.HTTPStatusError as e:
        logger.error(
            f"Model listing failed: {e.response.status_code} {e.response.text}"
        )
        raise HTTPException(
            e.response.status_code, f"Anthropic API error: {e.response.text}"
        )
    except Exception as e:
        logger.error(f"Model listing error: {e}")
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# Stream-JSON parser
# ---------------------------------------------------------------------------


def _parse_stream_json(
    stdout: str, fallback_model: Optional[str]
) -> tuple[str, str, dict, Optional[str], Optional[float]]:
    """Parse ``--output-format stream-json`` output from Claude CLI.

    stream-json emits one JSON object per line.  Key event types:

    * ``{"type": "assistant", "message": {"content": [{"type": "text", "text": "..."}], ...}}``
      — full assistant message (one per turn)
    * ``{"type": "result", "result": "...", "usage": {...}, ...}``
      — final summary (same as the old ``--output-format json`` blob)

    We concatenate all assistant-message text blocks across every turn so
    that multi-turn continuations are not lost.

    Returns:
        (content, model, usage_dict, session_id, cost_usd)
    """
    assistant_texts: list[str] = []
    used_model = fallback_model or "unknown"
    usage: dict[str, int] = {}
    session_id: Optional[str] = None
    cost_usd: Optional[float] = None
    num_turns = 0
    result_text: Optional[str] = None  # from the final "result" event

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = event.get("type")

        # --- Full assistant message (emitted once per turn) ---
        if etype == "assistant":
            msg = event.get("message", {})
            for block in msg.get("content", []):
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        assistant_texts.append(text)

        # --- Content-block delta (partial text chunk) ---
        elif etype == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                text = delta.get("text", "")
                if text:
                    # These are sub-message deltas; we already get full text
                    # from "assistant" events, so skip to avoid duplication.
                    pass

        # --- Final result summary ---
        elif etype == "result":
            result_text = event.get("result", "")
            num_turns = event.get("num_turns", 1)
            session_id = event.get("session_id")
            cost_usd = event.get("total_cost_usd")

            # Usage
            usage_raw = event.get("usage", {})
            usage = {
                "input_tokens": usage_raw.get("input_tokens", 0),
                "output_tokens": usage_raw.get("output_tokens", 0),
                "cache_creation_input_tokens": usage_raw.get(
                    "cache_creation_input_tokens", 0
                ),
                "cache_read_input_tokens": usage_raw.get("cache_read_input_tokens", 0),
            }

            # Model
            model_usage = event.get("modelUsage", {})
            if model_usage:
                used_model = next(iter(model_usage.keys()), used_model)

            if event.get("is_error"):
                error_msg = event.get("result", "Unknown CLI error")
                logger.error(f"Claude CLI reported error: {error_msg}")
                raise HTTPException(502, f"Claude CLI error: {error_msg}")

    # Decide which content to use:
    # - If we captured assistant texts from multiple turns, concatenate them
    #   (this is the whole point — prevents losing first-turn content).
    # - If only one turn or no assistant events were captured, fall back to
    #   the result text from the summary event.
    if assistant_texts:
        content = "\n\n".join(assistant_texts)
        if num_turns > 1:
            logger.info(
                f"Multi-turn response: {num_turns} turns, "
                f"{len(assistant_texts)} assistant blocks concatenated "
                f"({len(content)} chars)"
            )
    elif result_text is not None:
        content = result_text
        logger.info(f"Using result text from summary event ({len(content)} chars)")
    else:
        content = stdout.strip()
        logger.warning("No structured content found, using raw stdout")

    return content, used_model, usage, session_id, cost_usd


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a chat completion through the Claude Code CLI subprocess."""
    cli = find_claude_cli()
    if not cli:
        raise HTTPException(500, "Claude CLI not found")

    # Build the prompt from messages
    override_system = request.system_prompt
    system_text, prompt_text = build_prompt(request.messages)
    if override_system:
        system_text = override_system

    if not prompt_text.strip():
        raise HTTPException(400, "No prompt text derived from messages")

    # Resolve model
    model = resolve_model(request.model)

    # Build command — use stream-json to capture ALL turns.
    # With --output-format json the CLI returns only the LAST turn's text
    # in "result".  When a model like Opus hits the per-API-call output
    # token limit, the CLI silently does continuation turns and the first
    # turn's content is lost.  stream-json emits every message so we can
    # concatenate all assistant text.
    cmd = [cli, "-p", "--output-format", "stream-json", "--verbose"]
    if model:
        cmd.extend(["--model", model])
    if system_text:
        cmd.extend(["--system-prompt", system_text])
    # Disable session persistence for stateless API-like behaviour
    cmd.append("--no-session-persistence")
    # Disable all built-in CLI tools (file read, web search, etc.) so that
    # Claude outputs structured JSON tool calls for the gateway to execute
    # instead of trying to run tools itself.
    cmd.extend(["--tools", ""])

    logger.info(
        f"Claude CLI call: model={model or 'default'}, "
        f"prompt_len={len(prompt_text)}, system_len={len(system_text or '')}"
    )

    # Run the subprocess.  Use stdin for the prompt to avoid command-line
    # length limits on Windows (max ~32K chars).
    # Force UTF-8 encoding to avoid Windows cp1252 codec errors.
    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            input=prompt_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,  # 30 min timeout for slow models like Opus
            cwd=os.getcwd(),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        logger.error("Claude CLI timed out after 1800s")
        raise HTTPException(504, "Claude CLI subprocess timed out")
    except Exception as e:
        logger.error(f"Claude CLI subprocess error: {e}")
        raise HTTPException(500, f"Subprocess error: {e}")

    duration = time.time() - start
    logger.info(f"Claude CLI finished in {duration:.1f}s (exit={result.returncode})")

    if result.returncode != 0:
        stderr = result.stderr[:500] if result.stderr else "no stderr"
        logger.error(f"Claude CLI failed: {stderr}")
        raise HTTPException(502, f"Claude CLI error: {stderr}")

    # Guard against None stdout (e.g. encoding errors)
    stdout = result.stdout or ""
    if not stdout.strip():
        stderr = result.stderr[:500] if result.stderr else "no stderr"
        logger.error(f"Claude CLI returned empty stdout. stderr: {stderr}")
        raise HTTPException(502, f"Claude CLI returned no output. stderr: {stderr}")

    # Parse stream-json output: each line is a JSON event.
    # We collect text from ALL assistant messages across all turns so that
    # multi-turn continuations (Opus hitting output token limit) are merged.
    content, used_model, usage, session_id, cost_usd = _parse_stream_json(stdout, model)

    logger.info(
        f"Claude CLI result: model={used_model}, content_len={len(content)}, "
        f"usage={usage}"
    )

    if not content:
        logger.warning("No assistant content extracted from stream-json")

    return ChatResponse(
        content=content,
        model=used_model,
        finish_reason="end_turn",
        usage=usage,
        session_id=session_id,
        cost_usd=cost_usd,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    logger.info(f"Starting Claude Bridge on port {BRIDGE_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=BRIDGE_PORT)


if __name__ == "__main__":
    main()

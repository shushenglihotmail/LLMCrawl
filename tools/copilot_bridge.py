"""
Copilot Bridge Service - HTTP bridge to GitHub Copilot CLI.

Runs on the Windows host and accepts HTTP requests, piping them through
the Copilot CLI subprocess.  Same pattern as the Claude Bridge.

Architecture:
    Gateway --HTTP--> Copilot Bridge (Host:8009)
                           --> subprocess --> copilot.exe

Endpoints:
    POST /chat     - Chat completion via Copilot CLI subprocess
    GET  /models   - List known models (hardcoded — no discovery API)
    GET  /health   - Health check
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("copilot_bridge")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BRIDGE_PORT = int(os.getenv("COPILOT_BRIDGE_PORT", "8009"))


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
    system_prompt: Optional[str] = None


class ChatResponse(BaseModel):
    content: str
    role: str = "assistant"
    model: str
    finish_reason: str = "end_turn"
    usage: Dict[str, Any] = {}


class ModelInfo(BaseModel):
    name: str
    display_name: str


# ---------------------------------------------------------------------------
# Copilot CLI helpers
# ---------------------------------------------------------------------------

_copilot_cli_path: Optional[str] = None


def find_copilot_cli() -> Optional[str]:
    """Locate the GitHub Copilot CLI executable."""
    global _copilot_cli_path
    if _copilot_cli_path:
        return _copilot_cli_path

    # Environment variable
    env_path = os.environ.get("COPILOT_CLI_PATH")
    if env_path and os.path.isfile(env_path):
        _copilot_cli_path = env_path
        return env_path

    # System PATH
    which = shutil.which("copilot")
    if which:
        _copilot_cli_path = which
        return which

    # Windows default locations
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(local_app_data, "Microsoft", "WinGet", "Links", "copilot.exe"),
        os.path.expanduser(r"~\.copilot\bin\copilot.exe"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            _copilot_cli_path = c
            return c

    return None


def build_prompt(messages: List[ChatMessage]) -> tuple[Optional[str], str]:
    """Convert OpenAI-style message list to (system_prompt, prompt_text)."""
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
            conversation_parts.append(f"Assistant: {text}")
        elif msg.role == "tool":
            tid = msg.tool_call_id or "unknown"
            conversation_parts.append(f"Tool result (id={tid}): {msg.content or ''}")

    system_text = "\n".join(system_parts) if system_parts else None

    if len(conversation_parts) == 1 and conversation_parts[0].startswith("Human: "):
        prompt = conversation_parts[0][len("Human: ") :]
    else:
        prompt = "\n\n".join(conversation_parts)

    return system_text, prompt


def _parse_copilot_jsonl(
    stdout: str, fallback_model: Optional[str]
) -> tuple[str, str, dict]:
    """Parse JSONL output from Copilot CLI."""
    assistant_texts: list[str] = []
    used_model = fallback_model or "unknown"
    total_output_tokens = 0

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = event.get("type")

        if etype == "session.tools_updated":
            data = event.get("data", {})
            if data.get("model"):
                used_model = data["model"]

        elif etype == "assistant.message":
            if event.get("ephemeral"):
                continue
            data = event.get("data", {})
            content = data.get("content", "")
            if content:
                assistant_texts.append(content)
            total_output_tokens += data.get("outputTokens", 0)

        elif etype == "result":
            exit_code = event.get("exitCode", 0)
            if exit_code != 0:
                raise HTTPException(502, f"Copilot CLI exited with code {exit_code}")

    if assistant_texts:
        content = "\n\n".join(assistant_texts)
    else:
        content = stdout.strip()
        logger.warning("No structured content found, using raw stdout")

    usage = {"output_tokens": total_output_tokens, "total_tokens": total_output_tokens}
    return content, used_model, usage


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    cli = find_copilot_cli()
    if cli:
        logger.info(f"Copilot CLI found: {cli}")
    else:
        logger.error("Copilot CLI not found! Bridge will not work.")
    yield


app = FastAPI(
    title="Copilot Bridge",
    description="HTTP bridge from gateway to GitHub Copilot CLI",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    cli = find_copilot_cli()
    return {
        "status": "healthy" if cli else "unhealthy",
        "cli_path": cli,
        "port": BRIDGE_PORT,
    }


@app.get("/models", response_model=List[ModelInfo])
async def list_models():
    """Return known Copilot models (hardcoded — no discovery API)."""
    from gateway.llm.cli_providers import COPILOT_KNOWN_MODELS

    return [
        ModelInfo(name=name, display_name=display_name)
        for name, display_name in COPILOT_KNOWN_MODELS
    ]


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a chat completion through the Copilot CLI subprocess."""
    cli = find_copilot_cli()
    if not cli:
        raise HTTPException(500, "Copilot CLI not found")

    override_system = request.system_prompt
    system_text, prompt_text = build_prompt(request.messages)
    if override_system:
        system_text = override_system

    if not prompt_text.strip():
        raise HTTPException(400, "No prompt text derived from messages")

    # Copilot doesn't have --system-prompt, prepend to prompt
    if system_text:
        full_prompt = (
            f"[System Instructions]\n{system_text}\n"
            f"[End System Instructions]\n\n{prompt_text}"
        )
    else:
        full_prompt = prompt_text

    model = request.model

    cmd = [
        cli,
        "-p",
        full_prompt,
        "--output-format",
        "json",
        "--available-tools=",  # Disable built-in tools (pure LLM mode)
        "-s",
        "--no-custom-instructions",
    ]
    if model:
        cmd.extend(["--model", model])

    logger.info(
        f"Copilot CLI call: model={model or 'default'}, "
        f"prompt_len={len(full_prompt)}"
    )

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
            cwd=os.getcwd(),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        logger.error("Copilot CLI timed out after 1800s")
        raise HTTPException(504, "Copilot CLI subprocess timed out")
    except Exception as e:
        logger.error(f"Copilot CLI subprocess error: {e}")
        raise HTTPException(500, f"Subprocess error: {e}")

    duration = time.time() - start
    logger.info(f"Copilot CLI finished in {duration:.1f}s (exit={result.returncode})")

    if result.returncode != 0:
        stderr = result.stderr[:500] if result.stderr else ""
        detail = stderr or (result.stdout[:500] if result.stdout else "no output")
        logger.error(f"Copilot CLI failed (exit={result.returncode}): {detail}")
        raise HTTPException(502, f"Copilot CLI error: {detail}")

    stdout = result.stdout or ""
    if not stdout.strip():
        stderr = result.stderr[:500] if result.stderr else "no stderr"
        raise HTTPException(502, f"Copilot CLI returned no output. stderr: {stderr}")

    content, used_model, usage = _parse_copilot_jsonl(stdout, model)

    logger.info(f"Copilot CLI result: model={used_model}, content_len={len(content)}")

    return ChatResponse(
        content=content,
        model=used_model,
        finish_reason="end_turn",
        usage=usage,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=BRIDGE_PORT)

"""
Direct CLI providers for Claude and Copilot.

Spawns CLI executables as subprocesses, avoiding the HTTP bridge layer.
The gateway runs on the host and can call CLIs directly.

Each provider:
1. Discovers the CLI executable on the host
2. Builds the appropriate command line
3. Runs the subprocess with timeout
4. Parses the structured output (stream-json for Claude, JSONL for Copilot)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _clean_subprocess_env() -> dict[str, str]:
    """Build a clean env for CLI subprocesses.

    Strips NODE_OPTIONS and similar vars that can interfere with
    Node.js-based CLIs (Copilot, Claude) when the gateway process
    inherits them from uvicorn or other middleware.
    """
    # Build a clean env for Node.js-based CLI subprocesses.
    env = {}
    for k, v in os.environ.items():
        if k.upper() == "NODE_OPTIONS":
            logger.warning(f"Stripped {k}={v!r} from CLI subprocess env")
            continue
        env[k] = v
    env["PYTHONIOENCODING"] = "utf-8"
    # Log suspicious vars
    logger.info(f"Subprocess env NODE_OPTIONS present: {'NODE_OPTIONS' in env}")
    return env


# ---------------------------------------------------------------------------
# Shared: Prompt builder (converts OpenAI messages → single prompt)
# ---------------------------------------------------------------------------


def _truncate_tool_args(tool_name: str, args_str: str, max_len: int = 400) -> str:
    """Truncate tool call arguments for conversation history."""
    if len(args_str) <= max_len:
        return args_str
    try:
        args = json.loads(args_str)
        for key in list(args.keys()):
            val = args[key]
            if isinstance(val, str) and len(val) > 120:
                args[key] = val[:80] + f"...[{len(val)} chars truncated]"
        short = json.dumps(args, ensure_ascii=False)
        if len(short) <= max_len:
            return short
        return short[:max_len] + "...[truncated]"
    except (json.JSONDecodeError, TypeError):
        return args_str[:max_len] + "...[truncated]"


def build_prompt_from_messages(
    messages: List[Dict[str, Any]],
) -> tuple[Optional[str], str]:
    """Convert OpenAI-style message list to (system_prompt, prompt_text).

    The CLI ``-p`` flag expects a single text prompt.  Multi-turn history
    is serialised into structured text so the model understands context.
    """
    system_parts: list[str] = []
    conversation_parts: list[str] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content") or ""

        if role == "system":
            if content:
                system_parts.append(content)
        elif role == "user":
            conversation_parts.append(f"Human: {content}")
        elif role == "assistant":
            text = content
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function", {})
                args_str = _truncate_tool_args(
                    fn.get("name", ""), fn.get("arguments", "")
                )
                text += f"\n[Tool call: {fn.get('name', '?')}({args_str})]"
            conversation_parts.append(f"Assistant: {text}")
        elif role == "tool":
            tid = msg.get("tool_call_id", "unknown")
            conversation_parts.append(f"Tool result (id={tid}): {content}")

    system_text = "\n".join(system_parts) if system_parts else None

    if len(conversation_parts) == 1 and conversation_parts[0].startswith("Human: "):
        prompt = conversation_parts[0][len("Human: ") :]
    else:
        prompt = "\n\n".join(conversation_parts)

    return system_text, prompt


# ---------------------------------------------------------------------------
# Claude CLI Provider
# ---------------------------------------------------------------------------

# Curated Claude model list (matches Claude Code CLI /model list).
# The [1m] suffix activates 1M context window (same model, larger context).
# name = model ID passed to --model, display_name = shown in HiChat dropdown.
CLAUDE_KNOWN_MODELS: list[tuple[str, str]] = [
    ("sonnet", "Claude Sonnet 4.6"),
    ("sonnet[1m]", "Claude Sonnet 4.6 (1M context)"),
    ("opus", "Claude Opus 4.6"),
    ("opus[1m]", "Claude Opus 4.6 (1M context)"),
    ("haiku", "Claude Haiku 4.5"),
]


class ClaudeCLIProvider:
    """Runs Claude Code CLI as a subprocess for chat completions."""

    def __init__(self) -> None:
        self._cli_path: Optional[str] = self._find_cli()
        if self._cli_path:
            logger.info(f"Claude CLI found: {self._cli_path}")
        else:
            logger.info("Claude CLI not found on host")

    @property
    def cli_path(self) -> Optional[str]:
        return self._cli_path

    @property
    def available(self) -> bool:
        return self._cli_path is not None

    @staticmethod
    def _find_cli() -> Optional[str]:
        """Locate the Claude Code CLI executable.

        Prefers the PATH version (latest installed) over hardcoded locations.
        Resolves symlinks to avoid WinGet shim issues on Windows.
        """
        # Environment variable (highest priority)
        env_path = os.environ.get("CLAUDE_CLI_PATH")
        if env_path and os.path.isfile(env_path):
            return os.path.realpath(env_path)

        # System PATH — preferred, finds the latest installed version
        which = shutil.which("claude")
        if which:
            resolved = os.path.realpath(which)
            logger.debug(f"Claude CLI found on PATH: {which} -> {resolved}")
            return resolved

        # Windows default locations (fallback for older installations)
        candidates = [
            os.path.expanduser(r"~\.local\bin\claude.exe"),
            os.path.expanduser(r"~\.claude-cli\currentVersion\claude.exe"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return os.path.realpath(c)

        return None

    async def run_chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        effort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a chat completion through Claude CLI subprocess.

        Args:
            model: Model name (e.g. "claude-opus-4-6")
            messages: OpenAI-format message list
            system_prompt: Optional system prompt override (e.g. with tool defs)
            effort: Optional reasoning effort level (low, medium, high, max)

        Returns:
            Dict with content, model, usage, finish_reason
        """
        if not self._cli_path:
            raise RuntimeError("Claude CLI not found")

        # Build prompt from messages
        msg_system, prompt_text = build_prompt_from_messages(messages)
        system_text = system_prompt or msg_system

        if not prompt_text.strip():
            raise ValueError("No prompt text derived from messages")

        # Build command — model name is passed as-is to Claude CLI
        # (accepts aliases like "opus", "sonnet", "haiku" and suffixes like "[1m]")
        cmd = [self._cli_path, "-p", "--output-format", "stream-json", "--verbose"]
        if model:
            cmd.extend(["--model", model])
        if system_text:
            cmd.extend(["--system-prompt", system_text])
        if effort:
            # Claude CLI uses: low, medium, high, max
            claude_effort = "max" if effort == "xhigh" else effort
            cmd.extend(["--effort", claude_effort])
        cmd.append("--no-session-persistence")
        cmd.extend(["--tools", ""])  # Disable built-in tools

        logger.info(
            f"Claude CLI call: model={model or 'default'}, "
            f"prompt_len={len(prompt_text)}, system_len={len(system_text or '')}"
        )

        start = time.time()
        try:
            env = _clean_subprocess_env()
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                input=prompt_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1800,
                cwd=os.getcwd(),
                env=env,
            )
            stdout_raw = result.stdout or ""
            stderr_raw = result.stderr or ""
            returncode = result.returncode
        except subprocess.TimeoutExpired:
            logger.error("Claude CLI timed out after 1800s")
            raise RuntimeError("Claude CLI subprocess timed out")
        except Exception as e:
            logger.error(f"Claude CLI subprocess error: {e}")
            raise RuntimeError(f"Claude CLI subprocess error: {e}")

        duration = time.time() - start
        logger.info(f"Claude CLI finished in {duration:.1f}s (exit={returncode})")

        if returncode != 0:
            stderr = stderr_raw[:500] if stderr_raw else ""
            stdout_err = ""
            if not stderr and stdout_raw:
                for line in stdout_raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                        if evt.get("is_error") or evt.get("type") == "error":
                            stdout_err = (
                                evt.get("result", "")
                                or evt.get("error", {}).get("message", "")
                                or line
                            )
                            break
                    except (json.JSONDecodeError, AttributeError):
                        continue
                if not stdout_err:
                    stdout_err = stdout_raw[:500]
            detail = stderr or stdout_err or "no output"
            logger.error(f"Claude CLI failed (exit={returncode}): {detail}")
            raise RuntimeError(f"Claude CLI error: {detail}")

        stdout = stdout_raw
        if not stdout.strip():
            stderr = stderr_raw[:500] if stderr_raw else "no stderr"
            raise RuntimeError(f"Claude CLI returned no output. stderr: {stderr}")

        content, used_model, usage, session_id, cost_usd = _parse_stream_json(
            stdout, model
        )

        logger.info(
            f"Claude CLI result: model={used_model}, "
            f"content_len={len(content)}, usage={usage}"
        )

        return {
            "content": content,
            "role": "assistant",
            "model": used_model,
            "finish_reason": "end_turn",
            "usage": usage,
        }


def _parse_stream_json(
    stdout: str, fallback_model: Optional[str]
) -> tuple[str, str, dict, Optional[str], Optional[float]]:
    """Parse ``--output-format stream-json`` output from Claude CLI.

    Returns:
        (content, model, usage_dict, session_id, cost_usd)
    """
    assistant_texts: list[str] = []
    used_model = fallback_model or "unknown"
    usage: dict[str, int] = {}
    session_id: Optional[str] = None
    cost_usd: Optional[float] = None
    num_turns = 0
    result_text: Optional[str] = None

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = event.get("type")

        if etype == "assistant":
            msg = event.get("message", {})
            for block in msg.get("content", []):
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        assistant_texts.append(text)

        elif etype == "content_block_delta":
            # Sub-message deltas — skip to avoid duplication with "assistant"
            pass

        elif etype == "result":
            result_text = event.get("result", "")
            num_turns = event.get("num_turns", 1)
            session_id = event.get("session_id")
            cost_usd = event.get("total_cost_usd")

            usage_raw = event.get("usage", {})
            usage = {
                "input_tokens": usage_raw.get("input_tokens", 0),
                "output_tokens": usage_raw.get("output_tokens", 0),
                "cache_creation_input_tokens": usage_raw.get(
                    "cache_creation_input_tokens", 0
                ),
                "cache_read_input_tokens": usage_raw.get("cache_read_input_tokens", 0),
            }

            model_usage = event.get("modelUsage", {})
            if model_usage:
                used_model = next(iter(model_usage.keys()), used_model)

            if event.get("is_error"):
                error_msg = event.get("result", "Unknown CLI error")
                logger.error(f"Claude CLI reported error: {error_msg}")
                raise RuntimeError(f"Claude CLI error: {error_msg}")

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


# ---------------------------------------------------------------------------
# Copilot CLI Provider
# ---------------------------------------------------------------------------

# Known Copilot models (manually maintained — no models API available).
# Users can also specify any model name via LLM_MODELS config.
COPILOT_KNOWN_MODELS: list[tuple[str, str]] = [
    ("claude-sonnet-4.6", "Copilot Claude Sonnet 4.6"),
    ("claude-sonnet-4.5", "Copilot Claude Sonnet 4.5"),
    ("claude-haiku-4.5", "Copilot Claude Haiku 4.5"),
    ("claude-opus-4.6", "Copilot Claude Opus 4.6"),
    ("claude-opus-4.6-1m", "Copilot Claude Opus 4.6 (1M)"),
    ("claude-opus-4.5", "Copilot Claude Opus 4.5"),
    ("claude-sonnet-4", "Copilot Claude Sonnet 4"),
    ("gpt-5.4", "Copilot GPT-5.4"),
    ("gpt-5.3-codex", "Copilot GPT-5.3-Codex"),
    ("gpt-5.2-codex", "Copilot GPT-5.2-Codex"),
    ("gpt-5.2", "Copilot GPT-5.2"),
    ("gpt-5.1-codex-max", "Copilot GPT-5.1-Codex-Max"),
    ("gpt-5.1-codex", "Copilot GPT-5.1-Codex"),
    ("gpt-5.1", "Copilot GPT-5.1"),
    ("gpt-5.4-mini", "Copilot GPT-5.4 mini"),
    ("gpt-5.1-codex-mini", "Copilot GPT-5.1-Codex-Mini"),
    ("gpt-5-mini", "Copilot GPT-5 mini"),
    ("gpt-4.1", "Copilot GPT-4.1"),
]


class CopilotCLIProvider:
    """Runs GitHub Copilot CLI as a subprocess for chat completions."""

    def __init__(self) -> None:
        self._cli_path: Optional[str] = self._find_cli()
        if self._cli_path:
            logger.info(f"Copilot CLI found: {self._cli_path}")
        else:
            logger.info("Copilot CLI not found on host")

    @property
    def cli_path(self) -> Optional[str]:
        return self._cli_path

    @property
    def available(self) -> bool:
        return self._cli_path is not None

    @staticmethod
    def _find_cli() -> Optional[str]:
        """Locate the GitHub Copilot CLI executable.

        On Windows, shutil.which may return a WinGet symlink that injects
        ``--no-warnings`` when invoked via Python subprocess.  We resolve
        symlinks to the real executable to avoid this.

        Also skips ``.bat`` wrappers (e.g. VS Code extension's copilot.bat)
        which don't support the same CLI flags.
        """
        # Environment variable (highest priority)
        env_path = os.environ.get("COPILOT_CLI_PATH")
        if env_path and os.path.isfile(env_path):
            return os.path.realpath(env_path)

        # System PATH — but skip .bat wrappers (VS Code extension)
        which = shutil.which("copilot")
        if which:
            resolved = os.path.realpath(which)
            if not resolved.lower().endswith(".bat"):
                logger.debug(f"Copilot CLI found on PATH: {which} -> {resolved}")
                return resolved
            logger.debug(f"Skipping .bat wrapper: {which}")

        # Windows default locations (standalone CLI installs)
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(local_app_data, "Microsoft", "WinGet", "Links", "copilot.exe"),
            os.path.expanduser(r"~\.copilot\bin\copilot.exe"),
        ]
        for c in candidates:
            if c and os.path.isfile(c):
                return os.path.realpath(c)

        return None

    async def run_chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        effort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a chat completion through Copilot CLI subprocess.

        Args:
            model: Model name (e.g. "gpt-5.4", "claude-sonnet-4.6")
            messages: OpenAI-format message list
            system_prompt: Optional system prompt override (e.g. with tool defs)
            effort: Optional reasoning effort level (low, medium, high, xhigh)

        Returns:
            Dict with content, model, usage, finish_reason
        """
        if not self._cli_path:
            raise RuntimeError("Copilot CLI not found")

        # Build prompt from messages
        msg_system, prompt_text = build_prompt_from_messages(messages)
        system_text = system_prompt or msg_system

        if not prompt_text.strip():
            raise ValueError("No prompt text derived from messages")

        # Copilot doesn't have --system-prompt, so prepend to prompt
        if system_text:
            full_prompt = (
                f"[System Instructions]\n{system_text}\n"
                f"[End System Instructions]\n\n{prompt_text}"
            )
        else:
            full_prompt = prompt_text

        # Build command
        # --available-tools="" disables all built-in tools (shell, file edit, etc.)
        # so Copilot acts as a pure LLM endpoint. Without this, Copilot will
        # autonomously use its tools and the request can take 10+ minutes.
        cmd = [
            self._cli_path,
            "-p",
            full_prompt,
            "--output-format",
            "json",
            "--available-tools=",
            "-s",  # silent (no stats banner)
            "--no-custom-instructions",
        ]
        if model:
            cmd.extend(["--model", model])
        if effort:
            # Copilot CLI uses: low, medium, high, xhigh
            copilot_effort = "xhigh" if effort == "max" else effort
            cmd.extend(["--reasoning-effort", copilot_effort])

        logger.info(
            f"Copilot CLI call: model={model or 'default'}, "
            f"effort={effort or 'default'}, "
            f"prompt_len={len(full_prompt)}"
        )

        start = time.time()
        try:
            env = _clean_subprocess_env()
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1800,
                cwd=os.getcwd(),
                env=env,
            )
            stdout_raw = result.stdout or ""
            stderr_raw = result.stderr or ""
            returncode = result.returncode
        except subprocess.TimeoutExpired:
            logger.error("Copilot CLI timed out after 1800s")
            raise RuntimeError("Copilot CLI subprocess timed out")
        except Exception as e:
            logger.error(f"Copilot CLI subprocess error: {e}")
            raise RuntimeError(f"Copilot CLI subprocess error: {e}")

        duration = time.time() - start
        logger.info(f"Copilot CLI finished in {duration:.1f}s (exit={returncode})")

        if returncode != 0:
            stderr = stderr_raw[:500] if stderr_raw else ""
            stdout_head = stdout_raw[:500] if stdout_raw else ""
            detail = stderr or stdout_head or "no output"
            logger.error(
                f"Copilot CLI failed (exit={returncode}):\n"
                f"  STDERR: {stderr!r}\n"
                f"  STDOUT: {stdout_head!r}"
            )
            raise RuntimeError(f"Copilot CLI error: {detail}")

        stdout = stdout_raw
        if not stdout.strip():
            stderr = stderr_raw[:500] if stderr_raw else "no stderr"
            raise RuntimeError(f"Copilot CLI returned no output. stderr: {stderr}")

        content, used_model, usage = _parse_copilot_jsonl(stdout, model)

        logger.info(
            f"Copilot CLI result: model={used_model}, "
            f"content_len={len(content)}, usage={usage}"
        )

        return {
            "content": content,
            "role": "assistant",
            "model": used_model,
            "finish_reason": "end_turn",
            "usage": usage,
        }


def _parse_copilot_jsonl(
    stdout: str, fallback_model: Optional[str]
) -> tuple[str, str, dict]:
    """Parse JSONL output from Copilot CLI ``--output-format json``.

    Event types:
    - ``session.tools_updated``: model name
    - ``assistant.message``: content (skip ephemeral messages)
    - ``result``: session info and exit code

    Returns:
        (content, model, usage_dict)
    """
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
            # Skip ephemeral messages (deltas, status updates)
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
                raise RuntimeError(f"Copilot CLI exited with code {exit_code}")

    if assistant_texts:
        content = "\n\n".join(assistant_texts)
    else:
        content = stdout.strip()
        logger.warning(
            "No structured content found in Copilot output, using raw stdout"
        )

    usage = {
        "output_tokens": total_output_tokens,
        "total_tokens": total_output_tokens,
    }

    return content, used_model, usage

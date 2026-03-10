"""
Memory service integration utilities for gateway.

All operations use HTTP calls to memory service. Requires MEMORY_SERVICE_URL.
Gateway is a pure HTTP client - no direct file access to memory storage.

Handles:
- Auto-logging messages to daily logs (via HTTP to /write_daily)
- 80% context flush trigger with distillation (writes via HTTP)
- Memory context injection at conversation start (via HTTP to /context)
- Parsing distillation markers from LLM response (inline regex)
"""

import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .prompt_compressor import CONTEXT_LIMITS, estimate_messages_tokens

logger = logging.getLogger(__name__)

# Configuration
MEMORY_AUTO_LOG = os.getenv("MEMORY_AUTO_LOG", "true").lower() == "true"
MEMORY_AUTO_FLUSH = os.getenv("MEMORY_AUTO_FLUSH", "true").lower() == "true"
MEMORY_FLUSH_THRESHOLD = float(os.getenv("MEMORY_FLUSH_THRESHOLD", "0.8"))


def get_memory_service_url() -> Optional[str]:
    """Get memory service URL from environment."""
    return os.getenv("MEMORY_SERVICE_URL")


def is_memory_enabled() -> bool:
    """Check if memory service is enabled and configured."""
    return get_memory_service_url() is not None


def get_memory_config() -> Dict[str, Any]:
    """Get current memory configuration."""
    return {
        "enabled": is_memory_enabled(),
        "service_url": get_memory_service_url(),
        "auto_log": MEMORY_AUTO_LOG,
        "auto_flush": MEMORY_AUTO_FLUSH,
        "flush_threshold": MEMORY_FLUSH_THRESHOLD,
    }


async def append_to_daily_log_async(
    content: str,
    role: str = "user",
    conversation_id: Optional[str] = None,
) -> bool:
    """
    Append a message to the daily log via HTTP API.

    Requires MEMORY_SERVICE_URL to be configured.

    Args:
        content: Message content
        role: Message role (user/assistant)
        conversation_id: Session/conversation ID for grouping messages

    Returns:
        True if successful, False otherwise
    """
    if not MEMORY_AUTO_LOG:
        return False

    memory_url = get_memory_service_url()
    if not memory_url:
        logger.debug("MEMORY_SERVICE_URL not configured, skipping daily log")
        return False

    try:
        payload = {"role": role, "content": content}
        if conversation_id:
            payload["session_id"] = conversation_id

        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.post(
                f"{memory_url}/write_daily",
                json=payload,
            )
            response.raise_for_status()
            logger.debug(
                f"Logged {role} message via API: {len(content)} chars (session: {conversation_id})"
            )
            return True
    except Exception as e:
        logger.warning(f"Failed to write daily log via API: {e}")
        return False


def _get_distillation_prompt(token_usage_pct: float) -> str:
    """Generate distillation prompt for 80% context flush."""
    return f"""
### MEMORY CHECKPOINT ({token_usage_pct:.0%} context used)

Before continuing with your response, please extract important information from this conversation.

**Format your extraction with these exact markers:**

[SUMMARY]
(2-3 sentence recap of what was accomplished in this session)
[/SUMMARY]

[FACTS]
- Any permanent rules, preferences, or constraints discovered
- Important decisions that should be remembered
- Technical details that will be true in future sessions
(Leave empty if no durable facts to save)
[/FACTS]

After the markers, continue with your normal response to the user.
The user will NOT see the [SUMMARY] and [FACTS] sections - they are for memory only.
"""


def _parse_distillation_response(response: str) -> Tuple[str, str]:
    """
    Parse LLM response for summary and facts markers.

    Args:
        response: Full LLM response text

    Returns:
        Tuple of (summary, facts) - both may be empty strings
    """
    summary = ""
    facts = ""

    # Extract [SUMMARY]...[/SUMMARY]
    summary_match = re.search(
        r"\[SUMMARY\](.*?)\[/SUMMARY\]", response, re.DOTALL | re.IGNORECASE
    )
    if summary_match:
        summary = summary_match.group(1).strip()

    # Extract [FACTS]...[/FACTS]
    facts_match = re.search(
        r"\[FACTS\](.*?)\[/FACTS\]", response, re.DOTALL | re.IGNORECASE
    )
    if facts_match:
        facts = facts_match.group(1).strip()
        # Filter out "none" or "empty" responses
        if facts.lower() in ("none", "n/a", "-", ""):
            facts = ""

    return summary, facts


def _strip_distillation_markers(response: str) -> str:
    """
    Remove distillation markers from response before showing to user.

    Args:
        response: Full LLM response with markers

    Returns:
        Clean response without [SUMMARY] and [FACTS] sections
    """
    # Remove [SUMMARY]...[/SUMMARY] block
    clean = re.sub(
        r"\[SUMMARY\].*?\[/SUMMARY\]\s*",
        "",
        response,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Remove [FACTS]...[/FACTS] block
    clean = re.sub(
        r"\[FACTS\].*?\[/FACTS\]\s*", "", clean, flags=re.DOTALL | re.IGNORECASE
    )

    return clean.strip()


def check_and_get_flush_prompt(
    messages: List[Dict[str, Any]],
    provider_type: str = "default",
) -> Tuple[bool, Optional[str], float]:
    """
    Check if context is at 80% capacity and return flush prompt if needed.

    Args:
        messages: Current message list
        provider_type: LLM provider type for context limit lookup

    Returns:
        Tuple of (flush_triggered, flush_prompt, token_usage_pct)
    """
    if not MEMORY_AUTO_FLUSH:
        return False, None, 0.0

    if not is_memory_enabled():
        return False, None, 0.0

    # Calculate current token usage
    current_tokens = estimate_messages_tokens(messages)
    max_tokens = CONTEXT_LIMITS.get(provider_type, CONTEXT_LIMITS["default"])
    usage_ratio = current_tokens / max_tokens

    if usage_ratio < MEMORY_FLUSH_THRESHOLD:
        return False, None, usage_ratio

    logger.info(
        f"Context at {usage_ratio*100:.1f}% ({current_tokens}/{max_tokens} tokens), "
        f"triggering memory flush"
    )

    flush_prompt = _get_distillation_prompt(usage_ratio)
    return True, flush_prompt, usage_ratio


async def parse_and_save_distillation_async(response: str) -> Tuple[str, str, str]:
    """
    Parse LLM response for distillation markers and save via HTTP API.

    Args:
        response: Full LLM response text

    Returns:
        Tuple of (clean_response, summary, facts)
        - clean_response: Response with markers removed (for user)
        - summary: Extracted summary (empty if none)
        - facts: Extracted facts (empty if none)
    """
    memory_url = get_memory_service_url()
    if not memory_url:
        return response, "", ""

    try:
        # Parse markers (local regex operation)
        summary, facts = _parse_distillation_response(response)

        # Save summary to daily log via HTTP
        if summary:
            try:
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    await http_client.post(
                        f"{memory_url}/write_daily",
                        json={
                            "role": "system",
                            "content": f"## Session Summary\n{summary}",
                        },
                    )
                logger.info(f"Saved session summary via API: {len(summary)} chars")
            except Exception as e:
                logger.warning(f"Failed to save session summary via API: {e}")

        # Save facts to MEMORY.md via HTTP
        if facts:
            try:
                async with httpx.AsyncClient(timeout=10.0) as http_client:
                    await http_client.post(
                        f"{memory_url}/write_memory",
                        json={"content": facts, "replace": False},
                    )
                logger.info(f"Saved durable facts via API: {len(facts)} chars")
            except Exception as e:
                logger.warning(f"Failed to save durable facts via API: {e}")

        # Remove markers from response for user (local regex operation)
        clean_response = _strip_distillation_markers(response)

        return clean_response, summary, facts

    except Exception as e:
        logger.warning(f"Failed to parse/save distillation: {e}")
        return response, "", ""


async def get_memory_context(
    conversation_id: Optional[str] = None,
    query: Optional[str] = None,
    max_tokens: int = 2000,
) -> Optional[str]:
    """
    Get relevant memory context to inject at conversation start.

    Uses HTTP call to memory service /context endpoint.

    Args:
        conversation_id: Optional conversation ID
        query: Optional query to focus context
        max_tokens: Maximum tokens for context

    Returns:
        Memory context string, or None if unavailable
    """
    memory_url = get_memory_service_url()
    if not memory_url:
        logger.debug("MEMORY_SERVICE_URL not configured, skipping memory context")
        return None

    try:
        params = {"max_tokens": max_tokens}
        if conversation_id:
            params["conversation_id"] = conversation_id
        if query:
            params["query"] = query

        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.get(
                f"{memory_url}/context",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        context = data.get("context", "")
        if context:
            token_count = data.get("token_count", 0)
            sources = data.get("sources", [])
            logger.info(
                f"Loaded memory context: {token_count} tokens from {len(sources)} sources"
            )
            return context

    except Exception as e:
        logger.warning(f"Failed to get memory context: {e}")

    return None


async def save_memory_via_api(content: str, section: Optional[str] = None) -> bool:
    """
    Save content to MEMORY.md via HTTP API.

    Requires MEMORY_SERVICE_URL to be configured.

    Args:
        content: Content to save
        section: Optional section header

    Returns:
        True if successful, False otherwise
    """
    memory_url = get_memory_service_url()
    if not memory_url:
        logger.debug("MEMORY_SERVICE_URL not configured, skipping memory save")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.post(
                f"{memory_url}/write_memory",
                json={
                    "content": content,
                    "section": section
                    or f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    "replace": False,
                },
            )
            response.raise_for_status()
            logger.info(f"Saved memory via API: {len(content)} chars")
            return True

    except Exception as e:
        logger.warning(f"Failed to save memory via API: {e}")
        return False


async def read_durable_memory_async() -> str:
    """
    Read MEMORY.md content via HTTP API for injection into system prompt.

    Uses /context endpoint to get long-term memory.

    Returns:
        Contents of MEMORY.md, or empty string if not available
    """
    context = await get_memory_context(max_tokens=4000)
    return context or ""

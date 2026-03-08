"""
Memory service integration utilities for gateway.

Uses MemoryClient for direct file writes (fast, reliable).
Uses HTTP calls to memory service for search and context.

Handles:
- Auto-logging messages to daily logs (direct file write)
- 80% context flush trigger with distillation
- Memory context injection at conversation start
- Parsing distillation markers from LLM response
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .prompt_compressor import CONTEXT_LIMITS, estimate_messages_tokens

logger = logging.getLogger(__name__)

# Configuration
MEMORY_AUTO_LOG = os.getenv("MEMORY_AUTO_LOG", "true").lower() == "true"
MEMORY_AUTO_FLUSH = os.getenv("MEMORY_AUTO_FLUSH", "true").lower() == "true"
MEMORY_FLUSH_THRESHOLD = float(os.getenv("MEMORY_FLUSH_THRESHOLD", "0.8"))
MEMORY_DATA_PATH = os.getenv("MEMORY_DATA_PATH", "/data/memory")

# Add memory_service to path for importing MemoryClient
_memory_service_path = (
    Path(__file__).parent.parent.parent / "services" / "memory_service"
)
if str(_memory_service_path) not in sys.path:
    sys.path.insert(0, str(_memory_service_path))

# Import MemoryClient (lazy import to avoid circular deps)
_memory_client = None


def _get_memory_client():
    """Get or create MemoryClient instance."""
    global _memory_client
    if _memory_client is None:
        try:
            from client import MemoryClient

            _memory_client = MemoryClient(MEMORY_DATA_PATH)
            logger.info(f"MemoryClient initialized with path: {MEMORY_DATA_PATH}")
        except ImportError as e:
            logger.warning(f"Could not import MemoryClient: {e}")
            return None
    return _memory_client


def get_memory_service_url() -> Optional[str]:
    """Get memory service URL from environment."""
    return os.getenv("MEMORY_SERVICE_URL")


def is_memory_enabled() -> bool:
    """Check if memory service is enabled and configured."""
    return get_memory_service_url() is not None or _get_memory_client() is not None


def get_memory_config() -> Dict[str, Any]:
    """Get current memory configuration."""
    client = _get_memory_client()
    return {
        "enabled": is_memory_enabled(),
        "service_url": get_memory_service_url(),
        "data_path": MEMORY_DATA_PATH,
        "auto_log": MEMORY_AUTO_LOG,
        "auto_flush": MEMORY_AUTO_FLUSH,
        "flush_threshold": MEMORY_FLUSH_THRESHOLD,
        "client_enabled": client is not None,
    }


def append_to_daily_log(
    content: str,
    role: str = "user",
    conversation_id: Optional[str] = None,
) -> bool:
    """
    Append a message to the daily log.

    Writes directly to filesystem - memsearch.watch() will auto-index.

    Args:
        content: Message content
        role: Message role (user/assistant)
        conversation_id: Optional conversation ID (for future use)

    Returns:
        True if successful, False otherwise
    """
    if not MEMORY_AUTO_LOG:
        return False

    client = _get_memory_client()
    if not client:
        logger.debug("MemoryClient not available, skipping daily log")
        return False

    try:
        log_path = client.append_to_daily_log(role, content)
        logger.debug(f"Logged {role} message to {log_path}: {len(content)} chars")
        return True
    except Exception as e:
        logger.warning(f"Failed to write to daily log: {e}")
        return False


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

    client = _get_memory_client()
    if client:
        flush_prompt = client.get_distillation_prompt(usage_ratio)
    else:
        # Fallback prompt if client not available
        flush_prompt = _get_fallback_distillation_prompt(usage_ratio)

    return True, flush_prompt, usage_ratio


def _get_fallback_distillation_prompt(token_usage_pct: float) -> str:
    """Fallback distillation prompt if MemoryClient not available."""
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


def parse_and_save_distillation(response: str) -> Tuple[str, str, str]:
    """
    Parse LLM response for distillation markers and save to files.

    Args:
        response: Full LLM response text

    Returns:
        Tuple of (clean_response, summary, facts)
        - clean_response: Response with markers removed (for user)
        - summary: Extracted summary (empty if none)
        - facts: Extracted facts (empty if none)
    """
    client = _get_memory_client()
    if not client:
        return response, "", ""

    try:
        # Parse markers
        summary, facts = client.parse_distillation_response(response)

        # Save if found
        if summary:
            client.append_session_summary(summary)
            logger.info(f"Saved session summary: {len(summary)} chars")

        if facts:
            client.append_durable_facts(facts)
            logger.info(f"Saved durable facts: {len(facts)} chars")

        # Remove markers from response for user
        clean_response = client.strip_distillation_markers(response)

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

    Uses HTTP call to memory service for search functionality.

    Args:
        conversation_id: Optional conversation ID
        query: Optional query to focus context
        max_tokens: Maximum tokens for context

    Returns:
        Memory context string, or None if unavailable
    """
    memory_url = get_memory_service_url()
    if not memory_url:
        # Fallback: just read MEMORY.md directly
        client = _get_memory_client()
        if client:
            memory_content = client.read_memory_md()
            if memory_content:
                return f"## Your Long-term Memory\n\n{memory_content}"
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
    Save content to MEMORY.md via API (for LLM tool calls).

    Args:
        content: Content to save
        section: Optional section header

    Returns:
        True if successful, False otherwise
    """
    memory_url = get_memory_service_url()
    if not memory_url:
        # Fallback: write directly
        client = _get_memory_client()
        if client:
            try:
                client.append_durable_facts(content)
                return True
            except Exception as e:
                logger.warning(f"Failed to write memory directly: {e}")
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


def read_durable_memory() -> str:
    """
    Read MEMORY.md content for injection into system prompt.

    Returns:
        Contents of MEMORY.md, or empty string if not available
    """
    client = _get_memory_client()
    if not client:
        return ""

    try:
        return client.read_memory_md()
    except Exception as e:
        logger.warning(f"Failed to read MEMORY.md: {e}")
        return ""

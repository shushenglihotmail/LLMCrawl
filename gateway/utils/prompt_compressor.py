"""
Prompt compression utility for handling large prompts that exceed model context limits.

Compression strategies (in order of preference):
1. LLMLingua-2: BERT-based intelligent compression, CPU-friendly (~500MB-1GB model)
2. Tiktoken truncation: Token-aware truncation as fallback

LLMLingua-2 is the default - it uses a BERT-based architecture that is 3x-6x faster
than the original LLMLingua and works well on CPU-only VMs (4GB+ RAM recommended).
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import tiktoken

logger = logging.getLogger(__name__)

# Default context limits for different providers
CONTEXT_LIMITS = {
    "anthropic": 200000,
    "openai": 128000,
    "azure": 128000,
    "default": 100000,
}

# Reserve tokens for response
RESPONSE_TOKEN_RESERVE = 16000

# Global tiktoken encoding (initialized once)
_encoding = tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str) -> int:
    """Estimate token count for a string using tiktoken."""
    return len(_encoding.encode(text))


def estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """Estimate total tokens for a list of chat messages."""
    total = 0
    for msg in messages:
        # Add tokens for role and message structure overhead (~4 tokens per message)
        total += 4
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for block in content:
                total += estimate_tokens(str(block))

        # Handle tool calls if present
        if msg.get("tool_calls"):
            for tool_call in msg["tool_calls"]:
                total += estimate_tokens(str(tool_call))

    return total


class PromptCompressor:
    """
    Compresses prompts to fit within model context limits.

    Strategies:
    1. LLMLingua-2: BERT-based compression, 3-6x faster than original, CPU-friendly
    2. Tiktoken truncation: Token-aware truncation as fallback
    """

    def __init__(
        self,
        max_context_tokens: Optional[int] = None,
        response_reserve: int = RESPONSE_TOKEN_RESERVE,
    ):
        """
        Initialize the prompt compressor.

        Args:
            max_context_tokens: Maximum context window size. If None, auto-detect.
            response_reserve: Tokens to reserve for the response.
        """
        self.max_context_tokens = max_context_tokens
        self.response_reserve = response_reserve
        self._llmlingua_compressor: Any = None
        self._init_llmlingua()

    def _init_llmlingua(self) -> None:
        """Try to initialize LLMLingua-2 compressor (CPU-optimized, BERT-based)."""
        try:
            import torch
            from llmlingua import PromptCompressor as LLMLinguaCompressor

            device = "cuda" if torch.cuda.is_available() else "cpu"

            # LLMLingua-2 models (BERT-based, CPU-friendly):
            # - microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank (~500MB)
            # - microsoft/llmlingua-2-xlm-roberta-large-meetingbank (~1GB)
            model_name = os.getenv(
                "LLMLINGUA_MODEL",
                "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank",
            )

            self._llmlingua_compressor = LLMLinguaCompressor(
                model_name=model_name,
                use_llmlingua2=True,
                device_map=device,
            )
            logger.info(f"LLMLingua-2 initialized: {model_name} on {device}")
        except ImportError:
            logger.info(
                "LLMLingua-2 not installed, using tiktoken truncation. "
                "Install with: pip install llmlingua torch transformers accelerate"
            )
        except Exception as e:
            logger.warning(f"Failed to initialize LLMLingua-2: {e}")

    def get_context_limit(self, provider_type: str = "default") -> int:
        """Get the context limit for a given provider."""
        if self.max_context_tokens:
            return self.max_context_tokens
        return CONTEXT_LIMITS.get(provider_type, CONTEXT_LIMITS["default"])

    def needs_compression(
        self,
        messages: List[Dict[str, Any]],
        provider_type: str = "default",
    ) -> Tuple[bool, int, int]:
        """Check if messages need compression."""
        current_tokens = estimate_messages_tokens(messages)
        context_limit = self.get_context_limit(provider_type)
        max_allowed = context_limit - self.response_reserve
        return current_tokens > max_allowed, current_tokens, max_allowed

    def _compress_llmlingua(self, text: str, target_tokens: int) -> str:
        """Compress text using LLMLingua-2."""
        if self._llmlingua_compressor is None:
            raise RuntimeError("LLMLingua-2 not initialized")

        current_tokens = estimate_tokens(text)
        if current_tokens <= target_tokens:
            return text

        rate = min(target_tokens / current_tokens, 1.0)
        result = self._llmlingua_compressor.compress_prompt(
            text,
            rate=rate,
            force_tokens=["\n", ".", "?", ":", "-"],
        )
        compressed: str = result.get("compressed_prompt", text)
        new_tokens: int = result.get("compressed_tokens", estimate_tokens(compressed))
        logger.info(
            f"LLMLingua-2: {current_tokens} -> {new_tokens} tokens "
            f"({100 * new_tokens / current_tokens:.1f}%)"
        )
        return compressed

    def _compress_truncate(self, text: str, target_tokens: int) -> str:
        """Compress text by token-aware truncation (keeps beginning and end)."""
        tokens = _encoding.encode(text)
        if len(tokens) <= target_tokens:
            return text

        # Keep first 70% and last 30% of allowed tokens
        first_portion = int(target_tokens * 0.7)
        last_portion = target_tokens - first_portion - 10

        first_text = _encoding.decode(tokens[:first_portion])
        last_text = (
            _encoding.decode(tokens[-last_portion:]) if last_portion > 0 else ""
        )
        separator = f"\n\n[... {len(tokens) - target_tokens} tokens truncated ...]\n\n"

        result: str = first_text + separator + last_text
        return result

    def compress_text(self, text: str, target_tokens: int) -> str:
        """Compress text using LLMLingua-2 or tiktoken truncation as fallback."""
        if self._llmlingua_compressor:
            try:
                return self._compress_llmlingua(text, target_tokens)
            except Exception as e:
                logger.warning(f"LLMLingua-2 failed, using truncation: {e}")

        return self._compress_truncate(text, target_tokens)

    def compress_messages(
        self,
        messages: List[Dict[str, Any]],
        provider_type: str = "default",
    ) -> List[Dict[str, Any]]:
        """
        Compress messages to fit within context limits.

        Priority: tool results > old assistant messages > old user messages > system
        """
        needs_compress, current_tokens, max_allowed = self.needs_compression(
            messages, provider_type
        )

        if not needs_compress:
            return messages

        logger.warning(
            f"Prompt too large: {current_tokens} > {max_allowed} tokens. Compressing..."
        )

        # Calculate compression targets
        excess_tokens = current_tokens - max_allowed
        target_reduction = excess_tokens + (max_allowed * 0.1)  # 10% buffer

        # Analyze messages for compression priority
        message_sizes = []
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            size = estimate_tokens(
                content if isinstance(content, str) else str(content)
            )

            role = msg.get("role", "")
            if role == "tool":
                priority = 1
            elif role == "assistant":
                priority = 2
            elif role == "user":
                priority = 3 if i < len(messages) - 2 else 5
            else:  # system
                priority = 10

            message_sizes.append((i, size, priority))

        # Sort by priority, then by size (largest first)
        compression_order = sorted(message_sizes, key=lambda x: (x[2], -x[1]))

        # Determine compression targets
        compress_targets = {}
        remaining = target_reduction

        for idx, size, priority in compression_order:
            if remaining <= 0 or priority >= 10 or size < 100:
                continue
            reduction = min(size * 0.8, remaining)
            compress_targets[idx] = max(int(size - reduction), 100)
            remaining -= reduction

        # Apply compressions
        compressed_messages = []
        tokens_reduced = 0

        for i, msg in enumerate(messages):
            if i in compress_targets:
                content = msg.get("content", "")
                if isinstance(content, str) and content:
                    original = estimate_tokens(content)
                    compressed = self.compress_text(content, compress_targets[i])
                    new_tokens = estimate_tokens(compressed)
                    tokens_reduced += original - new_tokens

                    new_msg = msg.copy()
                    new_msg["content"] = compressed
                    compressed_messages.append(new_msg)
                    logger.info(
                        f"Compressed {msg.get('role')} msg {i}: "
                        f"{original} -> {new_tokens}"
                    )
                else:
                    compressed_messages.append(msg)
            else:
                compressed_messages.append(msg)

        final_tokens = estimate_messages_tokens(compressed_messages)
        logger.info(f"Compression complete: {current_tokens} -> {final_tokens} tokens")

        if final_tokens > max_allowed:
            logger.warning(f"Still over limit: {final_tokens} > {max_allowed}")

        return compressed_messages


# Global compressor instance
_compressor: Optional[PromptCompressor] = None


def get_compressor() -> PromptCompressor:
    """
    Get or create the global prompt compressor.

    Environment variables:
    - LLMLINGUA_MODEL: Model to use
      (default: microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank)
    """
    global _compressor
    if _compressor is None:
        _compressor = PromptCompressor()
    return _compressor


def compress_if_needed(
    messages: List[Dict[str, Any]],
    provider_type: str = "default",
) -> List[Dict[str, Any]]:
    """Compress messages if they exceed context limits."""
    return get_compressor().compress_messages(messages, provider_type)

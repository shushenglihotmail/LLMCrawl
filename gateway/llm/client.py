"""
LLM client for OpenAI, Azure OpenAI, Anthropic, Claude CLI, and Copilot CLI.
Handles chat completions, tool calling, and streaming.
"""  # noqa: F401

import asyncio  # noqa: F401
import json
import logging
import os
import re
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
import openai  # noqa: F401
from openai import AsyncAzureOpenAI, AsyncOpenAI

from gateway.utils.metrics import record_llm_request
from gateway.utils.prompt_compressor import compress_if_needed, estimate_messages_tokens
from gateway.utils.tool_constants import TOOL_CRAWL_AND_REFRESH

logger = logging.getLogger(__name__)

# Default maximum tokens for LLM response output
# This is the fallback when model-specific limit is not configured
# Most models support at least 4096-8192 output tokens
DEFAULT_MAX_RESPONSE_TOKENS = 8192


class LLMClient:
    """Unified client for OpenAI and Azure OpenAI with tool calling support."""

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()

        # Initialize OpenAI client
        # Note: API keys are optional when using Entra ID bearer token authentication
        if self.provider == "azure":
            api_key = os.getenv("AZURE_OPENAI_API_KEY", "dummy-key-for-entra-id")
            self.openai_client = AsyncAzureOpenAI(
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=api_key,
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            )
            logger.info(
                f"Azure OpenAI client initialized (Entra ID auth: {api_key == 'dummy-key-for-entra-id'})"
            )
        else:
            # API key may not be set if user only uses CLI providers (Claude/Copilot)
            openai_key = os.getenv("OPENAI_API_KEY", "")
            self.openai_client = AsyncOpenAI(api_key=openai_key or "unused")

        # Store Anthropic endpoint configuration for direct HTTP calls
        self.anthropic_endpoint = (
            os.getenv("AZURE_ANTHROPIC_ENDPOINT") if self.provider == "azure" else None
        )
        # API key is optional for Anthropic when using Entra ID
        self.anthropic_api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        if self.anthropic_endpoint:
            logger.info(f"Anthropic endpoint configured: {self.anthropic_endpoint}")

        # Claude Bridge configuration (host-side Claude Code CLI bridge)
        self.claude_bridge_url = os.getenv("CLAUDE_BRIDGE_URL")
        if self.claude_bridge_url:
            logger.info(f"Claude Bridge configured: {self.claude_bridge_url}")

        # Copilot Bridge configuration (host-side Copilot CLI bridge)
        self.copilot_bridge_url = os.getenv("COPILOT_BRIDGE_URL")
        if self.copilot_bridge_url:
            logger.info(f"Copilot Bridge configured: {self.copilot_bridge_url}")

        # Direct CLI providers (preferred over HTTP bridges when available)
        from gateway.llm.cli_providers import ClaudeCLIProvider, CopilotCLIProvider

        self.claude_cli = ClaudeCLIProvider()
        self.copilot_cli = CopilotCLIProvider()

        # For backward compatibility
        self.client = self.openai_client
        logger.info(f"Initialized LLM client: {self.provider}")

    def _uses_max_completion_tokens(self, model: str) -> bool:
        """
        Determine if a model uses the new max_completion_tokens parameter.

        GPT-5.x, newer GPT-4 variants (2024-11-20+), and o-series models
        use max_completion_tokens instead of max_tokens.

        Args:
            model: Model name or deployment name

        Returns:
            True if model requires max_completion_tokens parameter
        """
        model_lower = model.lower()

        # GPT-5.x models
        if "gpt-5" in model_lower:
            return True

        # o-series models (o1, o3, etc.)
        if model_lower.startswith("o1") or model_lower.startswith("o3"):
            return True

        # Newer GPT-4 models with date >= 2024-11-20
        if "gpt-4" in model_lower:
            # Extract date pattern (YYYY-MM-DD)
            date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", model)
            if date_match:
                year, month, day = map(int, date_match.groups())
                # Compare as integer YYYYMMDD
                date_int = year * 10000 + month * 100 + day
                # 2024-11-20 or later
                if date_int >= 20241120:
                    return True

        return False

    def _supports_custom_temperature(self, model: str) -> bool:
        """
        Determine if a model supports custom temperature values.

        GPT-5.x and o-series models only support temperature=1 (default).

        Args:
            model: Model name or deployment name

        Returns:
            False if model only supports default temperature, True otherwise
        """
        model_lower = model.lower()

        # GPT-5.x models only support temperature=1
        if "gpt-5" in model_lower:
            return False

        # o-series models only support temperature=1
        if model_lower.startswith("o1") or model_lower.startswith("o3"):
            return False

        return True

    def get_model_config(self, model_name: str) -> tuple[str, str, int]:
        """
        Resolve model name to (deployment_name, provider_type, max_output_tokens).

        Resolution priority:
        1. LLM_MODELS config — explicit provider_type set by user (e.g. openai,
           anthropic, claude, copilot).  Highest priority so users can override
           any automatic detection.
        2. Claude CLI/Bridge — model discovered at startup from Anthropic API.
        3. Copilot CLI/Bridge — model from hardcoded known-models list.
        4. Default LLM_PROVIDER fallback (self.provider, e.g. "openai").

        Args:
            model_name: The model name selected by user

        Returns:
            Tuple of (deployment_name, provider_type, max_output_tokens)
        """
        # --- 1. Explicit config in LLM_MODELS (highest priority) ---
        try:
            models_json = os.getenv("LLM_MODELS", "[]")
            models_config = json.loads(models_json)

            for model in models_config:
                if model.get("name") == model_name:
                    deployment_name = model.get("deployment_name", model_name)
                    provider_type = model.get("provider_type", "openai")
                    max_output_tokens = model.get("max_output_tokens")
                    if max_output_tokens is None:
                        if provider_type in ("anthropic", "claude"):
                            max_output_tokens = 64000
                        else:
                            max_output_tokens = 16384
                    logger.info(
                        f"Model '{model_name}' -> '{deployment_name}' "
                        f"(provider: {provider_type}, from LLM_MODELS config)"
                    )
                    return deployment_name, provider_type, max_output_tokens
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM_MODELS: {e}")

        # --- 2. Claude CLI/Bridge (discovered at startup) ---
        from gateway.utils.claude_bridge_manager import get_claude_bridge_manager

        claude_mgr = get_claude_bridge_manager()
        if claude_mgr.is_claude_model(model_name):
            logger.info(f"Model '{model_name}' -> Claude CLI/Bridge")
            return model_name, "claude", DEFAULT_MAX_RESPONSE_TOKENS

        # --- 3. Copilot CLI/Bridge (discovered at startup) ---
        from gateway.utils.copilot_bridge_manager import get_copilot_bridge_manager

        copilot_mgr = get_copilot_bridge_manager()
        if copilot_mgr.is_copilot_model(model_name):
            logger.info(f"Model '{model_name}' -> Copilot CLI/Bridge")
            return model_name, "copilot", DEFAULT_MAX_RESPONSE_TOKENS

        # --- 4. Default LLM_PROVIDER fallback ---
        logger.warning(
            f"Model '{model_name}' not in LLM_MODELS or CLI providers, "
            f"falling back to LLM_PROVIDER={self.provider}"
        )
        return model_name, self.provider, DEFAULT_MAX_RESPONSE_TOKENS

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        bearer_token: Optional[str] = None,
        effort: Optional[str] = None,
    ) -> Dict[str, Any] | AsyncGenerator[Dict[str, Any], None]:
        """
        Create a chat completion with optional tool calling.

        Args:
            messages: Chat messages including system prompts
            model: Model name selected by client (will be resolved to deployment_name for Azure)
            tools: Available tools for function calling
            tool_choice: "auto", "none", or specific tool
            temperature: Sampling temperature
            max_tokens: Maximum response tokens (if None, uses model-specific default)
            stream: Whether to stream the response
            bearer_token: Optional Entra ID bearer token for Azure Foundry authentication

        Returns:
            Chat completion response or stream generator
        """
        try:
            # Resolve deployment name, provider type, and max output tokens
            deployment_name, provider_type, model_max_tokens = self.get_model_config(
                model
            )

            # Use provided max_tokens or model-specific default
            effective_max_tokens = (
                max_tokens if max_tokens is not None else model_max_tokens
            )
            logger.info(
                f"Model resolution: '{model}' -> '{deployment_name}' "
                f"(provider: {provider_type}, max_tokens: {effective_max_tokens})"
            )

            # Compress messages if they exceed context limits
            original_token_count = estimate_messages_tokens(messages)
            messages = compress_if_needed(messages, provider_type)
            compressed_token_count = estimate_messages_tokens(messages)
            if compressed_token_count < original_token_count:
                logger.info(
                    f"Prompt compressed: {original_token_count} -> {compressed_token_count} tokens"
                )

            # Route to appropriate client based on provider type
            if provider_type == "copilot":
                return await self._copilot_chat_completion(
                    deployment_name,
                    messages,
                    tools,
                    tool_choice,
                    temperature,
                    effective_max_tokens,
                    effort=effort,
                )
            elif provider_type == "claude":
                return await self._claude_chat_completion(
                    deployment_name,
                    messages,
                    tools,
                    tool_choice,
                    temperature,
                    effective_max_tokens,
                    effort=effort,
                )
            elif provider_type == "anthropic":
                return await self._anthropic_chat_completion(
                    deployment_name,
                    messages,
                    tools,
                    tool_choice,
                    temperature,
                    effective_max_tokens,
                    stream,
                    bearer_token,
                )
            else:
                return await self._openai_chat_completion(
                    deployment_name,
                    messages,
                    tools,
                    tool_choice,
                    temperature,
                    effective_max_tokens,
                    stream,
                    bearer_token,
                )

        except Exception as e:
            logger.error(f"Chat completion failed: {e}")
            # Extract detailed error message from Azure OpenAI
            error_msg = str(e)
            if hasattr(e, "response"):
                try:
                    error_data = (
                        e.response.json() if hasattr(e.response, "json") else {}
                    )
                    if "error" in error_data:
                        error_msg = error_data["error"].get("message", error_msg)
                except Exception:
                    pass
            # Re-raise with preserved message
            raise Exception(error_msg) from e

    async def _openai_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: str,
        temperature: float,
        max_tokens: int,
        stream: bool,
        bearer_token: Optional[str] = None,
    ) -> Dict[str, Any] | AsyncGenerator[Dict[str, Any], None]:
        """Handle OpenAI/Azure OpenAI chat completion.

        Args:
            bearer_token: Optional Entra ID bearer token for Azure Foundry authentication
        """
        # Determine if model uses new max_completion_tokens parameter
        # GPT-5.x, newer GPT-4 variants (2024-11-20+), and o-series models use max_completion_tokens
        uses_max_completion_tokens = self._uses_max_completion_tokens(model)

        # Determine if model supports custom temperature
        supports_custom_temp = self._supports_custom_temperature(model)

        kwargs = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }

        # Only add temperature if the model supports custom values
        if supports_custom_temp:
            kwargs["temperature"] = temperature
        else:
            # Log that we're using default temperature for this model
            logger.info(
                f"Model '{model}' only supports default temperature (1), "
                f"ignoring requested temperature={temperature}"
            )

        # Use appropriate parameter name based on model version
        if uses_max_completion_tokens:
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens

        # Add bearer token if provided (for Azure Foundry Entra ID auth)
        if bearer_token:
            kwargs["extra_headers"] = {"Authorization": f"Bearer {bearer_token}"}
            logger.info("Using Entra ID bearer token for LLM authentication")

        # Add tools if provided
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        if stream:
            return self._stream_completion(**kwargs)
        else:
            start_time = time.time()
            request_size = len(json.dumps(messages))
            status = "success"
            error_type = None
            prompt_tokens = 0
            completion_tokens = 0
            response_size = 0

            try:
                response = await self.openai_client.chat.completions.create(**kwargs)
                parsed = self._parse_response(response)

                # Extract token usage from response
                if hasattr(response, "usage") and response.usage:
                    prompt_tokens = response.usage.prompt_tokens or 0
                    completion_tokens = response.usage.completion_tokens or 0
                response_size = len(json.dumps(parsed))
            except Exception as e:
                status = "error"
                error_type = type(e).__name__
                raise
            finally:
                duration = time.time() - start_time
                record_llm_request(
                    model=model,
                    provider=self.provider,
                    status=status,
                    duration=duration,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    request_size=request_size,
                    response_size=response_size,
                    error_type=error_type,
                )

            # Check if tools were passed but LLM responded with JSON text instead of tool call
            if tools and not parsed.get("tool_calls"):
                content = parsed.get("content", "")
                converted = self._try_convert_json_to_tool_call(content, tools)
                if converted:
                    logger.info(
                        f"Converted JSON text response to tool call: {converted['function']['name']}"
                    )
                    parsed["tool_calls"] = [converted]
                    # Remove the JSON from content to avoid confusion
                    parsed["content"] = self._strip_json_from_content(content)
                else:
                    logger.warning(
                        f"Tools were provided but LLM did not use them. "
                        f"Response content preview: {content[:200]}"
                    )

            return parsed

    async def _anthropic_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: str,
        temperature: float,
        max_tokens: int,
        stream: bool,
        bearer_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle Anthropic chat completion via direct HTTP with tool support.

        Args:
            bearer_token: Optional Entra ID bearer token for Azure Foundry authentication
        """
        if not self.anthropic_endpoint:
            raise Exception(
                "Anthropic endpoint not configured. Check AZURE_ANTHROPIC_ENDPOINT configuration."
            )

        start_time = time.time()
        request_size = len(json.dumps(messages))
        status = "success"
        error_type = None
        prompt_tokens = 0
        completion_tokens = 0
        response_size = 0

        # Convert OpenAI message format to Anthropic format
        anthropic_messages = []
        system_message = None

        for msg in messages:
            role = msg["role"]
            if role == "system":
                system_message = msg["content"]
            elif role in ["user", "assistant"]:
                # Handle tool_calls in assistant messages
                if role == "assistant" and msg.get("tool_calls"):
                    # Anthropic format: content blocks with tool_use
                    content_blocks = []
                    if msg.get("content"):
                        content_blocks.append({"type": "text", "text": msg["content"]})
                    for tool_call in msg["tool_calls"]:
                        content_blocks.append(
                            {
                                "type": "tool_use",
                                "id": tool_call["id"],
                                "name": tool_call["function"]["name"],
                                "input": json.loads(tool_call["function"]["arguments"]),
                            }
                        )
                    anthropic_messages.append(
                        {"role": "assistant", "content": content_blocks}
                    )
                else:
                    anthropic_messages.append({"role": role, "content": msg["content"]})
            elif role == "tool":
                # Convert tool result to Anthropic format
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.get("tool_call_id"),
                                "content": msg["content"],
                            }
                        ],
                    }
                )

        # Prepare request payload
        # Log max_tokens to debug Azure output limits
        logger.info(f"Anthropic request: max_tokens={max_tokens}")

        payload = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if system_message:
            payload["system"] = system_message

        # Add tools if provided (convert OpenAI format to Anthropic format)
        if tools:
            anthropic_tools = []
            for tool in tools:
                anthropic_tool = {
                    "name": tool["function"]["name"],
                    "description": tool["function"]["description"],
                    "input_schema": tool["function"]["parameters"],
                }
                anthropic_tools.append(anthropic_tool)
            payload["tools"] = anthropic_tools

            # Convert tool_choice
            if isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
                # Force specific tool
                payload["tool_choice"] = {
                    "type": "tool",
                    "name": tool_choice["function"]["name"],
                }
            elif tool_choice == "auto":
                payload["tool_choice"] = {"type": "auto"}
            elif tool_choice == "none":
                payload["tool_choice"] = {"type": "none"}

        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        # Add bearer token if provided (for Azure Foundry Entra ID auth)
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
            logger.info("Using Entra ID bearer token for Anthropic LLM authentication")
        elif self.anthropic_api_key:
            # Fallback to API key if no bearer token (for backward compatibility)
            headers["x-api-key"] = self.anthropic_api_key
            logger.info("Using API key for Anthropic authentication (deprecated)")

        try:
            # Use longer timeout for large context windows (Claude can be slow with 20k+ tokens)
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{self.anthropic_endpoint}v1/messages",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            # Convert Anthropic response to OpenAI format
            content = ""
            tool_calls = []

            if data.get("content"):
                for block in data["content"]:
                    if block.get("type") == "text":
                        content += block.get("text", "")
                    elif block.get("type") == "tool_use":
                        # Convert Anthropic tool_use to OpenAI tool_call format
                        tool_calls.append(
                            {
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(block["input"]),
                                },
                            }
                        )

            stop_reason = data.get("stop_reason")
            usage = data.get("usage", {})

            # Extract token usage for metrics
            prompt_tokens = usage.get("input_tokens", 0)
            completion_tokens = usage.get("output_tokens", 0)

            # Log response details for debugging
            logger.info(
                f"Anthropic response: stop_reason={stop_reason}, "
                f"input_tokens={usage.get('input_tokens')}, "
                f"output_tokens={usage.get('output_tokens')}"
            )

            # Warn if response was truncated due to max_tokens
            if stop_reason == "max_tokens":
                logger.warning(
                    f"Response truncated: hit max_tokens limit. "
                    f"Output tokens: {usage.get('output_tokens')}"
                )

            result = {
                "content": content,
                "role": "assistant",
                "finish_reason": stop_reason,
                "usage": usage,
            }

            if tool_calls:
                result["tool_calls"] = tool_calls

            response_size = len(json.dumps(result))

            return result

        except httpx.HTTPStatusError as e:
            status = "error"
            error_type = "HTTPStatusError"
            error_detail = e.response.text
            logger.error(
                f"Anthropic HTTP error: {e.response.status_code} - {error_detail}"
            )
            raise Exception(
                f"Anthropic API error ({e.response.status_code}): {error_detail}"
            ) from e
        except httpx.TimeoutException as e:
            status = "error"
            error_type = "TimeoutException"
            logger.error(f"Anthropic API timeout after 180s - request may be too large")
            raise Exception(
                f"Anthropic API timeout: Request took too long (>180s). Try reducing context size."
            ) from e
        except Exception as e:
            status = "error"
            error_type = type(e).__name__
            logger.error(f"Anthropic chat completion failed: {e}")
            raise Exception(f"Anthropic API error: {str(e)}") from e
        finally:
            duration = time.time() - start_time
            record_llm_request(
                model=model,
                provider="anthropic",
                status=status,
                duration=duration,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                request_size=request_size,
                response_size=response_size,
                error_type=error_type,
            )

    def _build_tools_system_prompt(
        self, tools: Optional[List[Dict[str, Any]]]
    ) -> Optional[str]:
        """Build a system prompt with tool definitions for CLI providers."""
        if not tools:
            return None
        tool_schemas = []
        for tool in tools:
            fn = tool.get("function", {})
            schema_entry = {
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
            }
            tool_schemas.append(schema_entry)

        tools_json = json.dumps(tool_schemas, indent=2)
        return (
            "You have access to the following tools:\n\n"
            f"{tools_json}\n\n"
            "IMPORTANT: When you need to call a tool, respond with "
            "JSON objects in this EXACT format (each in its own ```json block):\n"
            "```json\n"
            "{\n"
            '  "tool_name": "<tool_name>",\n'
            '  "arguments": { <arguments matching the tool\'s parameters> }\n'
            "}\n"
            "```\n\n"
            "Rules for tool calling:\n"
            "1. Output ONLY the JSON block(s) when calling tools — no explanation before or after\n"
            "2. Use the exact tool name from the list above\n"
            "3. Include all required parameters\n"
            "4. If you do NOT need to call a tool, respond normally with text\n"
            "5. You may call multiple tools in one response — use a separate ```json block for each\n"
            "6. NEVER repeat or echo back tool call arguments (especially file content) in your text responses"
        )

    async def _claude_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: str,
        temperature: float,
        max_tokens: int,
        effort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle Claude chat completion — try direct CLI first, fall back to HTTP bridge."""
        tools_system = self._build_tools_system_prompt(tools)

        # Try direct CLI first
        if self.claude_cli.available:
            start_time = time.time()
            status = "success"
            error_type = None
            try:
                result = await self.claude_cli.run_chat(
                    model=model,
                    messages=messages,
                    system_prompt=tools_system,
                    effort=effort,
                )
                # Extract tool calls from response if tools were passed
                if tools and not result.get("tool_calls"):
                    all_calls = self._try_convert_all_json_tool_calls(
                        result.get("content", ""), tools
                    )
                    if all_calls:
                        names = [c["function"]["name"] for c in all_calls]
                        logger.info(
                            f"Claude CLI: converted {len(all_calls)} JSON "
                            f"tool call(s): {names}"
                        )
                        result["tool_calls"] = all_calls
                        result["content"] = self._strip_all_json_from_content(
                            result.get("content", "")
                        )
                return result
            except Exception as e:
                status = "error"
                error_type = type(e).__name__
                logger.error(f"Claude CLI failed: {e}")
                # Fall through to HTTP bridge if available
                if not self.claude_bridge_url:
                    raise Exception(f"Claude CLI error: {e}") from e
                logger.info("Falling back to Claude HTTP bridge")
            finally:
                duration = time.time() - start_time
                record_llm_request(
                    model=model,
                    provider="claude_cli",
                    status=status,
                    duration=duration,
                    prompt_tokens=0,
                    completion_tokens=0,
                    request_size=0,
                    response_size=0,
                    error_type=error_type,
                )

        # Fall back to HTTP bridge
        return await self._claude_bridge_chat_completion(
            model, messages, tools, tool_choice, temperature, max_tokens
        )

    async def _copilot_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: str,
        temperature: float,
        max_tokens: int,
        effort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle Copilot chat completion — try direct CLI first, fall back to HTTP bridge."""
        tools_system = self._build_tools_system_prompt(tools)

        # Try direct CLI first
        if self.copilot_cli.available:
            start_time = time.time()
            status = "success"
            error_type = None
            try:
                result = await self.copilot_cli.run_chat(
                    model=model,
                    messages=messages,
                    system_prompt=tools_system,
                    effort=effort,
                )
                # Extract tool calls from response if tools were passed
                if tools and not result.get("tool_calls"):
                    all_calls = self._try_convert_all_json_tool_calls(
                        result.get("content", ""), tools
                    )
                    if all_calls:
                        names = [c["function"]["name"] for c in all_calls]
                        logger.info(
                            f"Copilot CLI: converted {len(all_calls)} JSON "
                            f"tool call(s): {names}"
                        )
                        result["tool_calls"] = all_calls
                        result["content"] = self._strip_all_json_from_content(
                            result.get("content", "")
                        )
                return result
            except Exception as e:
                status = "error"
                error_type = type(e).__name__
                logger.error(f"Copilot CLI failed: {e}")
                if not self.copilot_bridge_url:
                    raise Exception(f"Copilot CLI error: {e}") from e
                logger.info("Falling back to Copilot HTTP bridge")
            finally:
                duration = time.time() - start_time
                record_llm_request(
                    model=model,
                    provider="copilot_cli",
                    status=status,
                    duration=duration,
                    prompt_tokens=0,
                    completion_tokens=0,
                    request_size=0,
                    response_size=0,
                    error_type=error_type,
                )

        # Fall back to HTTP bridge
        if not self.copilot_bridge_url:
            raise Exception(
                "Copilot CLI not available and COPILOT_BRIDGE_URL not configured."
            )
        return await self._copilot_bridge_chat_completion(
            model, messages, tools, tool_choice, temperature, max_tokens
        )

    async def _copilot_bridge_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: str,
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        """Handle chat completion via the host-side Copilot Bridge HTTP service."""
        start_time = time.time()
        status = "success"
        error_type = None

        payload: Dict[str, Any] = {"model": model, "messages": messages}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature

        tools_system = self._build_tools_system_prompt(tools)
        if tools_system:
            payload["system_prompt"] = tools_system

        try:
            async with httpx.AsyncClient(timeout=1860.0) as client:
                response = await client.post(
                    f"{self.copilot_bridge_url.rstrip('/')}/chat",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            content = data.get("content", "")
            usage = data.get("usage", {})

            result = {
                "content": content,
                "role": "assistant",
                "finish_reason": data.get("finish_reason", "end_turn"),
                "usage": usage,
            }

            if tools and not result.get("tool_calls"):
                all_calls = self._try_convert_all_json_tool_calls(content, tools)
                if all_calls:
                    result["tool_calls"] = all_calls
                    result["content"] = self._strip_all_json_from_content(content)

            return result

        except httpx.HTTPStatusError as e:
            status = "error"
            error_type = "HTTPStatusError"
            detail = e.response.text[:500]
            raise Exception(
                f"Copilot Bridge error ({e.response.status_code}): {detail}"
            ) from e
        except httpx.TimeoutException:
            status = "error"
            error_type = "TimeoutException"
            raise Exception("Copilot Bridge timeout: request took too long (>1860s)")
        except Exception as e:
            status = "error"
            error_type = type(e).__name__
            raise Exception(f"Copilot Bridge error: {str(e)}") from e
        finally:
            duration = time.time() - start_time
            record_llm_request(
                model=model,
                provider="copilot_bridge",
                status=status,
                duration=duration,
                prompt_tokens=0,
                completion_tokens=0,
                request_size=0,
                response_size=0,
                error_type=error_type,
            )

    async def _claude_bridge_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: str,
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        """Handle chat completion via the host-side Claude Bridge service.

        The bridge wraps the Claude Code CLI subprocess on the Windows host.
        The gateway (running in Docker) communicates with it over HTTP, using
        the same pattern as the Windows Composition Bridge.
        """
        if not self.claude_bridge_url:
            raise Exception(
                "Claude Bridge not configured. Set CLAUDE_BRIDGE_URL "
                "(e.g. http://host.docker.internal:8006)."
            )

        start_time = time.time()
        request_size = len(json.dumps(messages))
        status = "success"
        error_type = None
        prompt_tokens = 0
        completion_tokens = 0
        response_size = 0

        # Build bridge request payload
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature

        # If tools were provided, embed their descriptions in a system prompt
        # with explicit JSON format so Claude can reason about and call them.
        if tools:
            tool_schemas = []
            for tool in tools:
                fn = tool.get("function", {})
                schema_entry = {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {}),
                }
                tool_schemas.append(schema_entry)

            tools_json = json.dumps(tool_schemas, indent=2)
            tools_text = (
                "You have access to the following tools:\n\n"
                f"{tools_json}\n\n"
                "IMPORTANT: When you need to call a tool, respond with "
                "JSON objects in this EXACT format (each in its own ```json block):\n"
                "```json\n"
                "{\n"
                '  "tool_name": "<tool_name>",\n'
                '  "arguments": { <arguments matching the tool\'s parameters> }\n'
                "}\n"
                "```\n\n"
                "Rules for tool calling:\n"
                "1. Output ONLY the JSON block(s) when calling tools — no explanation before or after\n"
                "2. Use the exact tool name from the list above\n"
                "3. Include all required parameters\n"
                "4. If you do NOT need to call a tool, respond normally with text\n"
                "5. You may call multiple tools in one response — use a separate ```json block for each\n"
                "6. NEVER repeat or echo back tool call arguments (especially file content) in your text responses"
            )
            payload["system_prompt"] = tools_text

        try:
            async with httpx.AsyncClient(timeout=1860.0) as client:
                response = await client.post(
                    f"{self.claude_bridge_url.rstrip('/')}/chat",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            content = data.get("content", "")
            usage = data.get("usage", {})
            prompt_tokens = usage.get("input_tokens", 0)
            completion_tokens = usage.get("output_tokens", 0)

            result = {
                "content": content,
                "role": "assistant",
                "finish_reason": data.get("finish_reason", "end_turn"),
                "usage": usage,
            }

            response_size = len(json.dumps(result))

            # If tools were passed, try to detect JSON tool calls in the text.
            # Claude may emit multiple tool calls in one response.
            if tools and not result.get("tool_calls"):
                all_calls = self._try_convert_all_json_tool_calls(content, tools)
                if all_calls:
                    names = [c["function"]["name"] for c in all_calls]
                    logger.info(
                        f"Claude bridge: converted {len(all_calls)} JSON "
                        f"tool call(s): {names}"
                    )
                    result["tool_calls"] = all_calls
                    result["content"] = self._strip_all_json_from_content(content)

            return result

        except httpx.HTTPStatusError as e:
            status = "error"
            error_type = "HTTPStatusError"
            detail = e.response.text[:500]
            logger.error(
                f"Claude Bridge HTTP error: {e.response.status_code} - {detail}"
            )
            raise Exception(
                f"Claude Bridge error ({e.response.status_code}): {detail}"
            ) from e
        except httpx.TimeoutException:
            status = "error"
            error_type = "TimeoutException"
            logger.error("Claude Bridge timeout after 1860s")
            raise Exception("Claude Bridge timeout: request took too long (>1860s)")
        except Exception as e:
            status = "error"
            error_type = type(e).__name__
            logger.error(f"Claude Bridge chat failed: {e}")
            raise Exception(f"Claude Bridge error: {str(e)}") from e
        finally:
            duration = time.time() - start_time
            record_llm_request(
                model=model,
                provider="claude_bridge",
                status=status,
                duration=duration,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                request_size=request_size,
                response_size=response_size,
                error_type=error_type,
            )

    async def _stream_completion(
        self, **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Handle streaming chat completion for OpenAI."""
        try:
            stream = await self.openai_client.chat.completions.create(**kwargs)

            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    choice = chunk.choices[0]

                    # Handle content delta
                    if hasattr(choice.delta, "content") and choice.delta.content:
                        yield {"type": "content", "content": choice.delta.content}

                    # Handle tool call deltas
                    if hasattr(choice.delta, "tool_calls") and choice.delta.tool_calls:
                        for tool_call in choice.delta.tool_calls:
                            yield {"type": "tool_call_delta", "tool_call": tool_call}

                    # Handle completion
                    if choice.finish_reason:
                        yield {"type": "finish", "finish_reason": choice.finish_reason}

        except Exception as e:
            logger.error(f"Streaming completion failed: {e}")
            yield {"type": "error", "error": str(e)}

    def _parse_response(self, response) -> Dict[str, Any]:
        """Parse the completion response into a standardized format."""
        choice = response.choices[0]
        message = choice.message

        result = {
            "content": message.content,
            "finish_reason": choice.finish_reason,
            "tool_calls": [],
        }

        # Parse tool calls if present
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tool_call in message.tool_calls:
                result["tool_calls"].append(
                    {
                        "id": tool_call.id,
                        "type": tool_call.type,
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                )

        return result

    def _try_convert_json_to_tool_call(
        self, content: str, tools: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Try to detect and convert JSON text in response to a proper tool call.

        Handles two formats:
        1. Explicit format: {"tool_name": "...", "arguments": {...}}
           (used by Claude Bridge with our tool prompt)
        2. Implicit format: JSON whose keys match a tool's required parameters
           (fallback for LLMs that output raw parameter JSON)

        Args:
            content: The response content text
            tools: The tools that were provided to the LLM

        Returns:
            A tool call dict if JSON was detected and matched a tool, None otherwise
        """
        if not content:
            return None

        # Build a set of valid tool names for quick lookup
        valid_tool_names = {t.get("function", {}).get("name", "") for t in tools}

        # Extract JSON from the content
        parsed_json = self._extract_json_from_text(content)
        if parsed_json is None:
            return None

        # --- Format 1: Explicit {"tool_name": "...", "arguments": {...}} ---
        if "tool_name" in parsed_json and parsed_json["tool_name"] in valid_tool_names:
            tool_name = parsed_json["tool_name"]
            arguments = parsed_json.get("arguments", {})
            return {
                "id": f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": (
                        json.dumps(arguments)
                        if isinstance(arguments, dict)
                        else str(arguments)
                    ),
                },
            }

        # --- Format 2: Implicit — JSON keys match tool parameters ---
        for tool in tools:
            tool_name = tool.get("function", {}).get("name", "")
            tool_params = (
                tool.get("function", {}).get("parameters", {}).get("properties", {})
            )

            if tool_name == TOOL_CRAWL_AND_REFRESH:
                # Special case: crawl_and_refresh needs "query"
                if "query" in parsed_json:
                    return {
                        "id": f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": TOOL_CRAWL_AND_REFRESH,
                            "arguments": json.dumps(parsed_json),
                        },
                    }
            elif tool_params:
                required_params = (
                    tool.get("function", {}).get("parameters", {}).get("required", [])
                )
                if required_params and all(
                    param in parsed_json for param in required_params
                ):
                    return {
                        "id": f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(parsed_json),
                        },
                    }

        return None

    def _extract_json_from_text(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Extract a JSON object from text content.

        Tries multiple strategies:
        1. JSON in ```json code blocks
        2. JSON starting at beginning of text
        3. JSON after a newline
        """
        if not content:
            return None

        # Strategy 1: JSON in code blocks
        code_block_match = re.search(r"```json?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 2 & 3: JSON starting at beginning or after newline
        start_patterns = [r"^\s*\{", r"\n\s*\{"]
        for pattern in start_patterns:
            match = re.search(pattern, content)
            if match:
                start_idx = match.end() - 1  # Include the {
                # Try progressively longer substrings until valid JSON
                for end_idx in range(start_idx + 2, len(content) + 1):
                    candidate = content[start_idx:end_idx]
                    if candidate.count("{") == candidate.count("}"):
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            continue

        return None

        return None

    def _strip_json_from_content(self, content: str) -> str:
        """
        Remove the JSON portion from the content, keeping any additional text.

        Args:
            content: The original response content

        Returns:
            Content with JSON stripped out
        """
        return self._strip_all_json_from_content(content)

    def _strip_all_json_from_content(self, content: str) -> str:
        """
        Remove ALL JSON blocks (including nested) from content.

        Handles:
        - ```json ... ``` code blocks
        - Bare JSON objects at start of text or after newlines
        """
        if not content:
            return content

        # Pass 1: Remove JSON in code blocks (including nested braces)
        content = re.sub(r"```json?\s*\{.*?\}\s*```", "", content, flags=re.DOTALL)

        # Pass 2: Remove bare JSON objects by finding balanced braces
        result_parts: list[str] = []
        i = 0
        while i < len(content):
            if content[i] == "{":
                # Try to find balanced closing brace
                depth = 0
                j = i
                in_string = False
                escape = False
                while j < len(content):
                    ch = content[j]
                    if escape:
                        escape = False
                    elif ch == "\\" and in_string:
                        escape = True
                    elif ch == '"' and not escape:
                        in_string = not in_string
                    elif not in_string:
                        if ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                            if depth == 0:
                                # Check if this was valid JSON
                                candidate = content[i : j + 1]
                                try:
                                    json.loads(candidate)
                                    # Valid JSON — skip it
                                    i = j + 1
                                    break
                                except json.JSONDecodeError:
                                    # Not valid JSON, keep the text
                                    result_parts.append(content[i])
                                    i += 1
                                    break
                    j += 1
                else:
                    # Unbalanced braces — keep as text
                    result_parts.append(content[i])
                    i += 1
            else:
                result_parts.append(content[i])
                i += 1

        return "".join(result_parts).strip()

    def _try_convert_all_json_tool_calls(
        self, content: str, tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Extract ALL JSON tool calls from content (Claude may emit several).

        Only recognises the explicit format: {"tool_name": "...", "arguments": {...}}
        Implicit matching (matching JSON keys to tool schemas) is intentionally
        disabled — it produced massive false-positive rates (59+ bogus calls).

        Returns a list of tool call dicts (OpenAI format), or empty list.
        """
        if not content:
            return []

        # Cap: no single LLM response should produce more than 10 tool calls
        MAX_TOOL_CALLS_PER_RESPONSE = 10

        json_objects = self._extract_all_json_from_text(content)
        if not json_objects:
            return []

        valid_tool_names = {t.get("function", {}).get("name", "") for t in tools}
        calls: list[dict[str, Any]] = []

        for parsed_json in json_objects:
            if len(calls) >= MAX_TOOL_CALLS_PER_RESPONSE:
                logger.warning(
                    f"Tool call cap reached ({MAX_TOOL_CALLS_PER_RESPONSE}), "
                    f"ignoring remaining JSON objects"
                )
                break

            # Only accept explicit format: {"tool_name": "...", "arguments": {...}}
            if (
                "tool_name" in parsed_json
                and parsed_json["tool_name"] in valid_tool_names
            ):
                arguments = parsed_json.get("arguments", {})
                calls.append(
                    {
                        "id": f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": parsed_json["tool_name"],
                            "arguments": (
                                json.dumps(arguments)
                                if isinstance(arguments, dict)
                                else str(arguments)
                            ),
                        },
                    }
                )

        # Fall back to single-extraction for backward compat
        if not calls:
            single = self._try_convert_json_to_tool_call(content, tools)
            if single:
                calls.append(single)

        return calls

    def _extract_all_json_from_text(self, content: str) -> list[dict[str, Any]]:
        """
        Extract ALL JSON objects from text content.

        Finds JSON in code blocks and bare JSON objects.
        """
        if not content:
            return []

        results: list[dict[str, Any]] = []

        # Strategy 1: All JSON code blocks
        for m in re.finditer(r"```json?\s*(\{.*?\})\s*```", content, re.DOTALL):
            try:
                results.append(json.loads(m.group(1)))
            except json.JSONDecodeError:
                pass

        if results:
            return results

        # Strategy 2: Bare JSON objects (balanced-brace extraction)
        i = 0
        while i < len(content):
            if content[i] == "{":
                depth = 0
                j = i
                in_string = False
                escape = False
                while j < len(content):
                    ch = content[j]
                    if escape:
                        escape = False
                    elif ch == "\\" and in_string:
                        escape = True
                    elif ch == '"' and not escape:
                        in_string = not in_string
                    elif not in_string:
                        if ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                            if depth == 0:
                                candidate = content[i : j + 1]
                                try:
                                    results.append(json.loads(candidate))
                                except json.JSONDecodeError:
                                    pass
                                i = j + 1
                                break
                    j += 1
                else:
                    i += 1
            else:
                i += 1

        return results

    async def create_embeddings(
        self, texts: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        """
        Create embeddings for a list of texts.

        Args:
            texts: List of texts to embed
            model: Embedding model override

        Returns:
            List of embedding vectors
        """
        if not model:
            model = os.getenv("EMBED_MODEL", "text-embedding-3-large")

        try:
            # Handle batching for large requests
            batch_size = 100
            all_embeddings = []

            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]

                response = await self.client.embeddings.create(model=model, input=batch)

                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)

            return all_embeddings

        except Exception as e:
            logger.error(f"Embedding creation failed: {e}")
            raise

    async def health_check(self, model: str = "gpt-4") -> Dict[str, Any]:
        """Check if the LLM client is working properly.

        Args:
            model: Model name to test (default: gpt-4)
        """
        try:
            response = await self.chat_completion(
                messages=[{"role": "user", "content": "Hello"}],
                model=model,
                max_tokens=10,
            )

            return {
                "status": "healthy",
                "provider": self.provider,
                "model": model,
                "response_received": bool(response.get("content")),
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": self.provider,
                "model": model,
                "error": str(e),
            }


# Global client instance
_llm_client = None


async def get_llm_client() -> LLMClient:
    """Get or create the global LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client

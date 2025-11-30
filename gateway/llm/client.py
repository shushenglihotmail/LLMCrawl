"""
LLM client for OpenAI, Azure OpenAI, and Anthropic integration.
Handles chat completions, tool calling, and streaming.
"""  # noqa: F401

import asyncio  # noqa: F401
import json
import logging
import os
import re
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
import openai  # noqa: F401
from openai import AsyncAzureOpenAI, AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified client for OpenAI and Azure OpenAI with tool calling support."""

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()

        # Initialize OpenAI client
        if self.provider == "azure":
            self.openai_client = AsyncAzureOpenAI(
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            )
        else:
            self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Store Anthropic endpoint configuration for direct HTTP calls
        self.anthropic_endpoint = (
            os.getenv("AZURE_ANTHROPIC_ENDPOINT") if self.provider == "azure" else None
        )
        self.anthropic_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        if self.anthropic_endpoint:
            logger.info(f"Anthropic endpoint configured: {self.anthropic_endpoint}")

        # For backward compatibility
        self.client = self.openai_client
        logger.info(f"Initialized LLM client: {self.provider}")

    def get_model_config(self, model_name: str) -> tuple[str, str]:
        """
        Get Azure deployment name and provider type for a given model name.

        For Azure: Maps from model name (user selection) to deployment_name and provider_type.
        For OpenAI: Returns model_name as-is with 'openai' provider.

        Args:
            model_name: The model name selected by user (e.g., 'claude-sonnet-4-5')

        Returns:
            Tuple of (deployment_name, provider_type)
        """
        if self.provider != "azure":
            return model_name, "openai"

        # Parse LLM_MODELS to find deployment_name and provider_type
        try:
            models_json = os.getenv("LLM_MODELS", "[]")
            models_config = json.loads(models_json)

            for model in models_config:
                if model.get("name") == model_name:
                    deployment_name = model.get("deployment_name", model_name)
                    provider_type = model.get("provider_type", "openai")
                    logger.info(
                        f"Resolved model '{model_name}' to deployment '{deployment_name}' (provider: {provider_type})"
                    )
                    return deployment_name, provider_type

            # Model not found in config, assume OpenAI
            logger.warning(
                f"Model '{model_name}' not found in LLM_MODELS config, assuming OpenAI"
            )
            return model_name, "openai"

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM_MODELS: {e}")
            return model_name, "openai"

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.1,
        max_tokens: int = 2000,
        stream: bool = False,
    ) -> Dict[str, Any] | AsyncGenerator[Dict[str, Any], None]:
        """
        Create a chat completion with optional tool calling.

        Args:
            messages: Chat messages including system prompts
            model: Model name selected by client (will be resolved to deployment_name for Azure)
            tools: Available tools for function calling
            tool_choice: "auto", "none", or specific tool
            temperature: Sampling temperature
            max_tokens: Maximum response tokens (respects MAX_INPUT_TOKENS)
            stream: Whether to stream the response

        Returns:
            Chat completion response or stream generator
        """
        try:
            # Resolve deployment name and provider type
            deployment_name, provider_type = self.get_model_config(model)
            logger.info(
                f"Model resolution: '{model}' -> '{deployment_name}' (provider: {provider_type})"
            )

            # Route to appropriate client based on provider type
            if provider_type == "anthropic":
                return await self._anthropic_chat_completion(
                    deployment_name,
                    messages,
                    tools,
                    tool_choice,
                    temperature,
                    max_tokens,
                    stream,
                )
            else:
                return await self._openai_chat_completion(
                    deployment_name,
                    messages,
                    tools,
                    tool_choice,
                    temperature,
                    max_tokens,
                    stream,
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
    ) -> Dict[str, Any] | AsyncGenerator[Dict[str, Any], None]:
        """Handle OpenAI/Azure OpenAI chat completion."""
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        # Add tools if provided
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        if stream:
            return self._stream_completion(**kwargs)
        else:
            response = await self.openai_client.chat.completions.create(**kwargs)
            parsed = self._parse_response(response)

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
    ) -> Dict[str, Any]:
        """Handle Anthropic chat completion via direct HTTP with tool support."""
        if not self.anthropic_endpoint:
            raise Exception(
                "Anthropic endpoint not configured. Check AZURE_ANTHROPIC_ENDPOINT configuration."
            )

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
            "x-api-key": self.anthropic_api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

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

            result = {
                "content": content,
                "role": "assistant",
                "finish_reason": data.get("stop_reason"),
            }

            if tool_calls:
                result["tool_calls"] = tool_calls

            return result

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text
            logger.error(
                f"Anthropic HTTP error: {e.response.status_code} - {error_detail}"
            )
            raise Exception(
                f"Anthropic API error ({e.response.status_code}): {error_detail}"
            ) from e
        except httpx.TimeoutException as e:
            logger.error(f"Anthropic API timeout after 180s - request may be too large")
            raise Exception(
                f"Anthropic API timeout: Request took too long (>180s). Try reducing context size."
            ) from e
        except Exception as e:
            logger.error(f"Anthropic chat completion failed: {e}")
            raise Exception(f"Anthropic API error: {str(e)}") from e

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

        Some LLMs output tool call parameters as JSON text instead of using the
        function calling API. This method detects such patterns and converts them.

        Args:
            content: The response content text
            tools: The tools that were provided to the LLM

        Returns:
            A tool call dict if JSON was detected and matched a tool, None otherwise
        """
        if not content:
            return None

        # Try to extract JSON from the content
        # Look for JSON that starts at the beginning or after a newline
        json_patterns = [
            r"^\s*(\{[^{}]*\})",  # JSON at start
            r"\n\s*(\{[^{}]*\})",  # JSON after newline
            r"```json?\s*(\{[^{}]*\})\s*```",  # JSON in code block
        ]

        json_str = None
        for pattern in json_patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                json_str = match.group(1)
                break

        if not json_str:
            return None

        try:
            parsed_json = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        # Check if the JSON matches any of our tool schemas
        # For crawl_and_refresh, we expect: query, and optionally seed_urls, freshness_days, depth
        for tool in tools:
            tool_name = tool.get("function", {}).get("name", "")
            tool_params = (
                tool.get("function", {}).get("parameters", {}).get("properties", {})
            )

            if tool_name == "crawl_and_refresh":
                # Check if JSON has the expected fields for crawl_and_refresh
                if "query" in parsed_json:
                    # This looks like a crawl_and_refresh call!
                    # Build the tool call structure
                    return {
                        "id": f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": "crawl_and_refresh",
                            "arguments": json.dumps(parsed_json),
                        },
                    }

            # Generic check: if JSON keys match tool parameter names
            elif tool_params:
                required_params = (
                    tool.get("function", {}).get("parameters", {}).get("required", [])
                )
                # Check if all required params are present in the JSON
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

    def _strip_json_from_content(self, content: str) -> str:
        """
        Remove the JSON portion from the content, keeping any additional text.

        Args:
            content: The original response content

        Returns:
            Content with JSON stripped out
        """
        if not content:
            return content

        # Remove JSON at the start
        content = re.sub(r"^\s*\{[^{}]*\}\s*", "", content)
        # Remove JSON in code blocks
        content = re.sub(r"```json?\s*\{[^{}]*\}\s*```\s*", "", content)

        return content.strip()

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

"""
LLM client for OpenAI and Azure OpenAI integration.
Handles chat completions, tool calling, and streaming.
"""

import os
import json
import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator
import openai
from openai import AsyncOpenAI, AsyncAzureOpenAI
import logging

logger = logging.getLogger(__name__)

class LLMClient:
    """Unified client for OpenAI and Azure OpenAI with tool calling support."""
    
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()
        self.chat_model = os.getenv("CHAT_MODEL", "gpt-4-turbo-preview")
        
        if self.provider == "azure":
            self.client = AsyncAzureOpenAI(
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
            )
        else:
            self.client = AsyncOpenAI(
                api_key=os.getenv("OPENAI_API_KEY")
            )
            
        logger.info(f"Initialized LLM client: {self.provider}, model: {self.chat_model}")
    
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.1,
        max_tokens: int = 2000,
        stream: bool = False
    ) -> Dict[str, Any] | AsyncGenerator[Dict[str, Any], None]:
        """
        Create a chat completion with optional tool calling.
        
        Args:
            messages: Chat messages including system prompts
            tools: Available tools for function calling
            tool_choice: "auto", "none", or specific tool
            temperature: Sampling temperature
            max_tokens: Maximum response tokens
            stream: Whether to stream the response
            
        Returns:
            Chat completion response or stream generator
        """
        try:
            kwargs = {
                "model": self.chat_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": stream
            }
            
            # Add tools if provided
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice
                
            if stream:
                return self._stream_completion(**kwargs)
            else:
                response = await self.client.chat.completions.create(**kwargs)
                return self._parse_response(response)
                
        except Exception as e:
            logger.error(f"Chat completion failed: {e}")
            raise
    
    async def _stream_completion(self, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        """Handle streaming chat completion."""
        try:
            stream = await self.client.chat.completions.create(**kwargs)
            
            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    choice = chunk.choices[0]
                    
                    # Handle content delta
                    if hasattr(choice.delta, 'content') and choice.delta.content:
                        yield {
                            "type": "content",
                            "content": choice.delta.content
                        }
                    
                    # Handle tool call deltas
                    if hasattr(choice.delta, 'tool_calls') and choice.delta.tool_calls:
                        for tool_call in choice.delta.tool_calls:
                            yield {
                                "type": "tool_call_delta",
                                "tool_call": tool_call
                            }
                    
                    # Handle completion
                    if choice.finish_reason:
                        yield {
                            "type": "finish",
                            "finish_reason": choice.finish_reason
                        }
                        
        except Exception as e:
            logger.error(f"Streaming completion failed: {e}")
            yield {
                "type": "error",
                "error": str(e)
            }
    
    def _parse_response(self, response) -> Dict[str, Any]:
        """Parse the completion response into a standardized format."""
        choice = response.choices[0]
        message = choice.message
        
        result = {
            "content": message.content,
            "finish_reason": choice.finish_reason,
            "tool_calls": []
        }
        
        # Parse tool calls if present
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tool_call in message.tool_calls:
                result["tool_calls"].append({
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    }
                })
        
        return result
    
    async def create_embeddings(
        self,
        texts: List[str],
        model: Optional[str] = None
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
                batch = texts[i:i + batch_size]
                
                response = await self.client.embeddings.create(
                    model=model,
                    input=batch
                )
                
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
                
            return all_embeddings
            
        except Exception as e:
            logger.error(f"Embedding creation failed: {e}")
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if the LLM client is working properly."""
        try:
            response = await self.chat_completion(
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10
            )
            
            return {
                "status": "healthy",
                "provider": self.provider,
                "model": self.chat_model,
                "response_received": bool(response.get("content"))
            }
            
        except Exception as e:
            return {
                "status": "unhealthy", 
                "provider": self.provider,
                "model": self.chat_model,
                "error": str(e)
            }

# Global client instance
_llm_client = None

async def get_llm_client() -> LLMClient:
    """Get or create the global LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
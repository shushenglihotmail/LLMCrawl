"""
Chat router with streaming support and tool calling integration.
Main endpoint for conversational interactions with the RAG system.
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..llm.client import get_llm_client
from ..llm.prompts import (
    CRAWL_AND_REFRESH_TOOL,
    build_messages_with_examples,
    should_trigger_crawl,
)
from ..routers.tools import get_tool_handler
from ..utils.conversation_store import get_conversation_store
from ..utils.logging import get_logger, log_request, log_response

logger = get_logger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    """Chat request model."""

    message: str = Field(..., description="User message")
    conversation_id: Optional[str] = Field(
        None, description="Conversation ID for context"
    )
    stream: bool = Field(False, description="Enable streaming response")
    force_refresh: bool = Field(
        False, description="Force web crawling even for general questions"
    )
    max_tokens: int = Field(2000, description="Maximum response tokens")
    temperature: float = Field(0.1, description="Sampling temperature")


class ChatResponse(BaseModel):
    """Chat response model."""

    response: str
    conversation_id: str
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    duration_ms: float


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, req: Request):
    """
    Main chat endpoint with automatic tool calling and streaming support.

    Automatically triggers web crawling for queries about recent events,
    news, earnings, etc. Returns responses with proper citations.
    """
    request_id = str(uuid.uuid4())
    start_time = datetime.now()

    log_request(
        logger,
        request_id,
        "POST",
        "/chat",
        message_length=len(request.message),
        stream=request.stream,
        conversation_id=request.conversation_id,
    )

    try:
        llm_client = await get_llm_client()
        tool_handler = get_tool_handler()
        conversation_store = get_conversation_store()

        # Generate or use existing conversation ID
        conversation_id = request.conversation_id or str(uuid.uuid4())

        # Load conversation history if continuing an existing conversation
        previous_messages = []
        if request.conversation_id:
            history = conversation_store.get_messages(request.conversation_id)
            logger.info(
                f"Loaded {len(history)} previous messages for conversation {request.conversation_id}"
            )
            previous_messages = history

        # Build messages with system prompts and examples
        base_messages = build_messages_with_examples(request.message)

        # If we have previous conversation history, insert it after system prompt + examples
        if previous_messages:
            # base_messages structure: [system, example1_user, example1_assistant, example2_user, example2_assistant, current_user]
            # We want: [system, examples..., history..., current_user]
            # Remove the current user message from base_messages (it's the last one)
            system_and_examples = base_messages[:-1]
            # Combine: system + examples + history + new user message
            messages = (
                system_and_examples
                + previous_messages
                + [{"role": "user", "content": request.message}]
            )
            logger.info(
                f"Message structure: {len(system_and_examples)} system+examples + {len(previous_messages)} history messages"
            )
        else:
            # New conversation - use base_messages as-is
            messages = base_messages

        # Store the new user message
        conversation_store.add_message(conversation_id, "user", request.message)

        # Determine if we should include tools
        tools = None
        tool_choice = "auto"

        # Include crawl tool if:
        # 1. Current query suggests need for fresh info
        # 2. User forces refresh
        # 3. Previous conversation mentioned news/events (context suggests continuation)
        should_include_tools = (
            should_trigger_crawl(request.message) or request.force_refresh
        )

        # Check if previous conversation context suggests this is a follow-up to a news query
        if not should_include_tools and previous_messages:
            # Look at recent messages for news/event keywords
            recent_context = " ".join(
                [
                    msg.get("content", "")[:200]
                    for msg in previous_messages[-4:]  # Last 2 exchanges
                    if isinstance(msg.get("content"), str)
                ]
            ).lower()
            # If recent context mentioned news/events, keep tools available for follow-ups
            if any(
                word in recent_context
                for word in [
                    "news",
                    "event",
                    "headline",
                    "story",
                    "article",
                    "report",
                    "coverage",
                ]
            ):
                should_include_tools = True
                logger.info(
                    f"Including tools based on conversation context about news/events"
                )

        if should_include_tools:
            tools = [CRAWL_AND_REFRESH_TOOL]
            # Only force tool for explicit fresh data queries, not follow-ups
            if should_trigger_crawl(request.message):
                tool_choice = {
                    "type": "function",
                    "function": {"name": "crawl_and_refresh"},
                }
                logger.info(
                    f"Including crawl tool (forced) for query: {request.message[:100]}..."
                )
            else:
                # For follow-ups, make tools available but let LLM decide
                tool_choice = "auto"
                logger.info(f"Including crawl tool (auto) based on context")

        if request.stream:
            return StreamingResponse(
                _stream_chat_response(
                    llm_client,
                    tool_handler,
                    messages,
                    tools,
                    tool_choice,
                    request,
                    request_id,
                ),
                media_type="text/plain",
            )
        else:
            result = await _complete_chat_response(
                llm_client,
                tool_handler,
                messages,
                tools,
                tool_choice,
                request,
                request_id,
            )

            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_response(logger, request_id, 200, duration_ms)

            return result

    except Exception as e:
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        log_response(logger, request_id, 500, duration_ms, error=str(e))

        logger.error(f"Chat endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {e}")


async def _complete_chat_response(
    llm_client,
    tool_handler,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    tool_choice: str,
    request: ChatRequest,
    request_id: str,
) -> ChatResponse:
    """Handle non-streaming chat response with tool calling."""

    conversation_id = request.conversation_id or str(uuid.uuid4())
    all_tool_calls = []
    sources = []

    # First LLM call
    logger.info(f"Calling LLM with tools: {bool(tools)}, tool_choice: {tool_choice}")
    response = await llm_client.chat_completion(
        messages=messages,
        tools=tools,
        tool_choice=tool_choice,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        stream=False,
    )

    logger.info(
        f"First LLM response has tool_calls: {bool(response.get('tool_calls'))}"
    )
    logger.info(
        f"First LLM response content: {response.get('content', '')[:200] if response.get('content') else 'None'}"
    )

    # Handle tool calls if present
    if response.get("tool_calls"):
        # Add assistant message with tool calls to conversation
        # Azure may return content=None when tool_choice is forced
        content_val = response.get("content") or ""
        assistant_message = {
            "role": "assistant",
            "content": content_val,
            "tool_calls": response["tool_calls"],
        }
        messages.append(assistant_message)

        # Don't store intermediate tool call message - only store final response

        # Execute tool calls
        for tool_call in response["tool_calls"]:
            all_tool_calls.append(tool_call)

            tool_result = await tool_handler.handle_tool_call(tool_call, request_id)
            messages.append(tool_result)

            # Don't store tool results in conversation history

            # Extract sources from tool result
            try:
                result_data = json.loads(tool_result["content"])
                if "hits" in result_data:
                    sources.extend(result_data["hits"])
            except:
                pass

        # Second LLM call with tool results (without tools to prevent additional calls)
        logger.info(
            f"Making second LLM call with {len(messages)} messages including tool results"
        )
        final_response = await llm_client.chat_completion(
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=False,
        )

        final_content = final_response.get("content", "")
        logger.info(f"Final LLM response length: {len(final_content)}")
    else:
        final_content = response.get("content", "")

    # Store assistant's response in conversation history
    conversation_store = get_conversation_store()
    conversation_store.add_message(conversation_id, "assistant", final_content)
    logger.info(f"Stored assistant response in conversation {conversation_id}")

    return ChatResponse(
        response=final_content,
        conversation_id=conversation_id,
        sources=sources,
        tool_calls=all_tool_calls,
        duration_ms=0,  # Will be set by caller
    )


async def _stream_chat_response(
    llm_client,
    tool_handler,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    tool_choice: str,
    request: ChatRequest,
    request_id: str,
):
    """Handle streaming chat response with tool calling."""

    conversation_id = request.conversation_id or str(uuid.uuid4())

    try:
        # Send conversation metadata
        yield f"data: {json.dumps({'type': 'start', 'conversation_id': conversation_id})}\n\n"

        # First LLM call (streaming)
        stream = await llm_client.chat_completion(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
        )

        tool_calls = []
        collected_content = ""

        async for chunk in stream:
            if chunk["type"] == "content":
                content = chunk["content"]
                collected_content += content
                yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"

            elif chunk["type"] == "tool_call_delta":
                # Collect tool call information
                # Note: In a full implementation, you'd need to accumulate these deltas
                pass

            elif chunk["type"] == "finish":
                if chunk["finish_reason"] == "tool_calls":
                    yield f"data: {json.dumps({'type': 'tool_start'})}\n\n"

                    # For streaming, we'd need to handle tool calls here
                    # This is a simplified version - in production you'd want
                    # to properly accumulate tool call deltas first

                    yield f"data: {json.dumps({'type': 'tool_complete'})}\n\n"

        # Send completion
        yield f"data: {json.dumps({'type': 'complete'})}\n\n"

    except Exception as e:
        logger.error(f"Streaming failed: {e}")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        llm_client = await get_llm_client()
        llm_health = await llm_client.health_check()

        return {
            "status": "healthy",
            "service": "gateway",
            "llm": llm_health,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "gateway",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }

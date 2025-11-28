"""
Agent API router - Chat endpoint for code intelligence.

Provides:
- POST /agent/chat - Execute agent workflow with tool calling
- GET /agent/health - Health check
"""

import fnmatch
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from gateway.agents import AgentConfig, convert_mcp_tool_to_openai
from gateway.agents.unified_workflow import (
    UnifiedWorkflowRequest,
    UnifiedWorkflowResponse,
)
from gateway.llm.client import LLMClient
from gateway.routers.tools import get_tool_handler
from gateway.utils.azdo_uri import is_azdo_uri, parse_azdo_uri
from gateway.utils.conversation_store import get_conversation_store
from gateway.utils.logging import log_request, log_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

# Initialize agent config (singleton)
_agent_config: Optional[AgentConfig] = None


# =============================================================================
# Helper Functions - Path Expansion
# =============================================================================


async def _expand_paths(
    agent: AgentConfig, path_list: List[str]
) -> List[str]:
    """
    Expand path list to actual file paths using conventions:
    - 'azdo:...' = Azure DevOps path (pass through, no expansion)
    - 'file.cpp' = direct file
    - '*.cpp' or 'x*.json' = wildcard pattern
    - 'folder/' or 'folder\\' = folder (non-recursive)
    - 'folder/**' = folder (recursive)
    """
    expanded_files = []

    for path in path_list:
        # Azure DevOps paths (azdo:) - pass through without expansion
        if path.startswith("azdo:"):
            expanded_files.append(path)
            continue

        # Normalize backslashes to forward slashes (Windows paths)
        path_normalized = path.replace("\\", "/")

        # Check for recursive folder pattern
        if path_normalized.endswith("/**"):
            folder = path_normalized[:-3]
            files = await _list_folder_files(agent, folder, recursive=True)
            expanded_files.extend(files)
        # Check for folder (ends with slash)
        elif path_normalized.endswith("/"):
            folder = path_normalized[:-1]
            files = await _list_folder_files(agent, folder, recursive=False)
            expanded_files.extend(files)
        # Check for wildcard pattern
        elif "*" in path_normalized:
            parts = path_normalized.split("/")
            pattern = parts[-1]
            folder = "/".join(parts[:-1]) if len(parts) > 1 else "."
            files = await _list_folder_files(agent, folder, False)
            matching = [f for f in files if fnmatch.fnmatch(f.split("/")[-1], pattern)]
            expanded_files.extend(matching)
        else:
            # Direct file path
            expanded_files.append(path_normalized)

    return expanded_files


async def _list_folder_files(
    agent: AgentConfig, folder_path: str, recursive: bool
) -> List[str]:
    """List files in a folder via MCP server."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{agent.mcp_url}/invoke",
                json={
                    "tool_name": "list_files",
                    "arguments": {"folder_path": folder_path, "recursive": recursive},
                },
            )
            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                files_data = result["result"].get("files", [])
                return [f["path"] for f in files_data if f.get("type") == "file"]
            return []
    except Exception as e:
        logger.error(f"Failed to list folder {folder_path}: {e}")
        return []


# =============================================================================
# Helper Functions - Content Extraction
# =============================================================================


def _extract_content_from_response(file_data: Dict[str, Any]) -> str:
    """Extract content from MCP response, handling various formats."""
    if "content" in file_data:
        return file_data["content"]
    elif "result" in file_data:
        result = file_data["result"]
        if isinstance(result, dict):
            return result.get("content", "")
        elif isinstance(result, list) and len(result) > 0:
            if isinstance(result[0], dict) and "text" in result[0]:
                return result[0]["text"]
            return str(result[0])
        return str(result)
    return ""


# =============================================================================
# Helper Functions - Context Gathering
# =============================================================================


async def _gather_target_files(
    agent: AgentConfig,
    paths: List[str],
    context_gathered: Dict[str, int],
) -> List[str]:
    """Gather content from target files (Azure DevOps)."""
    if not paths:
        return []

    target_content = []
    logger.info(f"Gathering {len(paths)} target paths from Azure DevOps")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for path in paths:
                # Handle azdo: prefixed paths
                if path.startswith("azdo:"):
                    file_path = path[5:]
                    if not file_path.startswith("/"):
                        file_path = "/" + file_path
                else:
                    file_path = path

                logger.info(f"Fetching target file: {file_path}")
                response = await client.post(
                    f"{agent.azure_devops_mcp_url}/invoke",
                    json={
                        "tool_name": "get_azure_devops_file",
                        "arguments": {"file_path": file_path},
                    },
                )

                if response.status_code == 200:
                    file_data = response.json()
                    content = _extract_content_from_response(file_data)
                    if content:
                        target_content.append(f"File: {file_path}\n\n{content}")
                        context_gathered["target_files"] += 1
                        logger.info(f"Extracted {len(content)} chars from {file_path}")
                else:
                    logger.error(f"Failed to fetch {file_path}: HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to gather target paths: {e}", exc_info=True)

    return target_content


async def _gather_reference_files(
    agent: AgentConfig,
    paths: List[str],
    context_gathered: Dict[str, int],
) -> List[str]:
    """Gather content from reference files (local or Azure DevOps)."""
    if not paths:
        return []

    reference_content = []
    azure_devops_mcp_url = os.getenv(
        "AZURE_DEVOPS_MCP_URL", "http://azure-devops-mcp-server:8004"
    )
    logger.info(f"Gathering {len(paths)} reference files")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for file_path in paths:
                if is_azdo_uri(file_path):
                    # Azure DevOps file
                    parsed = parse_azdo_uri(file_path)
                    if not parsed:
                        logger.error(f"Failed to parse azdo URI: {file_path}")
                        continue

                    arguments = {"file_path": parsed.path}
                    if parsed.project:
                        arguments["project"] = parsed.project
                    if parsed.repository:
                        arguments["repository"] = parsed.repository
                    if parsed.branch:
                        arguments["branch"] = parsed.branch

                    response = await client.post(
                        f"{azure_devops_mcp_url}/invoke",
                        json={"tool_name": "get_azure_devops_file", "arguments": arguments},
                    )
                else:
                    # Local file
                    logger.info(f"Reading local reference file: {file_path}")
                    response = await client.post(
                        f"{agent.mcp_url}/invoke",
                        json={
                            "tool_name": "read_local_file",
                            "arguments": {"file_path": file_path},
                        },
                    )

                if response.status_code == 200:
                    file_data = response.json()
                    content = _extract_content_from_response(file_data)
                    if content:
                        reference_content.append(f"Reference File: {file_path}\n\n{content}")
                        context_gathered["reference_files"] += 1
                        logger.info(f"Extracted {len(content)} chars from {file_path}")
                else:
                    logger.error(f"Failed to read {file_path}: HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to gather reference files: {e}", exc_info=True)

    return reference_content


async def _crawl_urls(
    agent: AgentConfig,
    request: UnifiedWorkflowRequest,
    request_id: str,
    context_gathered: Dict[str, int],
) -> List[str]:
    """Crawl seed URLs and optionally index them."""
    if not request.seed_urls:
        return []

    crawled_content = []
    logger.info(f"Crawling {len(request.seed_urls)} seed URLs, browse_web={request.browse_web}")

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                f"{agent.crawler_url}/crawl",
                json={
                    "query": request.user_message[:200],
                    "seed_urls": request.seed_urls,
                    "freshness_days": 90,
                    "depth": request.crawl_depth,
                    "max_results": 10,
                    "allow_web_search": request.browse_web,
                },
                headers={"X-Request-ID": request_id},
            )

            if response.status_code == 200:
                crawl_data = response.json()
                docs = crawl_data.get("docs", [])

                # Index documents if embedding enabled
                if request.enable_embedding and docs:
                    logger.info(f"Indexing {len(docs)} crawled documents")
                    await client.post(
                        f"{agent.indexer_url}/index",
                        json={"docs": docs},
                        headers={"X-Request-ID": request_id},
                    )

                # Add crawled content
                for doc in docs:
                    source = doc.get("source", "unknown")
                    crawled_content.append(
                        f"URL: {doc.get('url', 'unknown')}\n"
                        f"Source: {source}\n\n"
                        f"{doc.get('markdown', '')[:2000]}"
                    )
                    if source == "firecrawl":
                        context_gathered["web_search_results"] += 1
                    else:
                        context_gathered["crawled_urls"] += 1
    except Exception as e:
        logger.error(f"Failed to crawl content: {e}")

    return crawled_content


# =============================================================================
# Helper Functions - Message Building
# =============================================================================


def _build_context_string(
    target_content: List[str],
    reference_content: List[str],
    crawled_content: List[str],
) -> str:
    """Build combined context string from all sources."""
    context_parts = []

    if target_content:
        context_parts.append(
            f"=== TARGET FILES ({len(target_content)}) ===\n\n"
            + "\n\n---\n\n".join(target_content)
        )

    if reference_content:
        context_parts.append(
            f"=== REFERENCE FILES ({len(reference_content)}) ===\n\n"
            + "\n\n---\n\n".join(reference_content)
        )

    if crawled_content:
        context_parts.append(
            f"=== WEB CONTENT ({len(crawled_content)}) ===\n\n"
            + "\n\n---\n\n".join(crawled_content)
        )

    return "\n\n===\n\n".join(context_parts) if context_parts else ""


def _build_system_prompt(expose_to_llm: Dict[str, bool]) -> str:
    """Build system prompt with tool descriptions."""
    system_prompt = (
        "You are a helpful assistant with access to tools for fetching current information.\n\n"
        "AVAILABLE TOOLS:\n"
    )

    tool_descriptions = []
    if expose_to_llm.get("azure_devops_mcp", False):
        tool_descriptions.append(
            "- **Azure DevOps MCP Tools**: Search and read files from Azure DevOps repositories\n"
            "  - `search_azure_devops_code`: Search for code patterns in files (PREFERRED for finding packages, dependencies)\n"
            "  - `get_azure_devops_file`: Read specific file contents when you know the exact path\n"
            "  - `search_azure_devops_files`: Find files by name/path patterns\n"
            "    **CRITICAL RESTRICTION**: When using recursive=true, you MUST provide either:\n"
            "      * A specific filename in file_pattern (e.g., 'package.json')\n"
            "      * OR a search keyword to filter results\n"
            "    **NEVER** use recursive=true with only path_pattern and extension - this will timeout!"
        )

    if expose_to_llm.get("local_mcp", False):
        tool_descriptions.append(
            "- **Local MCP Tools**: Access local workspace files and directories\n"
            "  Use these when user asks about local files or workspace structure."
        )

    if expose_to_llm.get("crawler", False):
        tool_descriptions.append(
            "- **Crawler Tool** (`crawl_and_refresh`): Fetch and index web content\n"
            "  Use this when user asks for current web information or recent news."
        )

    if tool_descriptions:
        system_prompt += "\n".join(tool_descriptions) + "\n\n"

    system_prompt += (
        "CONVERSATION HANDLING:\n"
        "- **ALWAYS focus on answering the LATEST user message only** - this is the PRIMARY ASK.\n"
        "- Previous messages are provided as CONTEXT/BACKGROUND only.\n\n"
        "CRITICAL RULES FOR TOOL USAGE:\n"
        "1. You MUST use function calling to invoke tools - DO NOT output JSON as text.\n"
        "2. When asked about packages/dependencies, call search_azure_devops_code or search_azure_devops_files.\n"
        "3. DO NOT ask for clarification about which tool to use - just call the most appropriate tool.\n"
        "4. If context is already provided, analyze it directly.\n\n"
        "Remember: USE FUNCTION CALLING, NOT TEXT OUTPUT OF JSON."
    )

    return system_prompt


def _build_messages(
    system_prompt: str,
    full_context: str,
    user_message: str,
    conversation_id: Optional[str],
    clear_history: bool,
) -> List[Dict[str, str]]:
    """Build message list for LLM."""
    messages = [{"role": "system", "content": system_prompt}]

    # Load conversation history
    if not clear_history and conversation_id:
        conversation_store = get_conversation_store()
        history = conversation_store.get_messages(conversation_id)
        for msg in history:
            if msg.get("role") == "user":
                messages.append({"role": "user", "content": msg["content"]})
        if history:
            logger.info(f"Loaded {len([m for m in history if m.get('role') == 'user'])} user messages from history")

    # Add current message with context
    if full_context:
        messages.append({
            "role": "user",
            "content": f"Context:\n\n{full_context}\n\n---\n\nQuestion: {user_message}",
        })
    else:
        messages.append({"role": "user", "content": user_message})

    return messages


# =============================================================================
# Helper Functions - Tools
# =============================================================================


async def _load_tools(
    agent: AgentConfig,
    expose_to_llm: Dict[str, bool],
) -> List[Dict[str, Any]]:
    """Load tools based on expose_to_llm settings."""
    tools = []

    if expose_to_llm.get("local_mcp", False):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{agent.mcp_url}/tools")
                if response.status_code == 200:
                    mcp_tools = response.json().get("tools", [])
                    tools.extend([convert_mcp_tool_to_openai(tool) for tool in mcp_tools])
                    logger.info(f"Exposed {len(mcp_tools)} local MCP tools to LLM")
        except Exception as e:
            logger.error(f"Failed to load local MCP tools: {e}")

    if expose_to_llm.get("azure_devops_mcp", False):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{agent.azure_devops_mcp_url}/tools")
                if response.status_code == 200:
                    az_tools = response.json().get("tools", [])
                    tools.extend([convert_mcp_tool_to_openai(tool) for tool in az_tools])
                    logger.info(f"Exposed {len(az_tools)} Azure DevOps MCP tools to LLM")
        except Exception as e:
            logger.error(f"Failed to load Azure DevOps MCP tools: {e}")

    if expose_to_llm.get("crawler", False):
        from gateway.llm.prompts import CRAWL_AND_REFRESH_TOOL
        tools.append(CRAWL_AND_REFRESH_TOOL)
        logger.info("Exposed crawler tool to LLM")

    return tools


# =============================================================================
# Helper Functions - LLM Execution
# =============================================================================


async def _execute_llm_with_tools(
    request: UnifiedWorkflowRequest,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    request_id: str,
    context_gathered: Dict[str, int],
) -> Tuple[str, Optional[int]]:
    """Execute LLM with tool calling loop."""
    llm_client = LLMClient()
    tool_handler = get_tool_handler()
    max_tool_rounds = int(os.getenv("MAX_TOOL_ROUNDS", "5"))
    tool_round = 0

    # Log tools
    if tools:
        logger.info(f"Passing {len(tools)} tools to LLM: {[t.get('function', {}).get('name', '?') for t in tools]}")

    # Initial LLM call
    response = await llm_client.chat_completion(
        model=request.model,
        messages=messages,
        tools=tools if tools else None,
        tool_choice="auto" if tools else "none",
        max_tokens=request.max_tokens,
    )

    logger.info(f"Initial LLM response - has tool_calls: {bool(response.get('tool_calls'))}")

    # Tool execution loop
    while response.get("tool_calls") and tool_round < max_tool_rounds:
        tool_round += 1
        logger.info(f"Tool execution round {tool_round}/{max_tool_rounds}")

        # Add assistant message with tool calls
        messages.append({
            "role": "assistant",
            "content": response.get("content") or "",
            "tool_calls": response["tool_calls"],
        })

        # Execute each tool call
        for tool_call in response["tool_calls"]:
            tool_name = tool_call.get("function", {}).get("name", "unknown")
            logger.info(f"Executing tool: {tool_name}")

            tool_result = await tool_handler.handle_tool_call(
                tool_call,
                request_id,
                request.seed_urls or [],
                request.crawl_depth,
                not request.enable_embedding,
                request.browse_web,
            )
            messages.append(tool_result)

            # Update context_gathered
            try:
                result_data = json.loads(tool_result["content"])
                if "hits" in result_data:
                    context_gathered["tool_executed_urls"] = len(result_data["hits"])
            except Exception:
                pass

        # Next LLM call
        response = await llm_client.chat_completion(
            messages=messages,
            model=request.model,
            tools=tools,
            tool_choice="auto",
            max_tokens=request.max_tokens,
        )

        if not response.get("tool_calls"):
            logger.info(f"LLM finished after {tool_round} tool rounds")
            break

    if tool_round >= max_tool_rounds and response.get("tool_calls"):
        logger.warning(f"Reached max tool rounds ({max_tool_rounds}), stopping")

    response_text = response.get("content") or ""
    tokens_used = response.get("usage", {}).get("total_tokens")

    if not response_text and tool_round > 0:
        response_text = "Tool execution completed but no final response generated."

    return response_text, tokens_used


# =============================================================================
# Agent Singleton
# =============================================================================


def get_agent_config() -> AgentConfig:
    """Get or create agent config instance."""
    global _agent_config
    if _agent_config is None:
        _agent_config = AgentConfig(
            mcp_url=os.getenv("MCP_SERVER_URL", "http://mcp:8003"),
            crawler_url=os.getenv("CRAWLER_URL", "http://crawler:8001"),
            indexer_url=os.getenv("INDEXER_URL", "http://indexer:8002"),
            azure_devops_mcp_url=os.getenv(
                "AZURE_DEVOPS_MCP_URL", "http://azure-devops-mcp-server:8004"
            ),
        )
    return _agent_config


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/chat", response_model=UnifiedWorkflowResponse)
async def execute(request: UnifiedWorkflowRequest):
    """
    Execute agent workflow - single endpoint for all use cases.

    Workflow:
    1. Expand and gather context from target_paths (Azure DevOps)
    2. Expand and gather context from reference_files (Local/Azure DevOps)
    3. Crawl seed_urls if provided
    4. Build messages and tools for LLM
    5. Execute LLM with tool calling loop
    6. Return response with conversation tracking
    """
    request_id = str(uuid.uuid4())

    log_request(
        logger, request_id, "POST", "/agent/chat",
        message_length=len(request.user_message),
        stream=False,
        conversation_id=request.conversation_id,
    )

    # Determine conversation ID
    conversation_store = get_conversation_store()
    if request.clear_history:
        conversation_id = str(uuid.uuid4())
        logger.info(f"Clear history - new conversation: {conversation_id}")
    else:
        conversation_id = request.conversation_id or str(uuid.uuid4())
        if not request.conversation_id:
            logger.info(f"New conversation: {conversation_id}")

    try:
        agent = get_agent_config()
        context_gathered = {
            "target_files": 0,
            "reference_files": 0,
            "crawled_urls": 0,
            "web_search_results": 0,
        }

        # Step 1: Expand paths
        expanded_target_paths = await _expand_paths(agent, request.target_paths or [])
        expanded_reference_files = await _expand_paths(agent, request.reference_files or [])

        if request.target_paths:
            logger.info(f"Expanded {len(request.target_paths)} target paths to {len(expanded_target_paths)} files")
        if request.reference_files:
            logger.info(f"Expanded {len(request.reference_files)} reference files to {len(expanded_reference_files)} files")

        # Step 2: Gather context from all sources
        target_content = await _gather_target_files(agent, expanded_target_paths, context_gathered)
        reference_content = await _gather_reference_files(agent, expanded_reference_files, context_gathered)
        crawled_content = await _crawl_urls(agent, request, request_id, context_gathered)

        # Step 3: Build context and messages
        full_context = _build_context_string(target_content, reference_content, crawled_content)
        logger.info(f"Full context: {len(full_context)} chars")

        system_prompt = _build_system_prompt(request.expose_to_llm)
        messages = _build_messages(
            system_prompt, full_context, request.user_message,
            request.conversation_id, request.clear_history
        )

        # Step 4: Load tools
        tools = await _load_tools(agent, request.expose_to_llm)

        # Step 5: Execute LLM with tools
        response_text, tokens_used = await _execute_llm_with_tools(
            request, messages, tools, request_id, context_gathered
        )

        # Step 6: Save conversation history
        conversation_store.add_message(conversation_id, "user", request.user_message)
        conversation_store.add_message(conversation_id, "assistant", response_text)

        result = UnifiedWorkflowResponse(
            response=response_text,
            conversation_id=conversation_id,
            model=request.model or "default",
            tokens_used=tokens_used,
            context_gathered=context_gathered,
        )

        log_response(logger, request_id, 200, 0.0)
        return result

    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        log_response(logger, request_id, 500, 0.0, error=str(e))

        error_msg = str(e)
        status_code = 500
        if "rate limit" in error_msg.lower() or "429" in error_msg or "RateLimitReached" in error_msg:
            status_code = 429
        elif "token" in error_msg.lower() and "exceed" in error_msg.lower():
            status_code = 429

        raise HTTPException(status_code=status_code, detail=error_msg)


@router.get("/health")
async def health_check():
    """Agent health check."""
    try:
        agent = get_agent_config()
        return {
            "status": "healthy",
            "agent": "AgentConfig",
            "mcp_url": agent.mcp_url,
            "crawler_url": agent.crawler_url,
            "indexer_url": agent.indexer_url,
        }
    except Exception as e:
        logger.error(f"Agent health check failed: {e}")
        return JSONResponse(
            status_code=503, content={"status": "unhealthy", "error": str(e)}
        )

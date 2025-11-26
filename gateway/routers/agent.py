"""
Agent API router - Template-based workflow execution.

Provides:
1. GET /agent/templates - List all workflow templates
2. GET /agent/templates/{workflow} - Get specific template
3. POST /agent/execute - Execute workflow with filled template
"""

import fnmatch
import json
import logging
import os
import uuid
from typing import List, Union

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from gateway.agents import CodeIntelligenceAgent
from gateway.agents.templates import (
    GenerateWorkflowRequest,
    InspectWorkflowRequest,
    UnderstandWorkflowRequest,
    get_all_templates,
    get_template,
)
from gateway.agents.unified_workflow import (
    UnifiedWorkflowRequest,
    UnifiedWorkflowResponse,
)
from gateway.llm.client import LLMClient
from gateway.routers.tools import get_tool_handler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

# Initialize agent (singleton)
_agent = None


async def _expand_paths(
    agent: CodeIntelligenceAgent, path_list: List[str]
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
        # The agent will handle wildcards via Azure DevOps search API
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
            pattern = parts[-1]  # e.g., "*.cpp"
            folder = "/".join(parts[:-1]) if len(parts) > 1 else "."

            # List folder
            files = await _list_folder_files(agent, folder, False)

            # Filter by pattern
            matching = [f for f in files if fnmatch.fnmatch(f.split("/")[-1], pattern)]
            expanded_files.extend(matching)
        else:
            # Direct file path
            expanded_files.append(path_normalized)

    return expanded_files


async def _list_folder_files(
    agent: CodeIntelligenceAgent, folder_path: str, recursive: bool
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
                # Extract just the paths
                return [f["path"] for f in files_data if f.get("type") == "file"]
            return []
    except Exception as e:
        logger.error(f"Failed to list folder {folder_path}: {e}")
        return []


def get_agent() -> CodeIntelligenceAgent:
    """Get or create agent instance."""
    global _agent
    if _agent is None:
        _agent = CodeIntelligenceAgent(
            mcp_url=os.getenv("MCP_SERVER_URL", "http://mcp:8003"),
            crawler_url=os.getenv("CRAWLER_URL", "http://crawler:8001"),
            indexer_url=os.getenv("INDEXER_URL", "http://indexer:8002"),
            llm_client=LLMClient(),
            azure_devops_mcp_url=os.getenv(
                "AZURE_DEVOPS_MCP_URL", "http://azure-devops-mcp-server:8004"
            ),
        )
    return _agent


@router.get("/templates")
async def list_templates():
    """
    List all available workflow templates.

    Returns template definitions with parameter schemas and examples.
    Clients use these to build UIs or generate filled templates.

    Example response:
    {
        "templates": {
            "understand": {...},
            "inspect": {...},
            "generate": {...}
        },
        "count": 3
    }
    """
    return get_all_templates()


@router.get("/templates/{workflow}")
async def get_workflow_template(workflow: str):
    """
    Get template for specific workflow.

    Args:
        workflow: One of "understand", "inspect", "generate"

    Returns template definition with parameters and example.

    Example:
    GET /agent/templates/understand

    Response:
    {
        "name": "Understand & Document",
        "description": "...",
        "workflow": "understand",
        "parameters": {...},
        "example": {...}
    }
    """
    template = get_template(workflow)
    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"Template not found for workflow: {workflow}. "
            f"Available: understand, inspect, generate",
        )
    return template


@router.post("/execute")
async def execute_workflow(
    request: Union[
        UnderstandWorkflowRequest, InspectWorkflowRequest, GenerateWorkflowRequest
    ],
):
    """
    Execute workflow with filled template.

    Accepts one of three template types:
    - UnderstandWorkflowRequest
    - InspectWorkflowRequest
    - GenerateWorkflowRequest

    Example request body:
    {
        "workflow": "understand",
        "target_files": ["/src/compute/service.cpp"],
        "request": "Explain initialization",
        "educational_files": ["/docs/GUIDE.md"],
        "web_crawl_urls": ["https://docs.microsoft.com/..."]
    }

    Returns:
    {
        "workflow": "understand",
        "result": "...",  # LLM response
        "target_files": [...],
        "sources": [...],  # Web sources used
        "context_used": {
            "target_files_count": 2,
            "reference_files_count": 1,
            "web_sources_count": 3
        }
    }
    """

    logger.info(f"Executing {request.workflow} workflow")
    logger.info(f"Target paths: {len(request.target_paths)}")
    logger.info(f"Educational files: {len(request.educational_files or [])}")
    logger.info(f"Web crawl URLs: {len(request.web_crawl_urls or [])}")

    try:
        agent = get_agent()

        # Expand target_paths to actual file list
        target_files = await _expand_paths(agent, request.target_paths)

        # Check file count limit
        max_files = int(os.getenv("MAX_FILES_PER_REQUEST", "50"))
        if len(target_files) > max_files:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Too many files: {len(target_files)} files expanded. "
                    f"Maximum: {max_files}. Use more specific wildcards."
                ),
            )

        # Expand educational_files if provided
        reference_files = []
        if request.educational_files:
            reference_files = await _expand_paths(agent, request.educational_files)

        seed_urls = request.web_crawl_urls or []

        logger.info(f"Expanded to {len(target_files)} target files")
        if reference_files:
            logger.info(f"Expanded to {len(reference_files)} reference files")

        if seed_urls:
            logger.info(f"Will crawl {len(seed_urls)} seed URLs")

        if request.allow_web_search:
            logger.info(f"Web search enabled: allow_web_search=True")
        else:
            logger.info(f"Web search disabled: allow_web_search=False")

        # Execute workflow
        result = await agent.execute_workflow(
            workflow=request.workflow,
            target_files=target_files,
            request=request.request,
            model=request.model,
            reference_files=reference_files,
            seed_urls=seed_urls,
            allow_web_search=request.allow_web_search,
        )

        # Check for errors
        if "error" in result:
            error_msg = result["error"]
            logger.error(f"Workflow execution failed: {error_msg}")

            # Detect rate limit errors and return 429
            status_code = 500
            if (
                "rate limit" in error_msg.lower()
                or "429" in error_msg
                or "RateLimitReached" in error_msg
            ):
                status_code = 429
            elif "token" in error_msg.lower() and "exceed" in error_msg.lower():
                status_code = 429

            raise HTTPException(status_code=status_code, detail=error_msg)

        logger.info(f"Workflow completed: {result.get('context_used', {})}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Unexpected error executing workflow: {error_msg}", exc_info=True)

        # Detect rate limit errors
        status_code = 500
        if (
            "rate limit" in error_msg.lower()
            or "429" in error_msg
            or "RateLimitReached" in error_msg
        ):
            status_code = 429
        elif "token" in error_msg.lower() and "exceed" in error_msg.lower():
            status_code = 429

        raise HTTPException(status_code=status_code, detail=error_msg)


@router.post("/execute-with-urls")
async def execute_workflow_with_seed_urls(
    request: Union[
        UnderstandWorkflowRequest, InspectWorkflowRequest, GenerateWorkflowRequest
    ],
):
    """
    Execute workflow with specific seed URLs for crawling.

    This endpoint passes seed URLs to the crawler for targeted scraping.

    Implementation note: This requires extending agent.execute_workflow()
    to accept seed_urls parameter.
    """

    # TODO: Extend CodeIntelligenceAgent to accept seed_urls
    # For now, call regular execute endpoint
    return await execute_workflow(request)


@router.post("/unified", response_model=UnifiedWorkflowResponse)
async def execute_unified_workflow(request: UnifiedWorkflowRequest):
    """
    Execute unified workflow - single endpoint for all use cases.

    Agent workflow:
    1. Gather context from target_paths (Azure DevOps MCP)
    2. Gather context from reference_files (Local MCP)
    3. Crawl seed_urls if provided
    4. Optionally crawl web based on browse_web and user_message
    5. Combine all context with user_message and send to LLM
    6. LLM can use exposed tools based on expose_to_llm settings
    """
    import uuid

    import httpx

    from gateway.utils.conversation_store import get_conversation_store
    from gateway.utils.logging import log_request, log_response

    request_id = str(uuid.uuid4())

    log_request(
        logger,
        request_id,
        "POST",
        "/agent/unified",
        message_length=len(request.user_message),
        stream=False,
        conversation_id=request.conversation_id,
    )

    # Determine conversation ID
    conversation_store = get_conversation_store()

    if request.clear_history:
        # Clear history and start new conversation
        conversation_id = str(uuid.uuid4())
        logger.info(
            f"Clear history requested - starting new conversation: {conversation_id}"
        )
    else:
        # Use existing or create new
        conversation_id = request.conversation_id or str(uuid.uuid4())
        if not request.conversation_id:
            logger.info(f"New conversation started: {conversation_id}")

    try:
        agent = get_agent()
        context_gathered = {
            "target_files": 0,
            "reference_files": 0,
            "crawled_urls": 0,
            "web_search_results": 0,
        }

        # Step 1: Gather context from Azure DevOps target paths
        target_content = []
        if request.target_paths:
            logger.info(
                f"Gathering {len(request.target_paths)} target paths from Azure DevOps"
            )
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    for path in request.target_paths:
                        # Check if it's an Azure DevOps path
                        if path.startswith("azdo:"):
                            # Remove "azdo:" prefix and get the file directly
                            file_path = path[5:]  # Remove "azdo:" prefix
                            # Ensure it starts with /
                            if not file_path.startswith("/"):
                                file_path = "/" + file_path

                            logger.info(
                                f"Fetching target file: {file_path} from {agent.azure_devops_mcp_url}"
                            )
                            response = await client.post(
                                f"{agent.azure_devops_mcp_url}/invoke",
                                json={
                                    "tool_name": "get_azure_devops_file",
                                    "arguments": {"file_path": file_path},
                                },
                            )
                            logger.info(f"Response status: {response.status_code}")
                            if response.status_code == 200:
                                file_data = response.json()
                                logger.info(f"Response JSON keys: {file_data.keys()}")
                                logger.info(f"Response JSON: {str(file_data)[:500]}")

                                # Handle response structure (similar to local MCP)
                                content = ""
                                if "content" in file_data:
                                    content = file_data["content"]
                                elif "result" in file_data:
                                    result = file_data["result"]
                                    if isinstance(result, dict):
                                        content = result.get("content", "")
                                    elif isinstance(result, list) and len(result) > 0:
                                        if (
                                            isinstance(result[0], dict)
                                            and "text" in result[0]
                                        ):
                                            content = result[0]["text"]
                                        else:
                                            content = str(result[0])
                                    else:
                                        content = str(result)

                                logger.info(
                                    f"Extracted target content length: {len(content)} chars"
                                )
                                target_content.append(f"File: {file_path}\n\n{content}")
                                context_gathered["target_files"] += 1
                            else:
                                logger.error(
                                    f"Failed to fetch {file_path}: HTTP {response.status_code}"
                                )
                                logger.error(f"Response: {response.text[:500]}")
                        else:
                            # Direct file path - use get_file
                            logger.info(
                                f"Fetching target file: {path} from {agent.azure_devops_mcp_url}"
                            )
                            response = await client.post(
                                f"{agent.azure_devops_mcp_url}/invoke",
                                json={
                                    "tool_name": "get_azure_devops_file",
                                    "arguments": {"file_path": path},
                                },
                            )
                            logger.info(f"Response status: {response.status_code}")
                            if response.status_code == 200:
                                file_data = response.json()
                                logger.info(f"Response JSON keys: {file_data.keys()}")
                                logger.info(f"Response JSON: {str(file_data)[:500]}")

                                # Handle response structure
                                content = ""
                                if "content" in file_data:
                                    content = file_data["content"]
                                elif "result" in file_data:
                                    result = file_data["result"]
                                    if isinstance(result, dict):
                                        content = result.get("content", "")
                                    elif isinstance(result, list) and len(result) > 0:
                                        if (
                                            isinstance(result[0], dict)
                                            and "text" in result[0]
                                        ):
                                            content = result[0]["text"]
                                        else:
                                            content = str(result[0])
                                    else:
                                        content = str(result)

                                logger.info(
                                    f"Extracted target content length: {len(content)} chars"
                                )
                                target_content.append(f"File: {path}\n\n{content}")
                                context_gathered["target_files"] += 1
                            else:
                                logger.error(
                                    f"Failed to fetch {path}: HTTP {response.status_code}"
                                )
                                logger.error(f"Response: {response.text[:500]}")
            except Exception as e:
                logger.error(f"Failed to gather target paths: {e}", exc_info=True)

        # Step 2: Gather context from local reference files
        reference_content = []
        if request.reference_files:
            logger.info(
                f"Gathering {len(request.reference_files)} reference files from local MCP"
            )
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    for file_path in request.reference_files:
                        logger.info(
                            f"Reading reference file: {file_path} from {agent.mcp_url}"
                        )
                        response = await client.post(
                            f"{agent.mcp_url}/invoke",
                            json={
                                "tool_name": "read_local_file",
                                "arguments": {"file_path": file_path},
                            },
                        )
                        logger.info(f"Response status: {response.status_code}")
                        if response.status_code == 200:
                            file_data = response.json()
                            logger.info(f"Response JSON keys: {file_data.keys()}")
                            logger.info(f"Response JSON: {str(file_data)[:500]}")

                            # Handle both possible response formats
                            content = ""
                            if "content" in file_data:
                                content = file_data["content"]
                            elif "result" in file_data:
                                # MCP /invoke might return result with content inside
                                result = file_data["result"]
                                if isinstance(result, dict):
                                    content = result.get("content", "")
                                elif isinstance(result, list) and len(result) > 0:
                                    # Check if it's a list of text content blocks
                                    if (
                                        isinstance(result[0], dict)
                                        and "text" in result[0]
                                    ):
                                        content = result[0]["text"]
                                    else:
                                        content = str(result[0])
                                else:
                                    content = str(result)

                            logger.info(
                                f"Extracted content length: {len(content)} chars"
                            )
                            reference_content.append(
                                f"Reference File: {file_path}\n\n{content}"
                            )
                            context_gathered["reference_files"] += 1
                        else:
                            logger.error(
                                f"Failed to read {file_path}: HTTP {response.status_code}"
                            )
                            logger.error(f"Response: {response.text[:500]}")
            except Exception as e:
                logger.error(f"Failed to gather reference files: {e}", exc_info=True)

        # Step 3: Crawl seed URLs (only if provided)
        # browse_web controls whether crawler can follow links beyond seed URLs
        crawled_content = []
        if request.seed_urls:
            logger.info(
                f"Crawling - seed_urls: {len(request.seed_urls)}, "
                f"browse_web: {request.browse_web}"
            )
            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    response = await client.post(
                        f"{agent.crawler_url}/crawl",
                        json={
                            "query": request.user_message[
                                :200
                            ],  # Use user message as search query
                            "seed_urls": request.seed_urls or [],
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
                            index_response = await client.post(
                                f"{agent.indexer_url}/index",
                                json={"docs": docs},
                                headers={"X-Request-ID": request_id},
                            )
                            if index_response.status_code == 200:
                                logger.info("Documents indexed successfully")

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

        # Step 4: Build context summary for LLM
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
            logger.info(f"Added {len(crawled_content)} crawled documents to context")

        # Combine all context
        full_context = "\n\n===\n\n".join(context_parts) if context_parts else ""
        logger.info(
            f"Full context length: {len(full_context)} chars, has context: {bool(full_context)}"
        )

        # Step 5: Build messages for LLM
        system_prompt = (
            "You are a helpful assistant with access to tools for fetching current information.\n\n"
            "AVAILABLE TOOLS:\n"
        )

        # Add tool descriptions based on what's exposed
        tool_descriptions = []
        if request.expose_to_llm.get("azure_devops_mcp", False):
            tool_descriptions.append(
                "- **Azure DevOps MCP Tools**: Search and read files from Azure DevOps repositories\n"
                "  - `search_azure_devops_code`: Search for code patterns in files (PREFERRED for finding packages, dependencies)\n"
                "    Example: search for 'Microsoft-NanoServer-NetFx' to find files containing this package name\n"
                "  - `get_azure_devops_file`: Read specific file contents when you know the exact path\n"
                "  - `search_azure_devops_files`: Find files by name/path patterns\n"
                "    **CRITICAL RESTRICTION**: When using recursive=true, you MUST provide either:\n"
                "      * A specific filename in file_pattern (e.g., 'package.json')\n"
                "      * OR a search keyword to filter results\n"
                "    **NEVER** use recursive=true with only path_pattern and extension - this will timeout!\n"
                "    Example WRONG: {path_pattern: '/dir/', extension: 'json', recursive: true}\n"
                "    Example RIGHT: {path_pattern: '/dir/', file_pattern: 'Microsoft*.json', recursive: true}\n\n"
                "  **For package analysis**: Always use search_azure_devops_code to search for package names,\n"
                "  not search_azure_devops_files which times out on large directories."
            )

        if request.expose_to_llm.get("local_mcp", False):
            tool_descriptions.append(
                "- **Local MCP Tools**: Access local workspace files and directories\n"
                "  Use these when user asks about local files or workspace structure."
            )

        if request.expose_to_llm.get("crawler", False):
            tool_descriptions.append(
                "- **Crawler Tool** (`crawl_and_refresh`): Fetch and index web content\n"
                "  Use this when user asks for current web information or recent news."
            )

        if tool_descriptions:
            system_prompt += "\n".join(tool_descriptions) + "\n\n"

        system_prompt += (
            "CRITICAL RULES FOR TOOL USAGE:\n"
            "1. You MUST use the function calling mechanism to invoke tools - DO NOT output JSON or describe tool calls as text.\n"
            "2. When the user asks about packages, dependencies, or code files, immediately call search_azure_devops_code or search_azure_devops_files.\n"
            "3. NEVER output tool arguments as JSON text - use proper function calling.\n"
            "4. DO NOT ask for clarification about which tool to use - just call the most appropriate tool.\n"
            "5. If context is already provided in the messages, analyze it directly.\n"
            "6. When user mentions 'MCP' they mean Model Context Protocol tools for accessing files/code.\n\n"
            "EXAMPLE OF CORRECT BEHAVIOR:\n"
            "User: 'Find child packages of X'\n"
            "You: [CALL search_azure_devops_code tool with appropriate query] - NOT output JSON\n\n"
            "Remember: USE FUNCTION CALLING, NOT TEXT OUTPUT OF JSON."
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

        # Load conversation history (user messages only to save tokens)
        if not request.clear_history and request.conversation_id:
            history = conversation_store.get_messages(request.conversation_id)
            # Only include previous user messages (skip system, assistant, tool messages)
            for msg in history:
                if msg.get("role") == "user":
                    messages.append({"role": "user", "content": msg["content"]})
            if history:
                logger.info(
                    f"Loaded {len([m for m in history if m.get('role') == 'user'])} user messages from history"
                )

        # Add current context and user message
        if full_context:
            messages.append(
                {
                    "role": "user",
                    "content": f"Context:\n\n{full_context}\n\n---\n\nQuestion: {request.user_message}",
                }
            )
        else:
            messages.append({"role": "user", "content": request.user_message})

        # Step 6: Build tools list based on expose_to_llm settings
        tools = []

        if request.expose_to_llm.get("local_mcp", False):
            # Add local MCP tools
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{agent.mcp_url}/tools")
                    if response.status_code == 200:
                        mcp_tools = response.json().get("tools", [])
                        # Convert MCP tools to OpenAI function format
                        for tool in mcp_tools:
                            if "type" not in tool:
                                tool["type"] = "function"
                            if "function" not in tool:
                                tool["function"] = {
                                    "name": tool.pop("name"),
                                    "description": tool.pop("description"),
                                    "parameters": tool.pop("inputSchema"),
                                }
                        tools.extend(mcp_tools)
                        logger.info(f"Exposed {len(mcp_tools)} local MCP tools to LLM")
            except Exception as e:
                logger.error(f"Failed to load local MCP tools: {e}")

        if request.expose_to_llm.get("azure_devops_mcp", False):
            # Add Azure DevOps MCP tools
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{agent.azure_devops_mcp_url}/tools")
                    if response.status_code == 200:
                        az_tools = response.json().get("tools", [])
                        # Convert MCP tools to OpenAI function format
                        for tool in az_tools:
                            if "type" not in tool:
                                tool["type"] = "function"
                            if "function" not in tool:
                                tool["function"] = {
                                    "name": tool.pop("name"),
                                    "description": tool.pop("description"),
                                    "parameters": tool.pop("inputSchema"),
                                }
                        tools.extend(az_tools)
                        logger.info(
                            f"Exposed {len(az_tools)} Azure DevOps MCP tools to LLM"
                        )
            except Exception as e:
                logger.error(f"Failed to load Azure DevOps MCP tools: {e}")

        if request.expose_to_llm.get("crawler", False):
            # Add crawler tool
            from gateway.routers.chat import CRAWL_AND_REFRESH_TOOL

            tools.append(CRAWL_AND_REFRESH_TOOL)
            logger.info("Exposed crawler tool to LLM")

        # Step 7: Call LLM with tool execution loop
        llm_client = LLMClient()
        tool_handler = get_tool_handler()

        # Tool execution loop
        max_tool_rounds = int(os.getenv("MAX_TOOL_ROUNDS", "5"))
        tool_round = 0
        all_tool_calls = []

        # Log tools being passed to LLM
        if tools:
            logger.info(f"Passing {len(tools)} tools to LLM:")
            for tool in tools:
                tool_name = tool.get("function", {}).get("name", "unknown")
                logger.info(f"  - {tool_name}")

        response = await llm_client.chat_completion(
            model=request.model,
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else "none",
            max_tokens=request.max_tokens,
        )

        logger.info(
            f"Initial LLM response - has tool_calls: {bool(response.get('tool_calls'))}, "
            f"content: {response.get('content', '')[:100] if response.get('content') else 'None'}"
        )

        # Handle tool calls in a loop
        while response.get("tool_calls") and tool_round < max_tool_rounds:
            tool_round += 1
            logger.info(f"Tool execution round {tool_round}/{max_tool_rounds}")

            # Add assistant message with tool calls to conversation
            content_val = response.get("content") or ""
            assistant_message = {
                "role": "assistant",
                "content": content_val,
                "tool_calls": response["tool_calls"],
            }
            messages.append(assistant_message)

            # Execute each tool call
            for tool_call in response["tool_calls"]:
                all_tool_calls.append(tool_call)
                logger.info(
                    f"Executing tool: {tool_call.get('function', {}).get('name', 'unknown')}"
                )

                # Handle tool execution
                tool_result = await tool_handler.handle_tool_call(
                    tool_call,
                    request_id,
                    request.seed_urls or [],
                    request.crawl_depth,
                    not request.enable_embedding,  # skip_embedding is inverse
                    request.browse_web,
                )
                messages.append(tool_result)

                # Update context_gathered with tool results
                try:
                    result_data = json.loads(tool_result["content"])
                    if "hits" in result_data:
                        context_gathered["tool_executed_urls"] = len(
                            result_data["hits"]
                        )
                except Exception:
                    pass

            # Next LLM call with tool results
            logger.info(f"Making LLM call with tool results (round {tool_round})")
            response = await llm_client.chat_completion(
                messages=messages,
                model=request.model,
                tools=tools,  # Keep tools available
                tool_choice="auto",
                max_tokens=request.max_tokens,
            )

            # Check if done
            if not response.get("tool_calls"):
                logger.info(f"LLM finished after {tool_round} tool rounds")
                break

        if tool_round >= max_tool_rounds and response.get("tool_calls"):
            logger.warning(f"Reached max tool rounds ({max_tool_rounds}), stopping")

        # Extract final response
        response_text = response.get("content") or ""
        tokens_used = response.get("usage", {}).get("total_tokens")

        if not response_text and tool_round > 0:
            response_text = "Tool execution completed but no final response generated."

        # Save conversation history
        # Save current user message (without context to save memory)
        conversation_store.add_message(conversation_id, "user", request.user_message)

        # Save assistant response
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
        logger.error(f"Unified workflow failed: {e}")
        log_response(logger, request_id, 500, 0.0, error=str(e))

        # Detect rate limit errors
        error_msg = str(e)
        status_code = 500
        if (
            "rate limit" in error_msg.lower()
            or "429" in error_msg
            or "RateLimitReached" in error_msg
        ):
            status_code = 429
        elif "token" in error_msg.lower() and "exceed" in error_msg.lower():
            status_code = 429

        raise HTTPException(status_code=status_code, detail=error_msg)


# Health check
@router.get("/health")
async def health_check():
    """Agent health check."""
    try:
        agent = get_agent()
        return {
            "status": "healthy",
            "agent": "CodeIntelligenceAgent",
            "mcp_url": agent.mcp_url,
            "crawler_url": agent.crawler_url,
            "indexer_url": agent.indexer_url,
        }
    except Exception as e:
        logger.error(f"Agent health check failed: {e}")
        return JSONResponse(
            status_code=503, content={"status": "unhealthy", "error": str(e)}
        )

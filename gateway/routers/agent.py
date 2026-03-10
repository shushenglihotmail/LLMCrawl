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
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, cast

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gateway.agents import AgentConfig, convert_mcp_tool_to_openai
from gateway.agents.unified_workflow import (
    UnifiedWorkflowRequest,
    UnifiedWorkflowResponse,
    WorkflowType,
)
from gateway.llm.client import LLMClient
from gateway.routers.tools import get_tool_handler
from gateway.utils.auth import get_bearer_token
from gateway.utils.azdo_uri import is_azdo_uri, parse_azdo_uri
from gateway.utils.conversation_store import get_conversation_store
from gateway.utils.file_store import get_file_store
from gateway.utils.logging import log_request, log_response
from gateway.utils.memory_integration import (
    append_to_daily_log_async,
    check_and_get_flush_prompt,
    is_memory_enabled,
    parse_and_save_distillation_async,
    read_durable_memory_async,
)
from gateway.utils.metrics import (
    AgentActivityTimer,
    classify_error,
    record_agent_request,
)
from gateway.utils.token_context import get_token
from gateway.utils.tool_constants import (
    DEFAULT_TOOL_LIMITS,
    TOOL_MEMORY_SEARCH,
    TOOL_QUERY_COMPOSITION_DB,
    TOOL_SAVE_FILE_FOR_DOWNLOAD,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

# Initialize agent config (singleton)
_agent_config: Optional[AgentConfig] = None

# =============================================================================
# Active Request Tracking (for cancellation)
# =============================================================================

# Track active requests by conversation_id
# Key: conversation_id, Value: {"cancelled": bool, "request_id": str}
_active_requests: Dict[str, Dict[str, Any]] = {}


def _mark_request_active(conversation_id: str, request_id: str) -> None:
    """Mark a conversation as having an active request."""
    _active_requests[conversation_id] = {
        "cancelled": False,
        "request_id": request_id,
    }


def _mark_request_cancelled(conversation_id: str) -> bool:
    """Mark a conversation's request as cancelled. Returns True if there was an active request."""
    if conversation_id in _active_requests:
        _active_requests[conversation_id]["cancelled"] = True
        logger.info(f"Marked request for conversation {conversation_id} as cancelled")
        return True
    return False


def _is_request_cancelled(conversation_id: str) -> bool:
    """Check if the current request has been cancelled."""
    return _active_requests.get(conversation_id, {}).get("cancelled", False)


def _clear_active_request(conversation_id: str) -> None:
    """Clear active request tracking for a conversation."""
    if conversation_id in _active_requests:
        del _active_requests[conversation_id]
        logger.debug(f"Cleared active request for conversation {conversation_id}")


def _is_conversation_busy(conversation_id: str) -> bool:
    """Check if a conversation has an active (non-cancelled) request."""
    req = _active_requests.get(conversation_id)
    return req is not None and not req.get("cancelled", False)


# =============================================================================
# Helper Functions - Path Expansion
# =============================================================================


async def _expand_paths(agent: AgentConfig, path_list: List[str]) -> List[str]:
    """
    Expand path list to actual file paths using conventions:

    Azure DevOps (azdo:) paths - NEW FORMAT:
    - 'azdo:/path:searchText' = Use Azure DevOps Code Search API
      - path is the scope (folder to search in)
      - searchText is passed directly to Azure DevOps API
      - Examples: 'azdo:/vm/compute:ext:xml', 'azdo:/:file:*manifest*.xml'
    - 'azdo:/path/to/file.cpp' = Direct file path (no colon after path = exact file)

    Local paths:
    - 'file.cpp' = direct file
    - '*.cpp' or 'x*.json' = wildcard pattern
    - 'folder/' or 'folder\\' = folder (non-recursive)
    - 'folder/**' = folder (recursive)
    """
    expanded_files = []

    for path in path_list:
        # Check if this is an Azure DevOps path
        if is_azdo_uri(path):
            # Parse the azdo URI to get components
            parsed = parse_azdo_uri(path)
            if not parsed:
                # Can't parse, pass through as-is
                expanded_files.append(path)
                continue

            # Check if this is a search query (has search_text)
            if parsed.is_search_query():
                # Use Azure DevOps Code Search API
                files = await _search_azdo_files(agent, parsed)
                expanded_files.extend(files)
            else:
                # Direct file path - keep original URI format
                expanded_files.append(path)
        else:
            # Local file path
            # Normalize backslashes to forward slashes (Windows paths)
            path_normalized = path.replace("\\", "/")

            # Check for recursive folder pattern
            if path_normalized.endswith("/**"):
                folder = path_normalized[:-3]
                files = await _list_local_folder_files(agent, folder, recursive=True)
                expanded_files.extend(files)
            # Check for folder (ends with slash)
            elif path_normalized.endswith("/"):
                folder = path_normalized[:-1]
                files = await _list_local_folder_files(agent, folder, recursive=False)
                expanded_files.extend(files)
            # Check for wildcard pattern
            elif "*" in path_normalized:
                parts = path_normalized.split("/")
                pattern = parts[-1]
                folder = "/".join(parts[:-1]) if len(parts) > 1 else "."
                files = await _list_local_folder_files(agent, folder, recursive=False)
                matching = [
                    f for f in files if fnmatch.fnmatch(f.split("/")[-1], pattern)
                ]
                expanded_files.extend(matching)
            else:
                # Direct file path
                expanded_files.append(path_normalized)

    return expanded_files


async def _list_local_folder_files(
    agent: AgentConfig, folder_path: str, recursive: bool
) -> List[str]:
    """List files in a local folder using direct filesystem access."""
    try:
        from pathlib import Path

        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            logger.warning(f"Folder does not exist: {folder_path}")
            return []

        files = []
        if recursive:
            for f in folder.rglob("*"):
                if f.is_file():
                    files.append(str(f).replace("\\", "/"))
        else:
            for f in folder.iterdir():
                if f.is_file():
                    files.append(str(f).replace("\\", "/"))
        return files
    except Exception as e:
        logger.error(f"Failed to list local folder {folder_path}: {e}")
        return []


async def _search_azdo_files(agent: AgentConfig, parsed: Any) -> List[str]:
    """
    Search for files in Azure DevOps using Code Search API.

    Uses the new azdo:/path:searchText format where:
    - path is the scope (folder to search in)
    - search_text is passed directly to Azure DevOps Code Search API
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            arguments = {
                "search_text": parsed.search_text,
                "path": parsed.path,
            }
            if parsed.project:
                arguments["project"] = parsed.project
            if parsed.repository:
                arguments["repository"] = parsed.repository
            if parsed.branch:
                arguments["branch"] = parsed.branch

            logger.info(
                f"Azure DevOps Code Search: path={parsed.path}, "
                f"search_text={parsed.search_text}"
            )
            response = await client.post(
                f"{agent.azure_devops_mcp_url}/invoke",
                json={
                    "tool_name": "search_azure_devops_code",
                    "arguments": arguments,
                },
            )
            response.raise_for_status()
            result = response.json()
            logger.debug(f"Azure DevOps MCP response: {result}")

            if result.get("success"):
                result_data = result.get("result", {})
                files_data = result_data.get("results", [])

                # Extract file paths and build azdo URIs
                file_paths = []
                for f in files_data:
                    if isinstance(f, dict):
                        path = f.get("file_path")
                        if path:
                            file_paths.append(path)

                logger.info(
                    f"Code Search found {len(file_paths)} files for: "
                    f"{parsed.search_text}"
                )
                # Reconstruct azdo URIs for the files (without search_text for direct access)
                return [_build_azdo_uri(parsed, fp) for fp in file_paths]
            else:
                logger.warning(f"Azure DevOps MCP returned success=False: {result}")
            return []
    except Exception as e:
        logger.error(f"Failed to search Azure DevOps: {e}")
        return []


def _build_azdo_uri(parsed: Any, file_path: str) -> str:
    """
    Build an azdo: URI from parsed components and a file path.

    Note: This builds a direct file access URI (no search_text),
    even if the original parsed URI had search_text.
    """
    # Ensure file_path starts with /
    if not file_path.startswith("/"):
        file_path = "/" + file_path

    # If no project/repo specified, use simple format: azdo:/path
    if not parsed.project and not parsed.repository:
        uri = f"azdo:{file_path}"
        if parsed.branch:
            uri += f"?branch={parsed.branch}"
        return uri

    # Full format: azdo://project/repo/path
    uri = f"azdo://{parsed.project}/{parsed.repository}{file_path}"
    if parsed.branch:
        uri += f"?branch={parsed.branch}"
    return uri


# =============================================================================
# Helper Functions - Content Extraction
# =============================================================================


def _extract_content_from_response(file_data: Dict[str, Any]) -> str:
    """Extract content from MCP response, handling various formats."""
    if "content" in file_data:
        return str(file_data["content"])
    elif "result" in file_data:
        result = file_data["result"]
        if isinstance(result, dict):
            return str(result.get("content", ""))
        elif isinstance(result, list) and len(result) > 0:
            if isinstance(result[0], dict) and "text" in result[0]:
                return str(result[0]["text"])
            return str(result[0])
        return str(result)
    return ""


# =============================================================================
# Helper Functions - Context Gathering
# =============================================================================


async def _gather_files(
    agent: AgentConfig,
    paths: List[str],
    context_gathered: Dict[str, int],
    context_key: str,
    label: str,
) -> List[str]:
    """
    Gather content from files (local or Azure DevOps).

    Local files are read directly from the filesystem since Gateway runs on host.
    Azure DevOps files are fetched via the Azure DevOps MCP server.

    Args:
        agent: Agent configuration
        paths: List of file paths (can be local or azdo: URIs)
        context_gathered: Dict to track gathered context counts
        context_key: Key in context_gathered to increment (e.g., "target_files", "reference_files")
        label: Label for log output (e.g., "File", "Reference File")

    Returns:
        List of formatted file content strings
    """
    from pathlib import Path as FilePath

    if not paths:
        return []

    file_content = []
    logger.info(f"Gathering {len(paths)} {context_key.replace('_', ' ')}")

    for file_path in paths:
        try:
            if is_azdo_uri(file_path):
                # Azure DevOps file - fetch via Azure DevOps MCP server
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

                logger.info(f"Fetching Azure DevOps file: {file_path}")
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{agent.azure_devops_mcp_url}/invoke",
                        json={
                            "tool_name": "get_azure_devops_file",
                            "arguments": arguments,
                        },
                    )

                    if response.status_code == 200:
                        file_data = response.json()
                        content = _extract_content_from_response(file_data)
                        if content:
                            file_content.append(f"{label}: {file_path}\n\n{content}")
                            context_gathered[context_key] += 1
                            logger.info(
                                f"Extracted {len(content)} chars from {file_path}"
                            )
                    else:
                        logger.error(
                            f"Failed to fetch {file_path}: HTTP {response.status_code}"
                        )
            else:
                # Local file - read directly from filesystem
                # Gateway runs on host, so it has direct access
                logger.info(f"Reading local file: {file_path}")

                local_path = FilePath(file_path)
                if local_path.exists() and local_path.is_file():
                    content = local_path.read_text(encoding="utf-8")
                    file_content.append(f"{label}: {file_path}\n\n{content}")
                    context_gathered[context_key] += 1
                    logger.info(f"Read {len(content)} chars from {file_path}")
                else:
                    logger.error(f"File not found: {file_path}")

        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")

    return file_content


def _format_path_tree(paths: List[str]) -> str:
    """
    Format a list of paths as a tree-like structure for display.
    Groups paths by their parent directories for better readability.
    """
    if not paths:
        return ""

    # Sort paths for consistent display
    sorted_paths = sorted(paths)

    lines = []
    for path in sorted_paths:
        # Determine if it's a folder or file based on trailing slash or lack of extension
        if path.endswith("/") or path.endswith("\\"):
            lines.append(f"  📁 {path}")
        else:
            lines.append(f"  📄 {path}")

    return "\n".join(lines)


async def _gather_reference_files(
    agent: AgentConfig,
    paths: List[str],
    context_gathered: Dict[str, int],
) -> List[str]:
    """Gather content from reference files (local or Azure DevOps)."""
    return await _gather_files(
        agent, paths, context_gathered, "reference_files", "Reference File"
    )


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
    logger.info(f"Crawling {len(request.seed_urls)} seed URLs")

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                f"{agent.crawler_url}/crawl",
                json={
                    "urls": request.seed_urls,  # Crawler expects list of URLs
                    "depth": request.crawl_depth,
                    "max_results": 10,
                },
                headers={"X-Request-ID": request_id},
            )

            if response.status_code == 200:
                crawl_data = response.json()
                docs = crawl_data.get("docs", [])

                # Index documents if embedding enabled
                if request.enable_embedding and docs:
                    logger.info(f"Indexing {len(docs)} crawled documents")

                    # Prepare headers with token
                    index_headers = {"X-Request-ID": request_id}
                    token = get_token()
                    if token:
                        index_headers["Authorization"] = f"Bearer {token}"
                    else:
                        logger.warning("No Bearer token available for Indexer request")

                    await client.post(
                        f"{agent.indexer_url}/index",
                        json={"docs": docs},
                        headers=index_headers,
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
    reference_content: List[str],
    crawled_content: List[str],
) -> str:
    """Build combined context string from all sources."""
    context_parts = []

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


def _apply_workflow_restrictions(workflow: WorkflowType, expose_to_llm: dict) -> dict:
    """
    Apply workflow-specific restrictions to the expose_to_llm settings.

    GENERAL_CHAT workflow restrictions:
    - azure_devops_mcp: Always disabled

    CODE_ANALYSIS and BUILD_SYSTEM_ANALYSIS:
    - All options available (use client settings as-is)

    Args:
        workflow: The workflow type
        expose_to_llm: Original client settings

    Returns:
        Modified expose_to_llm dict with workflow restrictions applied
    """
    # Start with a copy of the original settings
    effective_settings = dict(expose_to_llm)

    if workflow == WorkflowType.GENERAL_CHAT:
        # GENERAL_CHAT: Disable Azure DevOps access
        effective_settings["azure_devops_mcp"] = False
        logger.info("GENERAL_CHAT workflow: Azure DevOps MCP disabled")

    return effective_settings


def _file_download_prompt_section() -> str:
    """Build the file download instruction section for system prompts."""
    return (
        "\nFILE DOWNLOAD RULES (MANDATORY):\n"
        "- When you retrieve file content using ANY tool (get_azure_devops_file, "
        "read_local_file, get_azure_devops_commit_changes, "
        "get_azure_devops_commit_file_diff, search_azure_devops_code, or any "
        "other file-retrieving tool), you MUST call save_file_for_download with "
        "the content so the user can download the file from the chat UI.\n"
        "- When you generate reports, analysis summaries, code, scripts, "
        "configuration files, or any document the user would want to save, "
        "you MUST call save_file_for_download to offer a download.\n"
        "- CRITICAL: NEVER say 'I have saved the file' or 'a download is available' "
        "unless you have ACTUALLY called the save_file_for_download tool in this "
        "conversation. Claiming a file was saved without calling the tool is "
        "incorrect behavior.\n"
        "- You do NOT need to include download links in your response text. "
        "The chat UI will automatically show download buttons when you call "
        "save_file_for_download.\n"
        "- Use an appropriate filename with the correct file extension.\n"
        "- When writing a report or analysis, save the full report as a "
        "markdown file via save_file_for_download.\n\n"
    )


def _build_system_prompt_general_chat(expose_to_llm: dict) -> str:
    """
    Build system prompt for GENERAL_CHAT workflow.

    System role: Informational consultant - casual, helpful conversation.
    Limited options: No target files, no reference files, no Azure DevOps exposure.

    Note: Tool descriptions are NOT included in the system prompt to avoid
    the "double definition" problem with OpenAI models. Tools are passed
    via the tools=[...] parameter which contains their descriptions.
    """
    system_prompt = (
        "You are a friendly and knowledgeable Informational Consultant.\n"
        "Your goal is to provide helpful, accurate information and have engaging conversations.\n\n"
        "You excel at:\n"
        "- Answering general questions across various topics\n"
        "- Explaining concepts in clear, accessible language\n"
        "- Providing thoughtful analysis and recommendations\n"
        "- Having natural, conversational exchanges\n\n"
    )

    system_prompt += (
        "GUIDELINES:\n"
        "- Be conversational and approachable\n"
        "- Provide clear, well-organized responses\n"
        "- Ask clarifying questions when the request is ambiguous\n"
        "- Focus on being helpful rather than technical\n"
        "- If you don't know something, say so honestly\n"
        "- **Focus**: The input message may contain previous conversation history. You must ONLY answer the NEWEST/LAST question or instruction at the very end. Treat everything before it as read-only context.\n"
    )

    return system_prompt


def _build_system_prompt_code_analysis(expose_to_llm: dict) -> str:
    """
    Build system prompt for CODE_ANALYSIS workflow.

    System role: Technical architect for deep code analysis, review, and refactoring.
    All options available.

    Note: Tool descriptions are NOT included in the system prompt to avoid
    the "double definition" problem with OpenAI models. Tools are passed
    via the tools=[...] parameter which contains their descriptions.
    """
    system_prompt = (
        "You are an expert Technical Architect specializing in code analysis, review, and refactoring.\n"
        "Your goal is to provide deep technical analysis, identify issues, and propose improvements.\n\n"
        "Your expertise includes:\n"
        "- **Code Analysis**: Understanding code structure, logic flow, and dependencies\n"
        "- **Code Review**: Identifying bugs, security issues, performance problems, and code smells\n"
        "- **Refactoring**: Proposing and implementing structural improvements\n"
        "- **Architecture Assessment**: Evaluating design patterns and architectural decisions\n"
        "- **Best Practices**: Applying industry standards and coding conventions\n\n"
    )

    system_prompt += (
        "WORKFLOW & CONTEXT HANDLING:\n"
        "You will receive inputs categorized as Target Files, Reference Files, or Web/Seed Content.\n\n"
        "1. **Target Files (Code to Analyze):**\n"
        "   - **Analyze**: Detailed breakdown of structure, logic, and dependencies.\n"
        "   - **Review**: Identify issues, bugs, security concerns, and improvements.\n"
        "   - **Refactor**: If requested, propose a refactoring plan, then generate the improved code.\n\n"
        "2. **Reference Files & Web Content:**\n"
        "   - Treat these as **CONTEXT & KNOWLEDGE SOURCES**.\n"
        "   - Use them to understand coding standards, patterns, and project conventions.\n\n"
        "3. **Active Information Gathering:**\n"
        "   - If context is insufficient, use available tools to gather more information.\n"
        "   - Use Azure DevOps tools to explore related code and dependencies.\n\n"
    )

    system_prompt += (
        "CRITICAL RULES:\n"
        "- **Code Search**: Prefer `search_azure_devops_code` for finding dependencies and definitions.\n"
        "- **Be Thorough**: Provide comprehensive analysis with specific line references.\n"
        "- **Actionable Feedback**: Give concrete suggestions, not vague recommendations.\n"
        "- **Focus**: The input message may contain previous conversation history. You must ONLY answer the NEWEST/LAST question or instruction at the very end. Treat everything before it as read-only context.\n"
    )

    system_prompt += _file_download_prompt_section()

    return system_prompt


def _build_system_prompt_build_system(expose_to_llm: dict) -> str:
    """
    Build system prompt for BUILD_SYSTEM_ANALYSIS workflow.

    System role: Technical architect and expert build engineer for metadata, manifest,
    and build system analysis.
    All options available.

    Note: Tool descriptions are NOT included in the system prompt to avoid
    the "double definition" problem with OpenAI models. Tools are passed
    via the tools=[...] parameter which contains their descriptions.
    """
    system_prompt = (
        "You are a Principal Build Architect and Release Manager specializing in **Windows OS Engineering**.\n"
        "Your deep expertise covers the Windows Build System, Component-Based Servicing (CBS), Modular Build System (MBS), Feature, Feature OnDemand Package and OS Image Composition.\n"
        "You do not just read code; you visualize the dependency graph that creates a bootable Windows Image (FFU/WIM).\n\n"
        "YOUR SPECIALIZED EXPERTISE INCLUDES:\n"
        "- **Build Engines**: MSBuild (`.targets`, `.props`), NMake, and custom Windows build tools.\n"
        "- **OS Composition**: Analyzing Feature Manifests (FM), OEMInput files, and Component Manifests.\n"
        "- **Package Management**: Understanding how Packages (CAB/APPX/MBS/FOD) bundle Binaries, Drivers (`.inf`), and Registry keys.\n"
        "- **Dependency Logic**: Resolving API contracts, binary compatibility, and 'OneCore' vs 'Desktop' dependencies.\n"
        "- **Refactoring**: Decoupling circular dependencies and optimizing Image Size (disk footprint).\n\n"
    )

    system_prompt += (
        "WORKFLOW & CONTEXT HANDLING:\n"
        "You will receive build files, manifests, or metadata as Target Files and supporting context.\n\n"
        "1. **Target Files (Build/Metadata Files):**\n"
        "   - **Analyze**: Understand build targets, dependencies, and configuration.\n"
        "   - **Diagnose**: Identify build errors, missing dependencies, version conflicts.\n"
        "   - **Optimize**: Suggest improvements for build performance and reliability.\n"
        "   - **Restructure**: If requested, propose and implement build system changes.\n\n"
        "2. **Reference Files & Documentation:**\n"
        "   - Use these to understand project conventions and build requirements.\n"
        "   - Cross-reference with official documentation when needed.\n\n"
        "3. **Active Information Gathering:**\n"
        "   - Explore related build files to understand the full dependency graph.\n"
        "   - Look for common build patterns and configurations in the codebase.\n\n"
    )

    system_prompt += (
        "CRITICAL RULES:\n"
        "- **Dependency Analysis**: Always consider transitive dependencies and version compatibility.\n"
        "- **Platform Awareness**: Note platform-specific build configurations and conditions.\n"
        "- **Be Precise**: Provide exact file paths, target names, and configuration values.\n"
        "- **Focus**: The input message may contain previous conversation history. You must ONLY answer the NEWEST/LAST question or instruction at the very end. Treat everything before it as read-only context.\n"
    )

    system_prompt += _file_download_prompt_section()

    return system_prompt


def _build_system_prompt_file_explorer(expose_to_llm: dict) -> str:
    """
    Build system prompt for FILE_EXPLORER workflow.

    System role: DevOps and local file assistant for browsing and searching files.
    All options available.
    """
    system_prompt = (
        "You are an expert DevOps Engineer and File System Assistant.\n"
        "Your goal is to help users browse, search, and explore repositories and local file systems efficiently.\n\n"
        "Your expertise includes:\n"
        "- **File Browsing**: Navigate directory structures, list folder contents\n"
        "- **Content Search**: Find files containing specific keywords or patterns\n"
        "- **Filename Matching**: Search by wildcards (*.cpp, test_*.py), prefixes, suffixes\n"
        "- **Folder Matching**: Find directories by name patterns\n"
        "- **Query Construction**: Automatically build aggregated search queries from natural language\n"
        "- **Pattern Recognition**: Understand file naming conventions and project structures\n\n"
    )

    system_prompt += (
        "QUERY CONSTRUCTION GUIDELINES:\n"
        "When a user asks to find files, automatically construct appropriate queries:\n\n"
        "1. **By Filename Pattern**:\n"
        '   - "find all JSON files" → pattern: `*.json`\n'
        '   - "find test files" → pattern: `test_*.py` or `*_test.py`\n'
        '   - "find config files" → pattern: `*config*` or `*.config.*`\n'
        "   - \"files starting with 'auth'\" → pattern: `auth*`\n"
        "   - \"files ending with '_helper'\" → pattern: `*_helper.*`\n\n"
        "2. **By Content Keyword**:\n"
        "   - \"find files containing 'TODO'\" → content search for 'TODO'\n"
        "   - \"where is class X defined\" → content search for 'class X'\n"
        "   - \"find imports of module Y\" → content search for 'import Y' or 'from Y'\n\n"
        "3. **By Folder Pattern**:\n"
        '   - "in the tests folder" → scope to `tests/` or `**/tests/**`\n'
        '   - "under src directory" → scope to `src/**`\n'
        '   - "find all util folders" → pattern: `**/util*/**`\n\n'
        "4. **Combined Queries**:\n"
        "   - \"find Python files containing 'async'\" → filename `*.py` + content 'async'\n"
        '   - "JSON configs in settings folder" → folder `**/settings/**` + pattern `*.json`\n\n'
    )

    system_prompt += (
        "INPUT CONTEXT USAGE (File Explorer Specific):\n"
        "1. **Target File Paths**: These are EXAMPLE files that match what the user wants to find.\n"
        "   - Study their naming patterns, extensions, and folder locations.\n"
        "   - Use them to understand what KIND of files to search for.\n"
        "   - Extract patterns: if given `src/utils/helper.py`, look for similar `*helper*.py` files.\n\n"
        "2. **Reference Files**: These are INSTRUCTIONS or HELP TIPS on how to find expected files.\n"
        "   - May contain documentation about project structure or naming conventions.\n"
        "   - May describe where certain file types are typically located.\n"
        "   - Use this knowledge to construct better search queries.\n\n"
        "3. **Seed URL Content**: Same purpose as Reference Files - provides CONTEXT and INSTRUCTIONS.\n"
        "   - May contain wiki pages about project organization.\n"
        "   - May describe file naming standards or folder structures.\n"
        "   - Use this documentation to understand where to search.\n\n"
    )

    system_prompt += (
        "CRITICAL RULES:\n"
        "- **Be Proactive**: Construct and execute queries without asking for clarification.\n"
        "- **Use Multiple Tools**: Combine filename and content searches for better results.\n"
        "- **Show Results Clearly**: List found files with paths and brief descriptions.\n"
        "- **Summarize Patterns**: If many files found, group by folder or type.\n"
        "- **Focus**: The input message may contain previous conversation history. You must ONLY answer the NEWEST/LAST question or instruction at the very end. Treat everything before it as read-only context.\n\n"
    )

    # Add strong function calling instructions
    system_prompt += (
        "**CRITICAL - FUNCTION CALLING RULES:**\n"
        "When you need to use a tool, you MUST use the function calling mechanism.\n"
        "- DO NOT output JSON in your response text to call tools.\n"
        "- DO NOT write out tool parameters as JSON - invoke the tool directly.\n"
        "- Use the proper function calling API provided to you.\n"
        "- If you want to crawl a URL or search files, make the actual tool call.\n"
        '- WRONG: Writing `{"query": "...", "seed_urls": [...]}` in your response.\n'
        "- RIGHT: Invoking the tool through the function calling interface.\n"
    )

    system_prompt += _file_download_prompt_section()

    return system_prompt


def _build_system_prompt(workflow: WorkflowType, expose_to_llm: dict) -> str:
    """
    Route to the appropriate prompt builder based on workflow type.

    Args:
        workflow: The workflow type selected by the client
        expose_to_llm: Dictionary of tools to expose to the LLM

    Returns:
        System prompt string appropriate for the workflow
    """
    if workflow == WorkflowType.GENERAL_CHAT:
        return _build_system_prompt_general_chat(expose_to_llm)
    elif workflow == WorkflowType.CODE_ANALYSIS:
        return _build_system_prompt_code_analysis(expose_to_llm)
    elif workflow == WorkflowType.BUILD_SYSTEM_ANALYSIS:
        return _build_system_prompt_build_system(expose_to_llm)
    elif workflow == WorkflowType.FILE_EXPLORER:
        return _build_system_prompt_file_explorer(expose_to_llm)
    else:
        # Default to code analysis for unknown workflow types
        logger.warning(
            f"Unknown workflow type: {workflow}, defaulting to CODE_ANALYSIS"
        )
        return _build_system_prompt_general_chat(expose_to_llm)


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
            elif msg.get("role") == "assistant":
                # Optimization: Include placeholder assistant message to maintain
                # conversation flow (User -> Assistant -> User) without using tokens
                # for the full response. This prevents the LLM from thinking previous
                # user questions are unanswered.
                messages.append(
                    {"role": "assistant", "content": "[Response omitted for brevity]"}
                )
        if history:
            logger.info(
                f"Loaded {len([m for m in history if m.get('role') in ['user', 'assistant']])} messages from history (assistant responses truncated)"
            )

    # Add current message with context
    if full_context:
        messages.append(
            {
                "role": "user",
                "content": f"Context:\n\n{full_context}\n\n---\n\nQuestion: {user_message}",
            }
        )
    else:
        messages.append({"role": "user", "content": user_message})

    return messages


# =============================================================================
# Helper Functions - Tools
# =============================================================================


async def _load_tools(
    agent: AgentConfig,
    expose_to_llm: Dict[str, bool],
    seed_urls: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Load tools based on expose_to_llm settings.

    Args:
        agent: Agent configuration
        expose_to_llm: Dict of which tools to expose to LLM
        seed_urls: Optional seed URLs to include in crawler tool description
    """
    tools = []

    if expose_to_llm.get("azure_devops_mcp", False):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{agent.azure_devops_mcp_url}/tools")
                if response.status_code == 200:
                    az_tools = response.json().get("tools", [])
                    tools.extend(
                        [convert_mcp_tool_to_openai(tool) for tool in az_tools]
                    )
                    logger.info(
                        f"Exposed {len(az_tools)} Azure DevOps MCP tools to LLM"
                    )
        except Exception as e:
            logger.error(f"Failed to load Azure DevOps MCP tools: {e}")

    if expose_to_llm.get("crawler", False):
        from gateway.llm.prompts import build_crawler_tool_with_seed_urls

        # Build crawler tool with seed URLs in description so LLM knows to prioritize them
        crawler_tool = build_crawler_tool_with_seed_urls(seed_urls)
        tools.append(crawler_tool)
        if seed_urls:
            logger.info(
                f"Exposed crawler tool to LLM with {len(seed_urls)} priority seed URLs"
            )
        else:
            logger.info("Exposed crawler tool to LLM")

    # Windows Composition Tool
    # Only expose if configured via environment variable AND requested by client
    if os.getenv("WIN_COMP_BRIDGE_URL") and expose_to_llm.get(
        "windows_composition", False
    ):
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": TOOL_QUERY_COMPOSITION_DB,
                    "description": (
                        "Query the Windows Composition Database (WCD) via the "
                        "global $d object. WCD models the relationship between "
                        "Editions, Packages, Assemblies, Files, and APIs. "
                        "Common entry points on $d include: Editions, Packages, "
                        "Assemblies, BuildFiles, RegistryValues, Apis, "
                        "ProductGroups. You can use methods like "
                        "GetInclusionGraph() to trace dependencies. "
                        "The output is a text-based tree view, not JSON. "
                        "Example output for GetInclusionGraph:\n"
                        "(EDITION):ServerDatacenterNano\n"
                        "  (PACKAGE):Microsoft-Windows-ServerDatacenterNanoEdition\n"
                        "    (PACKAGE):Microsoft-Windows-EditionPack-ServerDatacenterNano\n"
                        "      (FEATUREPACKAGE):Microsoft-Win2\n"
                        "        (PACKAGE):Runlevel-Win1\n"
                        "          (COMPONENT):Microsoft-Windows-Csrss\n"
                        "            (NTTREE):csrss.exe"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": (
                                    "The PowerShell command snippet accessing $d. "
                                    "Examples: "
                                    "$d.Editions['Professional'].AssemblyFilesDeep, "
                                    "$d.Packages['*ServerCore*'], "
                                    "$($d.BuildFiles['*file.dll'])."
                                    "GetInclusionGraph($d.Editions['Professional']), "
                                    "$d.RegistryValues['HKEY_CLASSES_ROOT\\*']."
                                    "ContainingPackages"
                                ),
                            }
                        },
                        "required": ["query"],
                    },
                },
            }
        )
        logger.info("Exposed Windows Composition tool to LLM")

    # Memory Search Tool - expose if memory service is configured
    if agent.memory_service_url and expose_to_llm.get("memory", True):
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": TOOL_MEMORY_SEARCH,
                    "description": (
                        "Search your long-term memory for relevant context, facts, "
                        "preferences, or past decisions. Use this when you need to "
                        "recall information from previous conversations, or when "
                        "the user asks 'do you remember...', 'what did I tell you "
                        "about...', or references past context. Returns memories "
                        "ranked by relevance using hybrid semantic + keyword search."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": (
                                    "Search query - what are you trying to recall? "
                                    "Be specific about what information you need."
                                ),
                            },
                        },
                        "required": ["query"],
                    },
                },
            }
        )
        logger.info("Exposed memory_search tool to LLM")

    # Always expose save_file_for_download tool when any tools are being loaded
    # This lets the LLM offer file downloads to the user
    if tools:  # Only add if we have at least one other tool
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": TOOL_SAVE_FILE_FOR_DOWNLOAD,
                    "description": (
                        "Save content as a downloadable file for the user. "
                        "You MUST call this tool whenever you retrieve file "
                        "content from ANY source (get_azure_devops_file, "
                        "read_local_file, get_azure_devops_commit_file_diff, "
                        "search_azure_devops_code, etc.) so the user can "
                        "download files directly from the chat UI. "
                        "Also call this when you generate reports, analysis, "
                        "code, scripts, or any document the user would want "
                        "to keep. The user will see a download button "
                        "automatically. NEVER claim you saved a file without "
                        "actually calling this tool."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": (
                                    "Filename for the download. Include the file "
                                    "extension. Examples: 'easyBMT.ps1', "
                                    "'config.json', 'analysis.md'"
                                ),
                            },
                            "content": {
                                "type": "string",
                                "description": (
                                    "The full file content to save. Must be the "
                                    "complete content, not truncated."
                                ),
                            },
                            "content_type": {
                                "type": "string",
                                "description": (
                                    "MIME type of the file. Default: 'text/plain'. "
                                    "Examples: 'text/plain', 'application/json', "
                                    "'text/markdown', 'text/x-powershell'"
                                ),
                            },
                        },
                        "required": ["filename", "content"],
                    },
                },
            }
        )
        logger.info("Exposed save_file_for_download tool to LLM")

    return tools


# =============================================================================
# Helper Functions - LLM Execution
# =============================================================================

# Per-tool round limits loaded from environment variable as JSON
# Format: {"tool_name": limit, ...}
# Tools not specified use DEFAULT_TOOL_ROUND_LIMIT
# Use -1 or a very large number for unlimited
_tool_limits_json = os.getenv(
    "TOOL_ROUND_LIMITS",
    json.dumps(DEFAULT_TOOL_LIMITS),
)

try:
    TOOL_ROUND_LIMITS: Dict[str, int] = json.loads(_tool_limits_json)
except json.JSONDecodeError:
    logger.warning(f"Invalid TOOL_ROUND_LIMITS JSON, using defaults")
    TOOL_ROUND_LIMITS = DEFAULT_TOOL_LIMITS.copy()

# Default limit for unknown tools
DEFAULT_TOOL_ROUND_LIMIT = int(os.getenv("MAX_TOOL_ROUNDS", "5"))

# Maximum elapsed time for agent loop before forcing a final answer (seconds)
# Default 900s = 15 min.  Covers ~5 Opus rounds comfortably.
MAX_AGENT_ELAPSED_SECONDS = int(os.getenv("MAX_AGENT_ELAPSED_SECONDS", "900"))


def _get_tool_limit(tool_name: str) -> int:
    """Get the round limit for a specific tool. Returns -1 for unlimited."""
    return TOOL_ROUND_LIMITS.get(tool_name, DEFAULT_TOOL_ROUND_LIMIT)


def _check_tool_limits(
    tool_calls: List[Dict[str, Any]], tool_usage: Dict[str, int]
) -> List[str]:
    """
    Check if any tools have exceeded their limits.

    Returns list of tools that have exceeded their limits.
    Tools with limit -1 are unlimited and never exceed.
    """
    exceeded = []
    for tool_call in tool_calls:
        tool_name = tool_call.get("function", {}).get("name", "unknown")
        limit = _get_tool_limit(tool_name)
        if limit == -1:
            continue  # Unlimited
        current_usage = tool_usage.get(tool_name, 0)
        if current_usage >= limit:
            exceeded.append(tool_name)
    return exceeded


async def _execute_llm_with_tools(
    request: UnifiedWorkflowRequest,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    request_id: str,
    context_gathered: Dict[str, int],
    conversation_id: str,
    bearer_token: Optional[str] = None,
) -> Tuple[str, Optional[int]]:
    """Execute LLM with tool calling loop.

    Checks for cancellation between tool calls and LLM rounds.

    Args:
        request: Workflow request
        messages: Chat messages
        tools: Available tools
        request_id: Request ID for logging
        context_gathered: Context gathering stats
        conversation_id: Conversation ID for cancellation
        bearer_token: Optional bearer token for LLM authentication
    """
    # Check for cancellation at start
    if _is_request_cancelled(conversation_id):
        logger.info(f"Request cancelled before LLM execution: {conversation_id}")
        return "*Request was cancelled.*", None

    llm_client = LLMClient()
    tool_handler = get_tool_handler()
    tool_round = 0
    # Track per-tool usage
    tool_usage: Dict[str, int] = {}
    # Track elapsed time for time-budget enforcement
    agent_start_time = time.monotonic()

    # Log tools
    if tools:
        logger.info(
            f"Passing {len(tools)} tools to LLM: {[t.get('function', {}).get('name', '?') for t in tools]}"
        )

    # Initial LLM call (max_tokens is model-specific, handled by LLM client)
    response = await llm_client.chat_completion(
        model=request.model or "gpt-4",
        messages=messages,
        tools=tools if tools else None,
        tool_choice="auto" if tools else "none",
        bearer_token=bearer_token,
    )
    response = cast(Dict[str, Any], response)

    logger.info(
        f"Initial LLM response - has tool_calls: {bool(response.get('tool_calls'))}"
    )

    # Tool execution loop with per-tool limits (no total limit)
    while response.get("tool_calls"):
        tool_round += 1

        # Check for cancellation before each tool round
        if _is_request_cancelled(conversation_id):
            logger.info(
                f"Request cancelled during tool round {tool_round}: {conversation_id}"
            )
            return "*Request was cancelled by user.*", None

        # ── Time-budget enforcement ──────────────────────────────────
        elapsed = time.monotonic() - agent_start_time
        if elapsed > MAX_AGENT_ELAPSED_SECONDS:
            logger.warning(
                f"Agent time budget exceeded ({elapsed:.0f}s > "
                f"{MAX_AGENT_ELAPSED_SECONDS}s) after {tool_round - 1} tool "
                f"rounds.  Forcing final answer."
            )
            # Ask the LLM to wrap up with what it has — no more tools
            messages.append(
                {
                    "role": "assistant",
                    "content": response.get("content") or "",
                    "tool_calls": response["tool_calls"],
                }
            )
            # Add a synthetic tool result informing the model
            for tc in response["tool_calls"]:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", "budget"),
                        "content": (
                            "⏱️ Time budget exceeded — please provide your "
                            "best answer now using the information already gathered."
                        ),
                    }
                )
            # Final LLM call with NO tools so it cannot request more
            wrap_response = await llm_client.chat_completion(
                model=request.model or "gpt-4",
                messages=messages,
                tools=None,
                tool_choice="none",
                bearer_token=bearer_token,
            )
            wrap_text = wrap_response.get("content") or ""
            wrap_tokens = wrap_response.get("usage", {}).get("total_tokens")
            budget_note = (
                f"\n\n---\n*⏱️ Response generated under time budget "
                f"({elapsed:.0f}s elapsed, {tool_round - 1} tool rounds). "
                f"Some tool calls were skipped.*"
            )
            return (wrap_text + budget_note), wrap_tokens

        # Check which tools have exceeded their limits
        exceeded_tools = _check_tool_limits(response["tool_calls"], tool_usage)

        if exceeded_tools:
            # Filter out tool calls that have exceeded their limits
            valid_tool_calls = [
                tc
                for tc in response["tool_calls"]
                if tc.get("function", {}).get("name", "unknown") not in exceeded_tools
            ]

            if not valid_tool_calls:
                # All requested tools have exceeded limits
                logger.warning(
                    f"All requested tools exceeded limits: {exceeded_tools}. "
                    f"Tool usage: {tool_usage}"
                )
                break

            logger.info(
                f"Filtered out tools that exceeded limits: {exceeded_tools}. "
                f"Proceeding with: {[tc.get('function', {}).get('name') for tc in valid_tool_calls]}"
            )
            response["tool_calls"] = valid_tool_calls

        logger.info(f"Tool execution round {tool_round} " f"(tool usage: {tool_usage})")

        # Add assistant message with tool calls
        messages.append(
            {
                "role": "assistant",
                "content": response.get("content") or "",
                "tool_calls": response["tool_calls"],
            }
        )

        # Execute each tool call
        for tool_call in response["tool_calls"]:
            # Check for cancellation before each tool call
            if _is_request_cancelled(conversation_id):
                logger.info(
                    f"Request cancelled before tool execution: {conversation_id}"
                )
                return "*Request was cancelled by user.*", None

            tool_name = tool_call.get("function", {}).get("name", "unknown")

            # Inject conversation_id for save_file_for_download so files
            # are tracked per conversation
            if tool_name == TOOL_SAVE_FILE_FOR_DOWNLOAD:
                try:
                    args = json.loads(tool_call["function"]["arguments"])
                    args["conversation_id"] = conversation_id
                    tool_call["function"]["arguments"] = json.dumps(args)
                except (json.JSONDecodeError, KeyError):
                    pass

            # Increment tool usage counter
            tool_usage[tool_name] = tool_usage.get(tool_name, 0) + 1
            tool_limit = _get_tool_limit(tool_name)

            logger.info(
                f"Executing tool: {tool_name} "
                f"(usage: {tool_usage[tool_name]}/{tool_limit})"
            )

            tool_result = await tool_handler.handle_tool_call(
                tool_call,
                request_id,
                skip_embedding=not request.enable_embedding,
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
            model=request.model or "gpt-4",
            tools=tools,
            tool_choice="auto",
            bearer_token=bearer_token,
        )

        if not response.get("tool_calls"):
            logger.info(f"LLM finished after {tool_round} tool rounds")
            break

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
            crawler_url=os.getenv("CRAWLER_URL", "http://crawler:8001"),
            indexer_url=os.getenv("INDEXER_URL", "http://indexer:8002"),
            azure_devops_mcp_url=os.getenv(
                "AZURE_DEVOPS_MCP_URL", "http://azure-devops-mcp-server:8004"
            ),
            memory_service_url=os.getenv("MEMORY_SERVICE_URL"),
        )
    return _agent_config


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/chat", response_model=UnifiedWorkflowResponse)
async def execute(
    request: UnifiedWorkflowRequest,
    bearer_token: Optional[str] = Depends(get_bearer_token),
):
    """
    Execute agent workflow - single endpoint for all use cases.

    Workflow:
    1. Expand and gather context from reference_files (Local)
    2. Crawl seed_urls if provided
    3. Build messages and tools for LLM
    4. Execute LLM with tool calling loop
    5. Return response with conversation tracking

    Args:
        request: Workflow request with user message and context
        bearer_token: Optional Entra ID bearer token for Azure Foundry authentication
    """
    request_id = str(uuid.uuid4())
    request_start_time = time.time()
    workflow_name = request.workflow.value if request.workflow else "unknown"

    log_request(
        logger,
        request_id,
        "POST",
        "/agent/chat",
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

    # Check if there's already an active request for this conversation
    if _is_conversation_busy(conversation_id):
        logger.warning(f"Conversation {conversation_id} already has an active request")
        raise HTTPException(
            status_code=409,
            detail="This conversation already has an active request. Please wait for it to complete or cancel it first.",
        )

    # Mark this request as active
    _mark_request_active(conversation_id, request_id)

    try:
        agent = get_agent_config()
        context_gathered = {
            "reference_files": 0,
            "crawled_urls": 0,
            "web_search_results": 0,
        }

        # Step 1: Expand reference file paths (with metrics)
        async with AgentActivityTimer("expand_paths") as expand_timer:
            expanded_reference_files = await _expand_paths(
                agent, request.reference_files or []
            )
            expand_timer.items = len(expanded_reference_files)

        if request.reference_files:
            logger.info(
                f"Expanded {len(request.reference_files)} reference files to {len(expanded_reference_files)} files"
            )

        # Step 2: Gather context from all sources (with metrics)
        async with AgentActivityTimer("prefetch_local") as local_timer:
            reference_content = await _gather_reference_files(
                agent, expanded_reference_files, context_gathered
            )
            local_timer.items = context_gathered.get("reference_files", 0)

        async with AgentActivityTimer("crawl") as crawl_timer:
            crawled_content = await _crawl_urls(
                agent, request, request_id, context_gathered
            )
            crawl_timer.items = context_gathered.get(
                "crawled_urls", 0
            ) + context_gathered.get("web_search_results", 0)

        # Step 3: Build context and messages
        full_context = _build_context_string(reference_content, crawled_content)
        logger.info(f"Full context: {len(full_context)} chars")

        # Apply workflow-specific settings
        effective_expose_to_llm = _apply_workflow_restrictions(
            request.workflow, request.expose_to_llm
        )

        system_prompt = _build_system_prompt(request.workflow, effective_expose_to_llm)

        # Memory integration: Inject MEMORY.md for new conversations
        is_new_conversation = request.clear_history or not request.conversation_id
        if is_memory_enabled() and is_new_conversation:
            durable_memory = await read_durable_memory_async()
            if durable_memory:
                system_prompt += f"\n\n## Your Long-term Memory\n\n{durable_memory}"
                logger.info(f"Injected durable memory: {len(durable_memory)} chars")

        # Memory integration: Log user message to daily log
        await append_to_daily_log_async(request.user_message, "user", conversation_id)

        messages = _build_messages(
            system_prompt,
            full_context,
            request.user_message,
            request.conversation_id,
            request.clear_history,
        )

        # Step 4: Load tools (use effective settings with workflow restrictions)
        # Pass seed_urls so LLM knows which URLs to prioritize when crawling
        tools = await _load_tools(agent, effective_expose_to_llm, request.seed_urls)

        # Memory integration: Check for 80% context flush
        flush_triggered, flush_prompt, token_pct = check_and_get_flush_prompt(
            messages, provider_type="default"
        )
        if flush_triggered and flush_prompt:
            messages.append({"role": "system", "content": flush_prompt})
            logger.info(
                f"Injected distillation prompt at {token_pct:.0%} context usage"
            )

        # Step 5: Execute LLM with tools (with metrics)
        async with AgentActivityTimer("llm_loop") as llm_timer:
            response_text, tokens_used = await _execute_llm_with_tools(
                request,
                messages,
                tools,
                request_id,
                context_gathered,
                conversation_id,
                bearer_token,
            )
            llm_timer.items = tokens_used

        # Memory integration: Parse distillation markers if flush was triggered
        if flush_triggered:
            response_text, summary, facts = await parse_and_save_distillation_async(
                response_text
            )
            if summary or facts:
                logger.info(
                    f"Distillation complete: summary={len(summary)} chars, facts={len(facts)} chars"
                )

        # Memory integration: Log assistant response to daily log
        await append_to_daily_log_async(response_text, "assistant", conversation_id)

        # Step 6: Save conversation history
        conversation_store.add_message(conversation_id, "user", request.user_message)
        conversation_store.add_message(conversation_id, "assistant", response_text)

        # Step 7: Collect downloadable files saved during tool execution
        file_store = get_file_store()
        stored_files = file_store.get_files_for_conversation(conversation_id)
        downloadable_files = [
            {
                "file_id": f.file_id,
                "filename": f.filename,
                "size": f.size,
                "content_type": f.content_type,
            }
            for f in stored_files
        ]

        result = UnifiedWorkflowResponse(
            response=response_text,
            conversation_id=conversation_id,
            model=request.model or "default",
            tokens_used=tokens_used,
            context_gathered=context_gathered,
            downloadable_files=downloadable_files,
        )

        # Record successful agent request
        request_duration = time.time() - request_start_time
        record_agent_request(
            workflow=workflow_name,
            status="success",
            duration=request_duration,
            conversation_id=conversation_id,
        )

        log_response(logger, request_id, 200, 0.0)
        return result

    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        log_response(logger, request_id, 500, 0.0, error=str(e))

        # Record failed agent request
        request_duration = time.time() - request_start_time
        error_type = classify_error(e)
        record_agent_request(
            workflow=workflow_name,
            status="error",
            duration=request_duration,
            error_type=error_type,
            error_message=str(e),
            conversation_id=conversation_id,
        )

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

    finally:
        # Always clear active request tracking when done
        _clear_active_request(conversation_id)


@router.post("/cancel/{conversation_id}")
async def cancel_request(conversation_id: str) -> Dict[str, Any]:
    """
    Cancel an active request for a conversation.

    Returns immediately after marking the request as cancelled.
    The actual cancellation happens at the next check point in the agent loop.
    """
    if _mark_request_cancelled(conversation_id):
        logger.info(f"Cancel request received for conversation: {conversation_id}")
        return {"status": "cancelling", "conversation_id": conversation_id}
    else:
        logger.info(f"No active request to cancel for conversation: {conversation_id}")
        return {"status": "no_active_request", "conversation_id": conversation_id}


@router.get("/status/{conversation_id}")
async def get_request_status(conversation_id: str) -> Dict[str, Any]:
    """
    Get the status of a conversation's request.

    Returns whether the conversation is busy (has an active request).
    """
    is_busy = _is_conversation_busy(conversation_id)
    is_cancelled = _is_request_cancelled(conversation_id)
    return {
        "conversation_id": conversation_id,
        "busy": is_busy,
        "cancelled": is_cancelled,
    }


@router.get("/health")
async def health_check() -> Any:
    """Agent health check."""
    try:
        agent = get_agent_config()
        return {
            "status": "healthy",
            "agent": "AgentConfig",
            "crawler_url": agent.crawler_url,
            "indexer_url": agent.indexer_url,
            "azure_devops_mcp_url": agent.azure_devops_mcp_url,
        }
    except Exception as e:
        logger.error(f"Agent health check failed: {e}")
        return JSONResponse(
            status_code=503, content={"status": "unhealthy", "error": str(e)}
        )


# =============================================================================
# Manual Distillation Endpoint
# =============================================================================


class DistillRequest(BaseModel):
    """Request for manual memory distillation."""

    conversation_id: str = Field(..., description="Conversation ID to distill")
    model: Optional[str] = Field(None, description="Model to use for distillation")


class DistillResponse(BaseModel):
    """Response from memory distillation."""

    success: bool
    conversation_id: str
    summary_preview: Optional[str] = None
    facts_preview: Optional[str] = None
    message: str


@router.post("/distill", response_model=DistillResponse)
async def manual_distill(
    request: DistillRequest,
    bearer_token: Optional[str] = Depends(get_bearer_token),
) -> DistillResponse:
    """
    Manual trigger for memory distillation (user-initiated).

    This endpoint allows users to trigger distillation at any time via the
    HiChat "Save to Memory" button, rather than waiting for the 80% context
    threshold.

    The distillation process:
    1. Loads conversation history
    2. Injects distillation prompt asking LLM to extract [SUMMARY] and [FACTS]
    3. Calls LLM with conversation context
    4. Parses response for markers
    5. Saves summary to daily log (sessional memory)
    6. Saves facts to MEMORY.md (durable memory)

    Args:
        request: DistillRequest with conversation_id
        bearer_token: Optional bearer token for LLM authentication

    Returns:
        DistillResponse with preview of saved memory
    """
    request_id = str(uuid.uuid4())
    conversation_id = request.conversation_id

    logger.info(f"Manual distill triggered for conversation: {conversation_id}")

    if not is_memory_enabled():
        return DistillResponse(
            success=False,
            conversation_id=conversation_id,
            message="Memory service is not enabled",
        )

    # Load conversation history
    conversation_store = get_conversation_store()
    history = conversation_store.get_messages(conversation_id)

    if not history:
        return DistillResponse(
            success=False,
            conversation_id=conversation_id,
            message="No conversation history found",
        )

    # Build messages with conversation history
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant. The user has requested to save "
                "important information from this conversation to long-term memory."
            ),
        }
    ]

    # Add conversation history
    for msg in history:
        if msg.get("role") in ["user", "assistant"]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    # Get distillation prompt (use 100% as indicator this is manual trigger)
    from gateway.utils.memory_integration import _get_distillation_prompt

    if not is_memory_enabled():
        return DistillResponse(
            success=False,
            conversation_id=conversation_id,
            message="Memory service not configured (MEMORY_SERVICE_URL not set)",
        )

    distill_prompt = _get_distillation_prompt(1.0)
    messages.append({"role": "system", "content": distill_prompt})

    # Call LLM to generate distillation
    try:
        llm_client = LLMClient()
        response = await llm_client.chat_completion(
            model=request.model or "gpt-4",
            messages=messages,
            tools=None,
            tool_choice="none",
            bearer_token=bearer_token,
        )

        response_text = response.get("content") or ""

        # Parse and save distillation
        clean_response, summary, facts = await parse_and_save_distillation_async(
            response_text
        )

        # Build response message
        saved_items = []
        if summary:
            saved_items.append("session summary")
        if facts:
            saved_items.append("durable facts")

        if saved_items:
            message = f"Saved {' and '.join(saved_items)} to memory"
        else:
            message = "No distillation markers found in LLM response"

        logger.info(
            f"Manual distill complete for {conversation_id}: "
            f"summary={len(summary)} chars, facts={len(facts)} chars"
        )

        return DistillResponse(
            success=bool(summary or facts),
            conversation_id=conversation_id,
            summary_preview=summary[:200] + "..." if len(summary) > 200 else summary,
            facts_preview=facts[:200] + "..." if len(facts) > 200 else facts,
            message=message,
        )

    except Exception as e:
        logger.error(f"Manual distill failed: {e}", exc_info=True)
        return DistillResponse(
            success=False,
            conversation_id=conversation_id,
            message=f"Distillation failed: {str(e)}",
        )

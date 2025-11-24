"""
Agent API router - Template-based workflow execution.

Provides:
1. GET /agent/templates - List all workflow templates
2. GET /agent/templates/{workflow} - Get specific template
3. POST /agent/execute - Execute workflow with filled template
"""

import fnmatch
import logging
import os
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
from gateway.llm.client import LLMClient

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

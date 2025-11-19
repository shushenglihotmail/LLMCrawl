"""
Agent API router - Template-based workflow execution.

Provides:
1. GET /agent/templates - List all workflow templates
2. GET /agent/templates/{workflow} - Get specific template
3. POST /agent/execute - Execute workflow with filled template
"""

import logging
import os
from typing import Union

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


def get_agent() -> CodeIntelligenceAgent:
    """Get or create agent instance."""
    global _agent
    if _agent is None:
        _agent = CodeIntelligenceAgent(
            mcp_url=os.getenv("MCP_SERVER_URL", "http://mcp:8003"),
            crawler_url=os.getenv("CRAWLER_URL", "http://crawler:8001"),
            indexer_url=os.getenv("INDEXER_URL", "http://indexer:8002"),
            llm_client=LLMClient(),
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
    logger.info(f"Target files: {len(request.target_files)}")
    logger.info(f"Educational files: {len(request.educational_files or [])}")
    logger.info(f"Web crawl URLs: {len(request.web_crawl_urls or [])}")

    try:
        agent = get_agent()

        # Prepare parameters
        target_files = request.target_files
        reference_files = request.educational_files or []

        # Determine web research strategy
        if request.web_crawl_urls:
            # User provided specific URLs to crawl
            web_research = True
            # TODO: Pass seed_urls to agent for targeted crawling
            logger.info(f"Will crawl: {request.web_crawl_urls}")
        else:
            # No URLs provided, skip web crawling
            web_research = False
            logger.info("Skipping web research (no URLs provided)")

        # Execute workflow
        result = await agent.execute_workflow(
            workflow=request.workflow,
            target_files=target_files,
            request=request.request,
            reference_files=reference_files,
            web_research=web_research,
            planning_model=request.planning_model,
            execution_model=request.execution_model,
        )

        # Check for errors
        if "error" in result:
            logger.error(f"Workflow execution failed: {result['error']}")
            raise HTTPException(
                status_code=500, detail=f"Workflow execution failed: {result['error']}"
            )

        logger.info(f"Workflow completed: {result.get('context_used', {})}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error executing workflow: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Workflow execution failed: {str(e)}"
        )


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

"""
Example integration of Code Intelligence Agent into gateway router.

This shows how to add agent detection and routing to the chat endpoint.
"""

import logging
import os
from typing import Optional

from gateway.agents import CodeIntelligenceAgent, WorkflowDetector
from gateway.llm.client import LLMClient

logger = logging.getLogger(__name__)


class ChatRouterWithAgent:
    """Example chat router with Code Intelligence Agent integration."""

    def __init__(self):
        # Initialize agent components
        self.llm_client = LLMClient()

        self.agent = CodeIntelligenceAgent(
            mcp_url=os.getenv("MCP_SERVER_URL", "http://mcp:8003"),
            crawler_url=os.getenv("CRAWLER_URL", "http://crawler:8001"),
            indexer_url=os.getenv("INDEXER_URL", "http://indexer:8002"),
            llm_client=self.llm_client,
            azure_devops_mcp_url=os.getenv(
                "AZURE_DEVOPS_MCP_URL", "http://azure-devops-mcp-server:8004"
            ),
        )

        self.detector = WorkflowDetector(
            mcp_url=os.getenv("MCP_SERVER_URL", "http://mcp:8003")
        )

    async def chat(self, query: str, conversation_id: str) -> dict:
        """
        Handle chat request with agent detection.

        Flow:
        1. Try to detect explicit agent invocation
        2. If detected, use agent (1-2 LLM calls)
        3. Otherwise, fall back to dynamic tool calling (5+ LLM calls)
        """

        # Try to detect explicit Code Intelligence Agent invocation
        workflow_request = self.detector.detect_workflow_invocation(query)

        if workflow_request:
            # Explicit agent invocation detected
            logger.info(
                f"Code Intelligence Agent invoked: workflow={workflow_request.workflow}, "
                f"files={len(workflow_request.target_files)}"
            )

            # Execute agent workflow
            result = await self.agent.execute_workflow(
                workflow=workflow_request.workflow,
                target_files=workflow_request.target_files,
                request=workflow_request.request,
                reference_files=workflow_request.reference_files,
                web_research=workflow_request.web_research,
            )

            # Check for errors
            if "error" in result:
                logger.error(f"Agent workflow failed: {result['error']}")
                return {
                    "error": result["error"],
                    "message": "Agent workflow failed. Try rephrasing your request.",
                }

            # Return agent result
            return {
                "response": result["result"],
                "mode": "agent",
                "workflow": workflow_request.workflow,
                "target_files": result["target_files"],
                "sources": result.get("sources", []),
                "context_used": result.get("context_used", {}),
                "llm_calls": 1,  # Agent typically uses 1-2 calls
            }

        else:
            # No explicit invocation, fall back to dynamic tool calling
            logger.info("Using dynamic tool calling (no agent invocation detected)")

            # Use existing dynamic chat completion
            result = await self._dynamic_chat_completion(query, conversation_id)

            return {
                "response": result["content"],
                "mode": "dynamic",
                "tool_calls": result.get("tool_calls_count", 0),
                "llm_calls": result.get("llm_calls_count", 0),
            }

    async def _dynamic_chat_completion(self, query: str, conversation_id: str) -> dict:
        """
        Existing dynamic tool calling implementation.

        This is your current chat completion logic with multi-round tool calling.
        """
        # Your existing implementation from gateway/routers/chat.py
        # This method handles the multi-round tool calling loop
        pass


# Integration into existing FastAPI router
# gateway/routers/chat.py

"""
Add this to your existing chat router:

from gateway.routers.chat_with_agent import ChatRouterWithAgent

# Initialize router with agent support
router_with_agent = ChatRouterWithAgent()

@router.post("/chat")
async def chat(request: ChatRequest):
    result = await router_with_agent.chat(
        query=request.query,
        conversation_id=request.conversation_id
    )

    # Add mode indicator to response
    if result.get("mode") == "agent":
        logger.info(
            f"Agent mode: {result['workflow']}, "
            f"{len(result['target_files'])} files, "
            f"{result['llm_calls']} LLM calls"
        )
    else:
        logger.info(
            f"Dynamic mode: {result['tool_calls']} tool calls, "
            f"{result['llm_calls']} LLM calls"
        )

    return result
"""


# Example usage patterns for testing

EXAMPLE_AGENT_QUERIES = [
    # Will trigger agent
    "run code analysis workflow on *.cpp files under /src/compute/",
    "invoke inspect agent on files suffixed with .json in /config/",
    "call generate workflow with template /templates/service.xml",
    # Will NOT trigger agent (uses dynamic)
    "explain the file /src/compute/service.cpp",
    "find bugs in the config files",
    "what do the .cpp files do?",
]


if __name__ == "__main__":
    import asyncio

    async def test():
        router = ChatRouterWithAgent()

        for query in EXAMPLE_AGENT_QUERIES:
            print(f"\nQuery: {query}")
            result = await router.chat(query, "test-123")
            print(f"Mode: {result.get('mode')}")
            if result.get("mode") == "agent":
                print(f"Workflow: {result.get('workflow')}")
                print(f"Files: {result.get('target_files')}")
            print(f"LLM calls: {result.get('llm_calls')}")

    asyncio.run(test())

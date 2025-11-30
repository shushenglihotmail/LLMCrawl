"""
Gateway Agents - Code Intelligence Agent for LLM-powered code analysis.

The agent gathers all context (files, Azure DevOps content, web crawl) in a single
round before calling the LLM, reducing costs by ~80% compared to multi-round tool calling.

Usage:
    POST /agent/chat - Execute chat with optional target files, reference files, and seed URLs
"""

from gateway.agents.agent_config import AgentConfig, convert_mcp_tool_to_openai
from gateway.agents.unified_workflow import WorkflowType

__all__ = [
    "AgentConfig",
    "convert_mcp_tool_to_openai",
    "WorkflowType",
]

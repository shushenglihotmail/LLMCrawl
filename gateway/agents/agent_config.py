"""
Agent configuration for Code Intelligence Agent.

Simple configuration holder for service URLs used by the agent router.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AgentConfig:
    """Configuration for Code Intelligence Agent services."""

    mcp_url: str
    crawler_url: str
    indexer_url: str
    azure_devops_mcp_url: Optional[str] = None


def convert_mcp_tool_to_openai(mcp_tool: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert MCP tool format to OpenAI function calling format.

    MCP format: {"name": "...", "description": "...", "inputSchema": {...}}
    OpenAI format: {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
    """
    return {
        "type": "function",
        "function": {
            "name": mcp_tool.get("name"),
            "description": mcp_tool.get("description"),
            "parameters": mcp_tool.get("inputSchema", {}),
        },
    }

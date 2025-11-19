"""
Gateway Agents - Specialized workflow agents for efficient LLM operations.

Agents orchestrate data gathering WITHOUT multiple LLM rounds, reducing costs by 80%.

Two invocation methods:

1. Template-based (recommended for clients):
   - GET /agent/templates → Discover workflows
   - GET /agent/templates/{workflow} → Get parameter schema
   - POST /agent/execute → Execute with filled template

2. Prompt-based (for advanced users):
   - "run code analysis workflow on *.cpp files under /src/"
   - Falls back to dynamic tool calling for non-explicit queries
"""

from gateway.agents.file_explanation_agent import CodeIntelligenceAgent
from gateway.agents.templates import (
    GenerateWorkflowRequest,
    InspectWorkflowRequest,
    UnderstandWorkflowRequest,
    get_all_templates,
    get_template,
)
from gateway.agents.workflow_detector import WorkflowDetector, WorkflowRequest

__all__ = [
    "CodeIntelligenceAgent",
    "WorkflowDetector",
    "WorkflowRequest",
    "UnderstandWorkflowRequest",
    "InspectWorkflowRequest",
    "GenerateWorkflowRequest",
    "get_all_templates",
    "get_template",
]

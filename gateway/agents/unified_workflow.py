"""
Unified workflow model for Code Intelligence Agent.

Simplified single workflow that handles all use cases:
- Reference file context (read directly from local filesystem)
- Web crawling for additional context
- Direct LLM interaction with user message
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class WorkflowType(str, Enum):
    """
    Workflow types that determine system behavior and available options.

    GENERAL_CHAT: Casual conversation with informational consultant.
        - System role: Informational consultant
        - Reference files: Disabled
        - Azure DevOps in expose_to_llm: Disabled
        - Use case: General questions, casual chat

    CODE_ANALYSIS: Deep code analysis with technical architect.
        - System role: Technical architect for code analysis, review, refactoring
        - All options available
        - Use case: Code review, refactoring, architecture analysis

    BUILD_SYSTEM_ANALYSIS: Metadata and build system analysis.
        - System role: Technical architect and expert build engineer
        - All options available
        - Use case: Build system, manifest, metadata analysis

    FILE_EXPLORER: DevOps and file assistant for browsing/searching files.
        - System role: DevOps and local file assistant/helper
        - All options available
        - Use case: Browse repos, search files by content/name/pattern
    """

    GENERAL_CHAT = "general_chat"
    CODE_ANALYSIS = "code_analysis"
    BUILD_SYSTEM_ANALYSIS = "build_system_analysis"
    FILE_EXPLORER = "file_explorer"


class UnifiedWorkflowRequest(BaseModel):
    """
    Unified workflow request combining all previous templates.

    Flow:
    1. Agent gathers context from reference_files (if provided) from local filesystem
    2. Agent crawls seed_urls (if provided) via crawler
    3. Agent combines all context with user_message and sends to LLM
    4. LLM can use exposed tools (if any) for additional operations

    Example:
    {
        "workflow": "code_analysis",
        "user_message": "Explain how Windows runlevels work",
        "reference_files": ["C:/docs/architecture.md"],  # Optional
        "seed_urls": ["https://www.osgwiki.com/wiki/Windows_Runlevels"],  # Optional
        "enable_embedding": false,  # Index crawled content
        "expose_to_llm": {
            "azure_devops_mcp": false,  # Expose Azure DevOps MCP tools to LLM
            "crawler": false  # Expose crawler tool to LLM
        },
        "model": "gpt-4",
        "conversation_id": "uuid-here",
        "crawl_depth": 1
    }
    """

    # Workflow type selection
    workflow: WorkflowType = Field(
        WorkflowType.GENERAL_CHAT,
        description="Workflow type that determines system behavior and available options",
    )

    # Required
    user_message: str = Field(..., description="User's question or request")

    # Optional context sources
    reference_files: Optional[List[str]] = Field(
        None, description="Local reference file paths for additional context"
    )

    seed_urls: Optional[List[str]] = Field(
        None, description="Web URLs to crawl for context"
    )

    # Control switches
    enable_embedding: bool = Field(
        False, description="Enable embedding/indexing for crawled content"
    )

    clear_history: bool = Field(
        False, description="Clear conversation history and start new conversation"
    )

    expose_to_llm: dict = Field(
        default_factory=lambda: {
            "azure_devops_mcp": False,
            "crawler": False,
        },
        description="Which tools to expose to LLM (doesn't restrict agent operations)",
    )

    # Standard chat parameters
    model: Optional[str] = Field(
        None, description="Model name to use (defaults to first model in LLM_MODELS)"
    )

    conversation_id: Optional[str] = Field(
        None, description="Conversation ID for context"
    )

    crawl_depth: int = Field(1, description="Depth for web crawling (1-5)")

    effort: Optional[str] = Field(
        None,
        description="Reasoning effort level for CLI models (low, medium, high, max/xhigh)",
    )


class UnifiedWorkflowResponse(BaseModel):
    """Response from unified workflow execution."""

    response: str = Field(..., description="LLM response")
    conversation_id: str = Field(..., description="Conversation ID")
    model: str = Field(..., description="Model used")
    tokens_used: Optional[int] = Field(None, description="Total tokens used")

    context_gathered: dict = Field(
        default_factory=dict, description="Summary of context gathered by agent"
    )

    saved_files: list = Field(
        default_factory=list,
        description="Files saved to disk by LLM during tool calling",
    )
    # Example: [
    #     {"filename": "easyBMT.ps1", "saved_path": "C:/output/easyBMT.ps1", "size": 4280}
    # ]

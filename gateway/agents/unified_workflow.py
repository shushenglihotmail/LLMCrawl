"""
Unified workflow model for Code Intelligence Agent.

Simplified single workflow that handles all use cases:
- Target file analysis (Azure DevOps MCP)
- Reference file context (Local MCP)
- Web crawling for additional context
- Direct LLM interaction with user message
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class UnifiedWorkflowRequest(BaseModel):
    """
    Unified workflow request combining all previous templates.

    Flow:
    1. Agent gathers context from target_paths (if provided) via Azure DevOps MCP
    2. Agent gathers context from reference_files (if provided) via Local MCP
    3. Agent crawls seed_urls (if provided) via crawler
    4. Agent optionally crawls web based on browse_web and user_message
    5. Agent combines all context with user_message and sends to LLM
    6. LLM can use exposed tools (if any) for additional operations

    Example:
    {
        "user_message": "Explain how Windows runlevels work",
        "target_paths": ["src/windows/runlevels/*.cpp"],  # Optional
        "reference_files": ["/docs/architecture.md"],  # Optional
        "seed_urls": ["https://www.osgwiki.com/wiki/Windows_Runlevels"],  # Optional
        "browse_web": false,  # Allow crawling beyond seed_urls
        "enable_embedding": false,  # Index crawled content
        "expose_to_llm": {
            "local_mcp": false,  # Expose local file MCP tools to LLM
            "azure_devops_mcp": false,  # Expose Azure DevOps MCP tools to LLM
            "crawler": false  # Expose crawler tool to LLM
        },
        "model": "gpt-4",
        "conversation_id": "uuid-here",
        "crawl_depth": 1,
        "max_tokens": 2000
    }
    """

    # Required
    user_message: str = Field(..., description="User's question or request")

    # Optional context sources
    target_paths: Optional[List[str]] = Field(
        None,
        description="Azure DevOps file paths to analyze (supports wildcards like *.cpp)",
    )

    reference_files: Optional[List[str]] = Field(
        None, description="Local reference file paths for additional context"
    )

    seed_urls: Optional[List[str]] = Field(
        None, description="Web URLs to crawl for context"
    )

    # Control switches
    browse_web: bool = Field(
        False,
        description="Allow crawling sites beyond seed_urls (applies to both agent and LLM)",
    )

    enable_embedding: bool = Field(
        False, description="Enable embedding/indexing for crawled content"
    )

    clear_history: bool = Field(
        False, description="Clear conversation history and start new conversation"
    )

    expose_to_llm: dict = Field(
        default_factory=lambda: {
            "local_mcp": False,
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

    max_tokens: int = Field(2000, description="Maximum response tokens")


class UnifiedWorkflowResponse(BaseModel):
    """Response from unified workflow execution."""

    response: str = Field(..., description="LLM response")
    conversation_id: str = Field(..., description="Conversation ID")
    model: str = Field(..., description="Model used")
    tokens_used: Optional[int] = Field(None, description="Total tokens used")

    context_gathered: dict = Field(
        default_factory=dict, description="Summary of context gathered by agent"
    )
    # Example: {
    #     "target_files": 5,
    #     "reference_files": 2,
    #     "crawled_urls": 3,
    #     "web_search_results": 10
    # }

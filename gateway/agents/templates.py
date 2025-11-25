"""
Workflow templates for Code Intelligence Agent.

Templates provide structured parameter input instead of parsing complex prompts.
Clients can:
1. GET /templates - List available templates
2. GET /templates/{workflow} - Get template for specific workflow
3. POST /agent/execute - Execute workflow with filled template
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PathItem(BaseModel):
    """Represents a file path (with wildcards) or folder path."""

    path: str = Field(
        ...,
        description="File path (supports wildcards like *.cpp, x*.json) or folder path",
    )
    is_folder: bool = Field(
        default=False,
        description="True if path is a folder, False if file/wildcard pattern",
    )
    include_subfolders: bool = Field(
        default=False,
        description="If is_folder=True, whether to include subfolders recursively",
    )


class WorkflowTemplate(BaseModel):
    """Base template for workflow execution."""

    workflow: Literal["understand", "inspect", "generate"]
    name: str
    description: str
    parameters: dict


class UnderstandWorkflowRequest(BaseModel):
    """
    Template for UNDERSTAND workflow - analyze and document files.

    Example:
    {
        "workflow": "understand",
        "target_files": [
            "/data/files/src/onecore/vm/compute/dll/ComputeServiceModule.cpp",
            "/data/files/src/onecore/vm/compute/dll/ComputeService.h"
        ],
        "request": "Explain how the vmcompute service initializes",
        "educational_files": ["/data/files/docs/HCS_GUIDE.md"],
        "web_crawl_urls": ["https://docs.microsoft.com/virtualization/windowscontainers/"]
    }
    """

    workflow: Literal["understand"] = "understand"

    # Optional: Files/folders to analyze
    target_paths: List[str] = Field(
        default_factory=list,
        description="Paths to analyze (optional). Use conventions: 'file.cpp'=file, 'folder\\'=folder, 'folder\\**'=recursive, '*.cpp'=wildcard",
        examples=[
            [
                "src/service/main.cpp",
                "src/utils/*.py",
                "src/models/",
                "src/core/**",
            ]
        ],
    )

    # Required: What to analyze
    request: str = Field(
        ...,
        description="What you want to understand about the files",
        examples=["Explain how the service initializes", "Document the API design"],
    )

    # Required: Model to use (from client selection)
    model: str = Field(
        ...,
        description="LLM model to use for analysis",
        examples=["gpt-4o", "gpt-5-chat", "claude-sonnet-4-5"],
    )

    # Optional: Educational/instruction files
    educational_files: Optional[List[str]] = Field(
        default=None,
        description="Optional instruction files or folders. Use same path conventions",
        examples=[
            [
                "docs/ARCHITECTURE.md",
                "examples/",
                "templates/**",
            ]
        ],
    )

    # Optional: Web crawl targets
    web_crawl_urls: Optional[List[str]] = Field(
        default=None,
        description="Optional URLs to crawl for additional context",
        examples=[["https://docs.microsoft.com/windows/win32/services/"]],
    )

    # Optional: Allow web search for additional context
    allow_web_search: bool = Field(
        default=False,
        description="Allow agent to crawl public internet for related information. If seed URLs provided, they are crawled with priority.",
    )


class InspectWorkflowRequest(BaseModel):
    """
    Template for INSPECT workflow - find bugs and issues.

    Example:
    {
        "workflow": "inspect",
        "target_files": ["/src/auth/handler.cpp"],
        "request": "Find security vulnerabilities and memory leaks",
        "educational_files": ["/docs/SECURITY_CHECKLIST.md"],
        "web_crawl_urls": ["https://owasp.org/www-project-top-ten/"]
    }
    """

    workflow: Literal["inspect"] = "inspect"

    # Optional: Files/folders to inspect
    target_paths: List[PathItem] = Field(
        default_factory=list,
        description="Files (with wildcards like *.cpp) or folders to inspect (optional)",
    )

    # Required: What to look for
    request: str = Field(
        ...,
        description="What issues to find",
        examples=[
            "Find security vulnerabilities",
            "Find memory leaks and resource issues",
            "Check for thread safety problems",
        ],
    )

    # Required: Model to use (from client selection)
    model: str = Field(
        ...,
        description="LLM model to use for analysis",
        examples=["gpt-4o", "gpt-5-chat", "claude-sonnet-4-5"],
    )

    # Optional: Guidelines/checklists
    educational_files: Optional[List[PathItem]] = Field(
        default=None,
        description="Optional security guidelines, coding standards, checklists",
        examples=[
            [
                {"path": "docs/SECURITY_GUIDELINES.md", "is_folder": False},
                {
                    "path": "docs/standards",
                    "is_folder": True,
                    "include_subfolders": False,
                },
            ]
        ],
    )

    # Optional: Web resources (CVE databases, OWASP, etc.)
    web_crawl_urls: Optional[List[str]] = Field(
        default=None,
        description="Optional security resources to reference",
        examples=[["https://cwe.mitre.org/", "https://owasp.org/"]],
    )

    # Optional: Control public internet crawling
    allow_web_search: bool = Field(
        default=False,
        description="Control public internet crawling. False (default): only crawl seed URLs if provided. True: allow public internet crawling (seed URLs have priority if provided).",
    )


class GenerateWorkflowRequest(BaseModel):
    """
    Template for GENERATE workflow - create new code from examples.

    Example:
    {
        "workflow": "generate",
        "target_files": [],
        "request": "Create a new file processing service",
        "educational_files": [
            "/templates/service_template.cpp",
            "/templates/service_template.h",
            "/docs/SERVICE_PATTERNS.md"
        ],
        "web_crawl_urls": null
    }
    """

    workflow: Literal["generate"] = "generate"

    # Optional for generate: Existing files for reference/context
    target_paths: List[PathItem] = Field(
        default_factory=list,
        description="Existing files or folders to use as reference/context",
    )

    # Required: What to generate
    request: str = Field(
        ...,
        description="What to generate and requirements",
        examples=[
            "Create a new REST API endpoint for user management",
            "Generate a Windows service for file processing",
        ],
    )

    # Required: Model to use (from client selection)
    model: str = Field(
        ...,
        description="LLM model to use for generation",
        examples=["gpt-4o", "gpt-5-chat", "claude-sonnet-4-5"],
    )

    # Required: Template/example files to learn from
    educational_files: List[PathItem] = Field(
        ...,
        description="Template files, examples, and style guides to follow",
        min_items=1,
        examples=[
            [
                {"path": "templates/service_template.cpp", "is_folder": False},
                {
                    "path": "examples/services",
                    "is_folder": True,
                    "include_subfolders": True,
                },
            ]
        ],
    )

    # Optional: Usually disabled for generation
    web_crawl_urls: Optional[List[str]] = Field(
        default=None,
        description="Usually not needed for generation (examples are sufficient)",
    )

    # Optional: Control public internet crawling
    allow_web_search: bool = Field(
        default=False,
        description="Control public internet crawling. False (default): only crawl seed URLs if provided. True: allow public internet crawling (seed URLs have priority if provided).",
    )


# Template definitions for GET /templates
WORKFLOW_TEMPLATES = {
    "understand": {
        "name": "Understand & Document",
        "description": "Analyze files and generate comprehensive documentation",
        "workflow": "understand",
        "parameters": {
            "target_files": {
                "type": "array",
                "items": {"type": "string"},
                "required": True,
                "description": "Files to analyze (supports wildcards)",
                "example": ["/src/compute/*.cpp"],
            },
            "request": {
                "type": "string",
                "required": True,
                "description": "What you want to understand",
                "example": "Explain service initialization flow",
            },
            "educational_files": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": "Instruction files with analysis tips",
                "example": ["/docs/ARCHITECTURE.md"],
            },
            "web_crawl_urls": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": "URLs to crawl for additional context",
                "example": ["https://docs.microsoft.com/windows/"],
            },
        },
        "example": {
            "workflow": "understand",
            "target_files": [
                "/data/files/src/onecore/vm/compute/dll/ComputeServiceModule.cpp"
            ],
            "request": "Explain how the vmcompute service initializes",
            "educational_files": ["/docs/HCS_GUIDE.md"],
            "web_crawl_urls": ["https://docs.microsoft.com/virtualization/"],
        },
    },
    "inspect": {
        "name": "Inspect & Analyze",
        "description": "Find bugs, security issues, and code quality problems",
        "workflow": "inspect",
        "parameters": {
            "target_files": {
                "type": "array",
                "items": {"type": "string"},
                "required": True,
                "description": "Files to inspect",
                "example": ["/src/auth/handler.cpp"],
            },
            "request": {
                "type": "string",
                "required": True,
                "description": "What issues to find",
                "example": "Find security vulnerabilities and memory leaks",
            },
            "educational_files": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": "Security guidelines, coding standards",
                "example": ["/docs/SECURITY_GUIDELINES.md"],
            },
            "web_crawl_urls": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": "Security resources (OWASP, CVE, etc.)",
                "example": ["https://owasp.org/www-project-top-ten/"],
            },
        },
        "example": {
            "workflow": "inspect",
            "target_files": ["/src/auth/handler.cpp"],
            "request": "Find security vulnerabilities",
            "educational_files": ["/docs/SECURITY_CHECKLIST.md"],
            "web_crawl_urls": ["https://owasp.org/"],
        },
    },
    "generate": {
        "name": "Generate from Examples",
        "description": "Create new code based on templates and examples",
        "workflow": "generate",
        "parameters": {
            "target_files": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": "Usually empty for generation",
                "example": [],
            },
            "request": {
                "type": "string",
                "required": True,
                "description": "What to generate",
                "example": "Create a new REST API endpoint for user management",
            },
            "educational_files": {
                "type": "array",
                "items": {"type": "string"},
                "required": True,
                "description": "Templates and examples to learn from",
                "example": ["/templates/api_endpoint.py", "/docs/CODING_STANDARDS.md"],
            },
            "web_crawl_urls": {
                "type": "array",
                "items": {"type": "string"},
                "required": False,
                "description": "Usually not needed (examples sufficient)",
                "example": None,
            },
        },
        "example": {
            "workflow": "generate",
            "target_files": [],
            "request": "Create a new file processing service",
            "educational_files": [
                "/templates/service_template.cpp",
                "/docs/SERVICE_PATTERNS.md",
            ],
            "web_crawl_urls": None,
        },
    },
}


def get_all_templates() -> dict:
    """Get all available workflow templates."""
    return {"templates": WORKFLOW_TEMPLATES, "count": len(WORKFLOW_TEMPLATES)}


def get_template(workflow: str) -> Optional[dict]:
    """Get template for specific workflow."""
    return WORKFLOW_TEMPLATES.get(workflow)

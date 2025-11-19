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

    # Required: Files to analyze
    target_files: List[str] = Field(
        ...,
        description="List of file paths to analyze. Can use wildcards like /src/**/*.cpp",
        min_items=1,
        examples=[
            [
                "/data/files/src/onecore/vm/compute/dll/ComputeServiceModule.cpp",
                "/data/files/src/onecore/vm/compute/dll/ComputeService.h",
            ]
        ],
    )

    # Required: What to analyze
    request: str = Field(
        ...,
        description="What you want to understand about the files",
        examples=["Explain how the service initializes", "Document the API design"],
    )

    # Optional: Educational/instruction files
    educational_files: Optional[List[str]] = Field(
        default=None,
        description="Optional instruction files with tips for analysis",
        examples=[["/docs/ARCHITECTURE.md", "/docs/CODING_PATTERNS.md"]],
    )

    # Optional: Web crawl targets
    web_crawl_urls: Optional[List[str]] = Field(
        default=None,
        description="Optional URLs to crawl for additional context",
        examples=[["https://docs.microsoft.com/windows/win32/services/"]],
    )

    # Optional: Model configuration
    planning_model: str = Field(
        default="gpt-4o-mini", description="Model for planning (cheap/fast)"
    )
    execution_model: str = Field(
        default="gpt-4o", description="Model for analysis (main)"
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

    # Required: Files to inspect
    target_files: List[str] = Field(
        ..., description="List of file paths to inspect", min_items=1
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

    # Optional: Guidelines/checklists
    educational_files: Optional[List[str]] = Field(
        default=None,
        description="Optional security guidelines, coding standards, checklists",
        examples=[["/docs/SECURITY_GUIDELINES.md", "/docs/CODING_STANDARDS.md"]],
    )

    # Optional: Web resources (CVE databases, OWASP, etc.)
    web_crawl_urls: Optional[List[str]] = Field(
        default=None,
        description="Optional security resources to reference",
        examples=[["https://cwe.mitre.org/", "https://owasp.org/"]],
    )

    planning_model: str = Field(default="gpt-4o-mini")
    execution_model: str = Field(default="gpt-4o")


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

    # Optional for generate: No target files needed
    target_files: List[str] = Field(
        default_factory=list, description="Usually empty for generation workflow"
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

    # Required: Template/example files to learn from
    educational_files: List[str] = Field(
        ...,
        description="Template files, examples, and style guides to follow",
        min_items=1,
        examples=[
            [
                "/templates/service_template.cpp",
                "/templates/service_template.h",
                "/docs/CODING_STANDARDS.md",
            ]
        ],
    )

    # Optional: Usually disabled for generation
    web_crawl_urls: Optional[List[str]] = Field(
        default=None,
        description="Usually not needed for generation (examples are sufficient)",
    )

    planning_model: str = Field(default="gpt-4o-mini")
    execution_model: str = Field(default="gpt-4o")


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

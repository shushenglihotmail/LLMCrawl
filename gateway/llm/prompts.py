"""
System and developer prompts for the Web RAG system.
Contains tool schemas, routing logic, and few-shot examples.

Uses Pydantic for type-safe tool definitions that can be converted to
different LLM formats (OpenAI, Claude, Gemini).
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from gateway.utils.tool_constants import TOOL_CRAWL_AND_REFRESH

# =============================================================================
# Pydantic Tool Input Models
# =============================================================================


class CrawlAndRefreshInput(BaseModel):
    """Input schema for the crawl_and_refresh tool.

    This model defines the parameters for web crawling and content refresh.
    Use .to_openai_tool() or other conversion methods for LLM-specific formats.
    """

    query: str = Field(description="User topic or question")
    seed_urls: Optional[List[str]] = Field(
        default=None, description="Optional seed URLs or domains to prefer"
    )
    freshness_days: int = Field(
        default=7, ge=1, description="How recent the content should be (in days)"
    )
    depth: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Crawl depth (1 = direct pages only, max 5). Keep low to avoid query overhead.",
    )


# =============================================================================
# Tool Schema Conversion Utilities
# =============================================================================


class ToolSchemaConverter:
    """Utility class to convert Pydantic models to various LLM tool formats."""

    @staticmethod
    def to_openai_tool(
        model: type[BaseModel], name: str, description: str
    ) -> Dict[str, Any]:
        """Convert a Pydantic model to OpenAI function calling format.

        Args:
            model: The Pydantic model class defining the input schema
            name: The function name to use
            description: Description of what the tool does

        Returns:
            OpenAI-compatible tool schema dict
        """
        schema = model.model_json_schema()

        # Extract properties and required fields from Pydantic schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Clean up Pydantic-specific fields for OpenAI compatibility
        cleaned_properties = {}
        for prop_name, prop_schema in properties.items():
            cleaned_prop = {}

            # Map Pydantic types to JSON Schema types
            if "anyOf" in prop_schema:
                # Handle Optional types - take the non-null type
                for option in prop_schema["anyOf"]:
                    if option.get("type") != "null":
                        cleaned_prop = option.copy()
                        break
            else:
                cleaned_prop = prop_schema.copy()

            # Remove Pydantic-specific keys
            cleaned_prop.pop("title", None)

            # Convert 'exclusiveMinimum' to 'minimum' for broader compatibility
            if "exclusiveMinimum" in cleaned_prop:
                cleaned_prop["minimum"] = cleaned_prop.pop("exclusiveMinimum") + 1

            cleaned_properties[prop_name] = cleaned_prop

        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": cleaned_properties,
                    "required": required,
                },
            },
        }

    @staticmethod
    def to_claude_tool(
        model: type[BaseModel], name: str, description: str
    ) -> Dict[str, Any]:
        """Convert a Pydantic model to Anthropic Claude tool format.

        Claude uses a similar but slightly different format from OpenAI.
        """
        schema = model.model_json_schema()

        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Clean up properties for Claude
        cleaned_properties = {}
        for prop_name, prop_schema in properties.items():
            cleaned_prop = {}

            if "anyOf" in prop_schema:
                for option in prop_schema["anyOf"]:
                    if option.get("type") != "null":
                        cleaned_prop = option.copy()
                        break
            else:
                cleaned_prop = prop_schema.copy()

            cleaned_prop.pop("title", None)

            if "exclusiveMinimum" in cleaned_prop:
                cleaned_prop["minimum"] = cleaned_prop.pop("exclusiveMinimum") + 1

            cleaned_properties[prop_name] = cleaned_prop

        return {
            "name": name,
            "description": description,
            "input_schema": {
                "type": "object",
                "properties": cleaned_properties,
                "required": required,
            },
        }

    @staticmethod
    def to_gemini_tool(
        model: type[BaseModel], name: str, description: str
    ) -> Dict[str, Any]:
        """Convert a Pydantic model to Google Gemini tool format.

        Gemini uses function declarations within a tools array.
        """
        schema = model.model_json_schema()

        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Clean and convert properties for Gemini
        cleaned_properties = {}
        for prop_name, prop_schema in properties.items():
            cleaned_prop = {}

            if "anyOf" in prop_schema:
                for option in prop_schema["anyOf"]:
                    if option.get("type") != "null":
                        cleaned_prop = option.copy()
                        break
            else:
                cleaned_prop = prop_schema.copy()

            cleaned_prop.pop("title", None)

            # Gemini uses STRING, INTEGER, ARRAY, etc.
            type_mapping = {
                "string": "STRING",
                "integer": "INTEGER",
                "number": "NUMBER",
                "boolean": "BOOLEAN",
                "array": "ARRAY",
                "object": "OBJECT",
            }

            if "type" in cleaned_prop:
                cleaned_prop["type"] = type_mapping.get(
                    cleaned_prop["type"], cleaned_prop["type"].upper()
                )

            if "items" in cleaned_prop and "type" in cleaned_prop["items"]:
                cleaned_prop["items"]["type"] = type_mapping.get(
                    cleaned_prop["items"]["type"], cleaned_prop["items"]["type"].upper()
                )

            if "exclusiveMinimum" in cleaned_prop:
                cleaned_prop["minimum"] = cleaned_prop.pop("exclusiveMinimum") + 1

            cleaned_properties[prop_name] = cleaned_prop

        return {
            "function_declarations": [
                {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "OBJECT",
                        "properties": cleaned_properties,
                        "required": required,
                    },
                }
            ]
        }


# =============================================================================
# Pre-built Tool Schemas (OpenAI format for backward compatibility)
# =============================================================================


# Tool schema that gets registered with the LLM (OpenAI format)
CRAWL_AND_REFRESH_TOOL = ToolSchemaConverter.to_openai_tool(
    model=CrawlAndRefreshInput,
    name=TOOL_CRAWL_AND_REFRESH,
    description="Search & crawl the web for up-to-date info; clean, index, and return fresh sources for answering with citations.",
)

# Claude format (for future use)
CRAWL_AND_REFRESH_TOOL_CLAUDE = ToolSchemaConverter.to_claude_tool(
    model=CrawlAndRefreshInput,
    name=TOOL_CRAWL_AND_REFRESH,
    description="Search & crawl the web for up-to-date info; clean, index, and return fresh sources for answering with citations.",
)

# Gemini format (for future use)
CRAWL_AND_REFRESH_TOOL_GEMINI = ToolSchemaConverter.to_gemini_tool(
    model=CrawlAndRefreshInput,
    name=TOOL_CRAWL_AND_REFRESH,
    description="Search & crawl the web for up-to-date info; clean, index, and return fresh sources for answering with citations.",
)


# =============================================================================
# Dynamic Tool Builders
# =============================================================================


def build_crawler_tool_with_seed_urls(
    seed_urls: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Build crawler tool schema with optional seed URLs included in the description.

    When seed_urls are provided, the tool description tells the LLM to prioritize
    crawling these URLs first for relevant information.

    Args:
        seed_urls: Optional list of URLs the user wants the LLM to prioritize

    Returns:
        OpenAI-compatible tool schema dict with dynamic description
    """
    base_description = (
        "Search & crawl the web for up-to-date info; clean, index, and return "
        "fresh sources for answering with citations. "
        "**IMPORTANT**: Keep depth low (1-2 recommended, max 5) to avoid high query overhead."
    )

    if seed_urls:
        # Build a description that tells LLM about the priority URLs
        urls_list = "\n".join(
            f"  - {url}" for url in seed_urls[:10]
        )  # Limit to 10 URLs
        description = (
            f"{base_description}\n\n"
            f"**PRIORITY SEED URLs** (user-provided - crawl these FIRST):\n{urls_list}\n\n"
            f"When calling this tool, include these seed_urls to prioritize crawling them. "
            f"These URLs are trusted sources the user wants you to search for information."
        )
    else:
        description = base_description

    return ToolSchemaConverter.to_openai_tool(
        model=CrawlAndRefreshInput,
        name=TOOL_CRAWL_AND_REFRESH,
        description=description,
    )

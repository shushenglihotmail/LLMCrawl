"""
Tool name constants and default limits.

Centralizes all tool names to avoid typos and ensure consistency
across the codebase (tool handlers, limit settings, tool descriptions).
"""

# =============================================================================
# Azure DevOps MCP Tools
# =============================================================================
TOOL_AZURE_DEVOPS_SEARCH_CODE = "search_azure_devops_code"
TOOL_AZURE_DEVOPS_GET_FILE = "get_azure_devops_file"

AZURE_DEVOPS_TOOLS = [
    TOOL_AZURE_DEVOPS_SEARCH_CODE,
    TOOL_AZURE_DEVOPS_GET_FILE,
]

# =============================================================================
# Crawler Tool
# =============================================================================
TOOL_CRAWL_AND_REFRESH = "crawl_and_refresh"

# =============================================================================
# Local MCP Tools
# =============================================================================
TOOL_READ_LOCAL_FILE = "read_local_file"
TOOL_LIST_FILES = "list_files"
TOOL_SEARCH_FILE_CONTENT = "search_file_content"
TOOL_INDEX_FILES = "index_files"

LOCAL_MCP_TOOLS = [
    TOOL_READ_LOCAL_FILE,
    TOOL_LIST_FILES,
    TOOL_SEARCH_FILE_CONTENT,
    TOOL_INDEX_FILES,
]

# =============================================================================
# Windows Composition Database Tool
# =============================================================================
TOOL_QUERY_COMPOSITION_DB = "query_composition_db"

# =============================================================================
# Default Tool Round Limits
# =============================================================================
# -1 means unlimited
DEFAULT_TOOL_LIMITS = {
    # Azure DevOps MCP tools - 30 calls
    TOOL_AZURE_DEVOPS_SEARCH_CODE: 30,
    TOOL_AZURE_DEVOPS_GET_FILE: 30,
    # Crawler tool - 20 calls
    TOOL_CRAWL_AND_REFRESH: 20,
    # Local MCP tools - 50 calls
    TOOL_READ_LOCAL_FILE: 50,
    TOOL_LIST_FILES: 50,
    TOOL_SEARCH_FILE_CONTENT: 50,
    TOOL_INDEX_FILES: 50,
    # WCD tool - unlimited
    TOOL_QUERY_COMPOSITION_DB: -1,
}

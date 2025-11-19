"""
Workflow detection for Code Intelligence Agent.

Detects explicit invocations like:
- "run code analysis workflow on *.cpp files under /src/compute/"
- "invoke inspect agent on files with .json suffix in /config/"
- "call understand workflow for .man files under /docs/"
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

WorkflowType = Literal["understand", "inspect", "generate"]


class WorkflowRequest:
    """Parsed workflow request with all parameters."""

    def __init__(
        self,
        workflow: WorkflowType,
        target_files: List[str],
        request: str,
        reference_files: Optional[List[str]] = None,
        web_research: bool = True,
    ):
        self.workflow = workflow
        self.target_files = target_files
        self.request = request
        self.reference_files = reference_files or []
        self.web_research = web_research


class WorkflowDetector:
    """Detects and parses Code Intelligence Agent workflow invocations."""

    # Workflow keywords
    WORKFLOW_KEYWORDS = {
        "understand": [
            "understand",
            "explain",
            "document",
            "summarize",
            "describe",
            "what does",
            "how does",
        ],
        "inspect": [
            "inspect",
            "find issues",
            "find bugs",
            "analyze issues",
            "check for",
            "review",
            "audit",
            "security",
            "vulnerabilities",
        ],
        "generate": [
            "generate",
            "create",
            "build",
            "make",
            "write",
            "produce",
            "based on",
            "from template",
        ],
    }

    # Invocation triggers
    INVOCATION_PATTERNS = [
        r"(?:run|call|invoke|execute|start)\s+(?:code\s+)?(?:analysis|intelligence)?\s*(?:workflow|agent)",
        r"(?:use|apply)\s+(?:the\s+)?(?:code\s+)?(?:analysis|intelligence)\s+(?:workflow|agent)",
        r"(?:do|perform)\s+(?:a\s+)?code\s+(?:analysis|inspection|review)",
    ]

    def __init__(self, mcp_url: str):
        """
        Initialize detector.

        Args:
            mcp_url: MCP server URL for file listing
        """
        self.mcp_url = mcp_url

    def detect_workflow_invocation(self, query: str) -> Optional[WorkflowRequest]:
        """
        Detect if query is an explicit Code Intelligence Agent invocation.

        Examples:
        - "run code analysis workflow on *.cpp files under /src/compute/"
        - "invoke inspect agent on files with .json suffix in /config/"
        - "call understand workflow for .man files under /docs/"
        - "execute generate agent with template files *.xml"

        Returns:
            WorkflowRequest if detected, None otherwise
        """
        query_lower = query.lower()

        # Check for explicit invocation pattern
        is_invocation = any(
            re.search(pattern, query_lower) for pattern in self.INVOCATION_PATTERNS
        )

        if not is_invocation:
            return None

        logger.info(f"Detected code intelligence agent invocation: {query}")

        # Determine workflow type
        workflow = self._detect_workflow_type(query_lower)
        if not workflow:
            logger.warning("Could not determine workflow type from query")
            return None

        # Extract file patterns
        file_patterns = self._extract_file_patterns(query)
        if not file_patterns:
            logger.warning("Could not extract file patterns from query")
            return None

        logger.info(f"Detected workflow: {workflow}, patterns: {file_patterns}")

        # Resolve actual file paths
        target_files = self._resolve_file_paths(file_patterns)
        if not target_files:
            logger.warning(f"No files found matching patterns: {file_patterns}")
            return None

        logger.info(f"Resolved {len(target_files)} target files")

        # Extract reference files (optional)
        reference_files = self._extract_reference_files(query)

        # Extract web research preference
        web_research = self._should_do_web_research(query)

        # Build clean request (remove invocation boilerplate)
        clean_request = self._clean_request(query, workflow)

        return WorkflowRequest(
            workflow=workflow,
            target_files=target_files,
            request=clean_request,
            reference_files=reference_files,
            web_research=web_research,
        )

    def _detect_workflow_type(self, query_lower: str) -> Optional[WorkflowType]:
        """Detect workflow type from query."""

        # Check for explicit workflow name
        if "understand" in query_lower or "explain" in query_lower:
            return "understand"
        if "inspect" in query_lower or "find issues" in query_lower:
            return "inspect"
        if "generate" in query_lower or "create" in query_lower:
            return "generate"

        # Check workflow keywords
        for workflow, keywords in self.WORKFLOW_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                return workflow

        return None

    def _extract_file_patterns(self, query: str) -> List[Dict[str, str]]:
        """
        Extract file patterns from query.

        Returns list of dicts with:
        - pattern: File pattern (*.cpp, *.json, etc.)
        - directory: Directory path (/src/compute/, /config/, etc.)
        """
        patterns = []

        # Pattern 1: "*.ext files under /path/"
        matches = re.finditer(
            r"(?:\*\.(\w+)|files?\s+(?:with\s+)?(?:suffix(?:ed)?|extension)\s+\.(\w+))"
            r".*?"
            r"(?:under|in|at|from)\s+([\w/\\.-]+)",
            query,
            re.IGNORECASE,
        )
        for match in matches:
            ext = match.group(1) or match.group(2)
            directory = match.group(3)
            patterns.append({"pattern": f"*.{ext}", "directory": directory})

        # Pattern 2: "/path/*.ext"
        matches = re.finditer(r"([\w/\\.-]+/\*\.(\w+))", query)
        for match in matches:
            full_pattern = match.group(1)
            directory = str(Path(full_pattern).parent)
            ext = match.group(2)
            patterns.append({"pattern": f"*.{ext}", "directory": directory})

        # Pattern 3: "on file(s) /path/file.ext"
        matches = re.finditer(
            r"(?:on|for)\s+files?\s+([\w/\\.-]+\.(\w+))", query, re.IGNORECASE
        )
        for match in matches:
            file_path = match.group(1)
            patterns.append({"pattern": file_path, "directory": None})

        # Pattern 4: "files suffixed with .ext" (no directory)
        matches = re.finditer(
            r"files?\s+(?:with\s+)?suffix(?:ed)?\s+(?:with\s+)?\.(\w+)",
            query,
            re.IGNORECASE,
        )
        for match in matches:
            ext = match.group(1)
            # No directory specified, will need to search workspace root
            patterns.append({"pattern": f"*.{ext}", "directory": "/"})

        logger.info(f"Extracted file patterns: {patterns}")
        return patterns

    def _resolve_file_paths(self, file_patterns: List[Dict[str, str]]) -> List[str]:
        """
        Resolve file patterns to actual file paths using MCP server.

        Args:
            file_patterns: List of pattern dicts from _extract_file_patterns

        Returns:
            List of resolved file paths
        """
        import asyncio

        import httpx

        resolved_files = []

        async def resolve():
            async with httpx.AsyncClient(timeout=30.0) as client:
                for pattern_info in file_patterns:
                    pattern = pattern_info["pattern"]
                    directory = pattern_info.get("directory")

                    # If pattern is a specific file (no wildcards)
                    if "*" not in pattern:
                        resolved_files.append(pattern)
                        continue

                    # Build search path
                    if directory:
                        search_path = f"{directory.rstrip('/')}/{pattern}"
                    else:
                        search_path = pattern

                    try:
                        # Use MCP list_files to find matching files
                        response = await client.post(
                            f"{self.mcp_url}/invoke",
                            json={
                                "tool_name": "list_files",
                                "arguments": {"directory": directory or "/"},
                            },
                        )
                        response.raise_for_status()
                        result = response.json()

                        if result.get("success"):
                            files = result["result"].get("files", [])

                            # Filter files by extension
                            ext = pattern.replace("*.", "")
                            matching_files = [
                                f["path"]
                                for f in files
                                if f["path"].endswith(f".{ext}")
                            ]

                            resolved_files.extend(matching_files)
                            logger.info(
                                f"Pattern {search_path} matched {len(matching_files)} files"
                            )

                    except Exception as e:
                        logger.error(f"Failed to resolve pattern {search_path}: {e}")

        # Run async resolution
        asyncio.create_task(resolve())
        asyncio.get_event_loop().run_until_complete(resolve())

        return list(set(resolved_files))  # Deduplicate

    def _extract_reference_files(self, query: str) -> List[str]:
        """
        Extract reference files from query.

        Looks for patterns like:
        - "with reference files /path/file1, /path/file2"
        - "using template /path/template.xml"
        - "based on /path/example.cpp"
        """
        reference_files = []

        # Pattern: "with reference files ..."
        matches = re.finditer(
            r"(?:with\s+)?(?:reference|template|example|guide)\s+files?\s+([\w/\\.,\s-]+)",
            query,
            re.IGNORECASE,
        )
        for match in matches:
            files_str = match.group(1)
            # Split by comma or space
            files = re.findall(r"[\w/\\.-]+", files_str)
            reference_files.extend(files)

        # Pattern: "based on /path/file"
        matches = re.finditer(r"based\s+on\s+([\w/\\.-]+)", query, re.IGNORECASE)
        for match in matches:
            reference_files.append(match.group(1))

        logger.info(f"Extracted reference files: {reference_files}")
        return reference_files

    def _should_do_web_research(self, query: str) -> bool:
        """Determine if web research should be performed."""

        query_lower = query.lower()

        # Explicit disable
        if any(
            phrase in query_lower
            for phrase in ["no web", "without web", "skip web", "local only"]
        ):
            return False

        # Explicit enable
        if any(
            phrase in query_lower
            for phrase in ["with web", "include web", "search web", "fetch docs"]
        ):
            return True

        # Default: enable for understand/inspect, disable for generate
        if "generate" in query_lower or "create" in query_lower:
            return False

        return True

    def _clean_request(self, query: str, workflow: WorkflowType) -> str:
        """
        Remove invocation boilerplate and return clean request.

        Examples:
        "run code analysis on *.cpp under /src/ and explain initialization"
        → "explain initialization"

        "invoke inspect agent on *.json files to find schema issues"
        → "find schema issues"
        """

        # Remove invocation patterns
        cleaned = query
        for pattern in self.INVOCATION_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Remove file pattern references
        cleaned = re.sub(
            r"\*\.\w+\s+files?(?:\s+(?:under|in|at|from)\s+[\w/\\.-]+)?",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"files?\s+(?:with\s+)?suffix(?:ed)?\s+(?:with\s+)?\.(\w+)",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"(?:under|in|at|from)\s+[\w/\\.-]+", "", cleaned, flags=re.IGNORECASE
        )

        # Remove reference file mentions
        cleaned = re.sub(
            r"(?:with\s+)?(?:reference|template|example|guide)\s+files?\s+[\w/\\.,\s-]+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        # Remove web research mentions
        cleaned = re.sub(
            r"(?:with|without|no|skip|include)\s+web(?:\s+research)?",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        # Clean up extra whitespace and "on", "to", "and"
        cleaned = re.sub(r"\s+(?:on|to|and|for)\s+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # If nothing left, provide default request
        if not cleaned or len(cleaned) < 10:
            default_requests = {
                "understand": "Analyze and document these files",
                "inspect": "Find potential issues and bugs",
                "generate": "Generate code following these examples",
            }
            cleaned = default_requests.get(workflow, "Analyze these files")

        logger.info(f"Cleaned request: {cleaned}")
        return cleaned


# Example usage
if __name__ == "__main__":
    detector = WorkflowDetector(mcp_url="http://localhost:8003")

    # Test queries
    test_queries = [
        "run code analysis workflow on *.cpp files under /src/compute/",
        "invoke inspect agent on files suffixed with .json in /config/ to find schema issues",
        "call understand workflow for .man files under /docs/ and explain service registration",
        "execute generate agent with template files /templates/service.xml, /templates/config.json",
        "run inspect on /src/auth/handler.cpp for security vulnerabilities",
        "use code intelligence agent on *.py files under /gateway/ without web research",
    ]

    for query in test_queries:
        print(f"\nQuery: {query}")
        request = detector.detect_workflow_invocation(query)
        if request:
            print(f"  Workflow: {request.workflow}")
            print(f"  Target files: {request.target_files}")
            print(f"  Request: {request.request}")
            print(f"  Reference files: {request.reference_files}")
            print(f"  Web research: {request.web_research}")
        else:
            print("  No workflow detected")

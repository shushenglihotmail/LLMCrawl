"""
Code Intelligence Agent - Specialized workflow for code/file operations.

Three main workflows:
1. UNDERSTAND & DOCUMENT: Analyze files/folders → Generate summaries/documentation
2. INSPECT & ANALYZE: Find bugs, style issues, security vulnerabilities, code smells
3. GENERATE FROM EXAMPLES: Learn patterns from existing code → Create new files

This agent orchestrates data gathering WITHOUT multiple LLM rounds:
- Reads target files (code, metadata, config)
- Reads educational/reference files (guides, templates, examples)
- Optionally crawls web documentation
- Sends everything to LLM in ONE call

Cost: 1-2 LLM calls (vs 5+ with dynamic tool calling)
"""

import json
import logging
import os
from typing import Any, Dict, List, Literal, Optional

import httpx

from gateway.routers.chat import convert_mcp_tool_to_openai

logger = logging.getLogger(__name__)

WorkflowType = Literal["understand", "inspect", "generate"]


def estimate_tokens(text: str) -> int:
    """Estimate token count (rough approximation: 1 token ≈ 4 characters)."""
    return len(text) // 4


class CodeIntelligenceAgent:
    """Agent for code understanding, inspection, and generation with context gathering."""

    def __init__(
        self,
        mcp_url: str,
        crawler_url: str,
        indexer_url: str,
        llm_client,
        azure_devops_mcp_url: Optional[str] = None,
    ):
        self.mcp_url = mcp_url
        self.azure_devops_mcp_url = azure_devops_mcp_url
        self.crawler_url = crawler_url
        self.indexer_url = indexer_url
        self.llm_client = llm_client
        self._mcp_tools_cache: Optional[List[Dict[str, Any]]] = None
        self._azure_devops_tools_cache: Optional[List[Dict[str, Any]]] = None

    async def _get_mcp_tools(self) -> List[Dict[str, Any]]:
        """Fetch MCP tools from the MCP server and convert to OpenAI format."""
        if self._mcp_tools_cache is not None:
            return self._mcp_tools_cache

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.mcp_url}/tools")
                response.raise_for_status()
                data = response.json()
                mcp_tools = data.get("tools", [])
                self._mcp_tools_cache = [
                    convert_mcp_tool_to_openai(tool) for tool in mcp_tools
                ]
                logger.info(f"Loaded {len(self._mcp_tools_cache)} MCP tools")
                return self._mcp_tools_cache
        except Exception as e:
            logger.warning(f"Failed to load MCP tools: {e}")
            return []

    async def _get_azure_devops_tools(self) -> List[Dict[str, Any]]:
        """Fetch tools from Azure DevOps MCP server and convert to OpenAI format."""
        if not self.azure_devops_mcp_url:
            return []

        if self._azure_devops_tools_cache is not None:
            return self._azure_devops_tools_cache

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.azure_devops_mcp_url}/tools")
                response.raise_for_status()
                data = response.json()
                mcp_tools = data.get("tools", [])
                self._azure_devops_tools_cache = [
                    convert_mcp_tool_to_openai(tool) for tool in mcp_tools
                ]
                logger.info(
                    f"Loaded {len(self._azure_devops_tools_cache)} Azure DevOps MCP tools"
                )
                return self._azure_devops_tools_cache
        except Exception as e:
            logger.warning(f"Failed to load Azure DevOps MCP tools: {e}")
            return []

    async def _handle_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a tool call from the LLM."""
        tool_name = tool_call["function"]["name"]
        arguments = json.loads(tool_call["function"]["arguments"])

        logger.info(f"Handling tool call: {tool_name}")
        logger.debug(f"Tool arguments: {arguments}")

        try:
            # Determine which MCP server to call
            azure_devops_tools = [
                "search_azure_devops_code",
                "search_azure_devops_files",
                "get_azure_devops_file",
            ]

            if tool_name in azure_devops_tools:
                mcp_url = self.azure_devops_mcp_url
            else:
                mcp_url = self.mcp_url

            if not mcp_url:
                return {"error": f"MCP server not configured for tool: {tool_name}"}

            # Call MCP server
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{mcp_url}/invoke",
                    json={"tool_name": tool_name, "arguments": arguments},
                )
                response.raise_for_status()
                result = response.json()

            logger.info(f"Tool call {tool_name} succeeded")
            return result

        except Exception as e:
            logger.error(f"Tool call {tool_name} failed: {e}")
            return {"error": str(e)}

    async def execute_workflow(
        self,
        workflow: WorkflowType,
        target_files: List[str],
        request: str,
        model: str,
        reference_files: Optional[List[str]] = None,
        seed_urls: Optional[List[str]] = None,
        allow_web_search: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a code intelligence workflow.

        Args:
            workflow: Type of workflow ("understand", "inspect", "generate")
            target_files: Primary files to operate on
            request: User's specific request/instruction
            model: LLM model to use (from client selection)
            reference_files: Optional reference files (guides, templates, examples)
            seed_urls: Optional URLs to crawl for additional context (crawled with priority)
            allow_web_search: Allow agent to crawl public internet for related information

        Returns:
            Result with content and sources
        """
        logger.info(f"Starting {workflow} workflow for {len(target_files)} files")
        logger.info(f"Using model: {model}")

        try:
            # Step 1: Read target files (expand folders to files if needed)
            target_contents = []
            logger.info(f"Processing {len(target_files)} target file paths")

            for file_path in target_files:
                logger.info(f"Processing path: {file_path}")

                # Check if it's a folder - if so, list files in it
                if not file_path or "/" not in file_path and "\\" not in file_path:
                    # Could be folder without path separator
                    logger.debug(
                        f"Path has no separator, trying as folder: {file_path}"
                    )
                    files_in_folder = await self._list_files(file_path)
                    if files_in_folder:
                        logger.info(
                            f"Folder detected: {file_path}, found {len(files_in_folder)} files"
                        )
                        for file_info in files_in_folder[
                            :10
                        ]:  # Limit to first 10 files
                            content = await self._read_file(file_info["path"])
                            if content:
                                target_contents.append(
                                    {"file": file_info["path"], "content": content}
                                )
                    else:
                        # Try as file
                        logger.debug(f"Not a folder, trying as file: {file_path}")
                        content = await self._read_file(file_path)
                        if content:
                            target_contents.append(
                                {"file": file_path, "content": content}
                            )
                        else:
                            logger.warning(f"Could not read file: {file_path}")
                else:
                    # Has path separator, treat as file first
                    logger.debug(f"Path has separator, trying as file: {file_path}")
                    content = await self._read_file(file_path)
                    if content:
                        target_contents.append({"file": file_path, "content": content})
                        logger.info(f"Successfully added file: {file_path}")
                    else:
                        # Maybe it's a folder path?
                        logger.debug(f"Failed as file, trying as folder: {file_path}")
                        files_in_folder = await self._list_files(file_path)
                        if files_in_folder:
                            logger.info(
                                f"Folder detected: {file_path}, found {len(files_in_folder)} files"
                            )
                            for file_info in files_in_folder[
                                :10
                            ]:  # Limit to first 10 files
                                content = await self._read_file(file_info["path"])
                                if content:
                                    target_contents.append(
                                        {"file": file_info["path"], "content": content}
                                    )
                        else:
                            logger.warning(
                                f"Could not read file or list folder: {file_path}"
                            )

            logger.info(f"Successfully read {len(target_contents)} files")

            if not target_contents:
                # Provide more specific error message
                if len(target_files) == 1 and target_files[0].startswith("azdo:"):
                    error_msg = f"No files found matching: {target_files[0]}. Check that the path and pattern are correct."
                else:
                    error_msg = f"Could not read any of the {len(target_files)} target file(s). Check that the paths exist and are accessible."
                logger.error(error_msg)
                return {"error": error_msg}

            # Estimate total input tokens
            total_chars = sum(len(tc["content"]) for tc in target_contents)
            estimated_tokens = estimate_tokens(
                "".join([tc["content"] for tc in target_contents])
            )

            # Check token limit
            max_tokens = int(os.getenv("MAX_INPUT_TOKENS", "100000"))
            if estimated_tokens > max_tokens:
                return {
                    "error": f"Input too large: ~{estimated_tokens:,} tokens estimated. "
                    f"Maximum allowed: {max_tokens:,} tokens. "
                    f"Please reduce the number of files or use smaller files. "
                    f"Current: {len(target_contents)} files with {total_chars:,} characters."
                }

            logger.info(
                f"Processing {len(target_contents)} files with ~{estimated_tokens:,} tokens"
            )

            # Step 2: Read reference files (guides, templates, examples)
            reference_contents = []
            if reference_files:
                for ref_file in reference_files:
                    content = await self._read_file(ref_file)
                    if content:
                        reference_contents.append(
                            {"file": ref_file, "content": content}
                        )

            # Step 3: Gather web context based on allow_web_search and seed_urls
            # Logic:
            # 1. allow_web_search=False, no seed_urls -> no crawling
            # 2. allow_web_search=True, no seed_urls -> crawl public internet (auto-generate query from request)
            # 3. allow_web_search=False, seed_urls provided -> crawl only seed URLs
            # 4. allow_web_search=True, seed_urls provided -> crawl seed URLs with priority, can also crawl public internet
            web_context = ""
            sources = []

            if seed_urls:
                # Seed URLs provided - crawl them regardless of allow_web_search flag
                # (seed URLs are explicit user intent, so always honor them)
                logger.info(f"Crawling {len(seed_urls)} seed URLs with priority")
                web_context, sources = await self._gather_web_context(seed_urls)

                if allow_web_search:
                    logger.info(
                        "Web search also allowed - seed URLs crawled with priority, public internet crawling available if needed"
                    )
                else:
                    logger.info(
                        "Web search disabled - only seed URLs will be crawled (no public internet)"
                    )
            elif allow_web_search:
                # No seed URLs but web search allowed - use crawler's search with request text
                logger.info(
                    "Web search enabled with no seed URLs - using request text as search query"
                )
                # Use crawler's search API directly (no seed URLs, just search query)
                web_context, sources = await self._search_web(request)
                if sources:
                    logger.info(f"Web search found {len(sources)} results")
                else:
                    logger.warning("Web search returned no results")
            else:
                # No seed URLs and web search disabled - no crawling at all
                logger.info(
                    "Web search disabled and no seed URLs provided - no web crawling"
                )

            # Step 4: Build workflow-specific prompt
            prompt = self._build_workflow_prompt(
                workflow=workflow,
                request=request,
                target_contents=target_contents,
                reference_contents=reference_contents,
                web_context=web_context,
            )

            # Step 5: Fetch available tools
            mcp_tools = await self._get_mcp_tools()
            azure_devops_tools = await self._get_azure_devops_tools()
            all_tools = mcp_tools + azure_devops_tools

            if all_tools:
                logger.info(
                    f"Providing {len(all_tools)} tools to LLM "
                    f"({len(mcp_tools)} MCP + {len(azure_devops_tools)} Azure DevOps)"
                )
            else:
                logger.warning("No tools available for LLM")

            # Step 6: LLM call with tools - may require multiple iterations if LLM calls tools
            logger.info(
                f"Making LLM {workflow} call " f"(~{len(prompt) // 4} tokens context)"
            )

            # Adjust temperature based on workflow
            temperature = {
                "understand": 0.1,  # Factual analysis
                "inspect": 0.0,  # Precise issue detection
                "generate": 0.3,  # Creative code generation
            }.get(workflow, 0.1)

            messages = [{"role": "user", "content": prompt}]
            max_iterations = (
                20  # Prevent infinite loops - allow more for complex searches
            )
            iteration = 0

            while iteration < max_iterations:
                iteration += 1
                logger.debug(f"LLM iteration {iteration}")

                response = await self.llm_client.chat_completion(
                    messages=messages,
                    model=model,
                    tools=all_tools if all_tools else None,
                    tool_choice="auto",
                    temperature=temperature,
                    max_tokens=4000,
                )

                # Check if LLM wants to call tools
                if response.get("tool_calls"):
                    logger.info(
                        f"LLM requested {len(response['tool_calls'])} tool call(s)"
                    )

                    # Add assistant message with tool calls
                    messages.append(
                        {
                            "role": "assistant",
                            "content": response.get("content") or "",
                            "tool_calls": response["tool_calls"],
                        }
                    )

                    # Execute each tool call
                    for tool_call in response["tool_calls"]:
                        tool_result = await self._handle_tool_call(tool_call)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call["id"],
                                "content": json.dumps(tool_result),
                            }
                        )

                    # Continue loop to get next LLM response with tool results
                    continue
                else:
                    # No tool calls - we have the final response
                    logger.info(f"LLM completed after {iteration} iteration(s)")
                    break

            if iteration >= max_iterations:
                logger.warning(
                    f"Reached max iterations ({max_iterations}), returning last response"
                )

            return {
                "workflow": workflow,
                "result": response["content"],
                "target_files": [tc["file"] for tc in target_contents],
                "sources": sources,
                "context_used": {
                    "target_files_count": len(target_contents),
                    "reference_files_count": len(reference_contents),
                    "web_sources_count": len(sources),
                },
            }

        except Exception as e:
            logger.error(f"{workflow} workflow failed: {e}")
            return {"error": str(e)}

    async def _read_file(self, file_path: str) -> Optional[str]:
        """
        Read file from MCP server (local or Azure DevOps).

        If file_path starts with 'azdo:', use Azure DevOps MCP server.
        Otherwise, use local file MCP server.

        Args:
            file_path: File path (e.g., "src/main.py" or "azdo:MergedComponents/file.json")

        Returns:
            File content or None on error
        """
        # Check if this is an Azure DevOps file
        if file_path.startswith("azdo:"):
            if not self.azure_devops_mcp_url:
                logger.error(
                    f"Azure DevOps file requested ({file_path}) but "
                    f"azure_devops_mcp_url is not configured. "
                    f"Set AZURE_DEVOPS_MCP_URL environment variable."
                )
                return None

            # Strip prefix and normalize backslashes to forward slashes (preserve case)
            clean_path = file_path[5:].strip()  # Remove "azdo:"
            clean_path = clean_path.replace(
                "\\", "/"
            )  # Normalize backslashes only, preserve case

            logger.info(
                f"Processing Azure DevOps path after normalization: {clean_path}"
            )

            # Check if this is a query pattern (contains keywords like 'file:', 'ext:', 'path:', 'branch:', 'AND')
            if self._is_azure_devops_query(clean_path):
                logger.info(f"Detected query pattern, executing search: {clean_path}")
                return await self._read_azure_devops_query(clean_path)
            else:
                # Single file path
                logger.info(f"Reading Azure DevOps file: {clean_path}")
                return await self._read_azure_devops_file(clean_path)

        # Use local file MCP server
        logger.info(f"Reading local file: {file_path}")

        # Handle Windows paths with drive letters if running in container
        # If path starts with drive letter (e.g. c:\os\src\...) and we are in container
        # where root is mounted (e.g. /data/files), we need to strip the prefix
        # This is a hack for the specific mapping C:\os -> /data/files

        # First, ensure we have forward slashes (client might have sent backslashes,
        # or _expand_paths might have already normalized them)
        file_path = file_path.replace("\\", "/")

        if ":" in file_path:
            # Check if it looks like the mapped root
            # Assuming C:\os is mapped to self.root_folder
            # We can try to find the relative part
            parts = file_path.split("/")
            # Try to find where the relative path starts
            # Heuristic: if path contains 'src', 'docs', 'data', 'tools', 'tests'
            for i, part in enumerate(parts):
                if part.lower() in ["src", "docs", "data", "tools", "tests"]:
                    # Construct relative path from here
                    file_path = "/".join(parts[i:])
                    logger.info(
                        f"Normalized Windows path to relative path: {file_path}"
                    )
                    break

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.mcp_url}/invoke",
                    json={
                        "tool_name": "read_local_file",
                        "arguments": {"file_path": file_path},
                    },
                )
                response.raise_for_status()
                result = response.json()

                if result.get("success"):
                    content = result["result"].get("content", "")
                    logger.info(
                        f"Successfully read local file: {file_path} ({len(content)} chars)"
                    )
                    return content
                else:
                    error_msg = result.get("error", "Unknown error")
                    logger.error(f"Failed to read local file {file_path}: {error_msg}")
                    return None

            except Exception as e:
                logger.error(f"Failed to read local file {file_path}: {e}")
                return None

    def _is_azure_devops_query(self, path: str) -> bool:
        """Check if path is an Azure DevOps query pattern rather than a simple file path."""
        query_keywords = ["file:", "ext:", "path:", "branch:", " AND ", " OR "]
        # Also treat paths with wildcards, folders, or recursive patterns as queries
        has_wildcard = "*" in path or "?" in path
        is_folder = path.endswith("/") or path.endswith("/**")
        return (
            any(keyword in path for keyword in query_keywords)
            or has_wildcard
            or is_folder
        )

    async def _read_azure_devops_query(self, query: str) -> Optional[str]:
        """
        Execute Azure DevOps query pattern and read matching files.

        Supports patterns like:
        - "Microsoft-NanoServer-PowerShell AND file:*.json"
        - "Microsoft-NanoServer-PowerShell ext:man"
        - "branch:official/rs_sparc_ctr; path:/MergedComponents; Microsoft-NanoServer-PowerShell AND file:*.json"

        Returns:
            Combined content of all matching files (up to 10) or None on error
        """
        if not self.azure_devops_mcp_url:
            logger.error("Azure DevOps MCP URL not configured")
            return None

        # Parse query to extract components
        query_parts = self._parse_azure_devops_query(query)
        logger.info(f"Parsed Azure DevOps query parts: {query_parts}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                logger.info(f"Searching Azure DevOps with query: {query_parts}")
                response = await client.post(
                    f"{self.azure_devops_mcp_url}/invoke",
                    json={
                        "tool_name": "search_azure_devops_files",
                        "arguments": query_parts,
                    },
                )
                response.raise_for_status()
                result = response.json()

                if not result.get("success"):
                    error_msg = result.get("error", "Unknown error")
                    logger.error(f"Azure DevOps query failed: {error_msg}")
                    return None

                files = result["result"].get("results", [])
                if not files:
                    logger.warning(
                        f"No files found matching pattern. "
                        f"Path: {query_parts.get('path_pattern', 'N/A')}, "
                        f"File pattern: {query_parts.get('file_pattern', 'N/A')}, "
                        f"Recursive: {query_parts.get('recursive', False)}"
                    )
                    return None

                logger.info(f"Found {len(files)} files, reading up to 10...")

                # Read content of matching files (limit to 10)
                contents = []
                for file_info in files[:10]:
                    file_path = (
                        file_info.get("path")
                        if isinstance(file_info, dict)
                        else file_info
                    )
                    content = await self._read_azure_devops_file(file_path)
                    if content:
                        contents.append(f"=== File: {file_path} ===\n{content}\n")

                if not contents:
                    logger.warning("Could not read any files from query results")
                    return None

                combined = "\n".join(contents)
                logger.info(
                    f"Read {len(contents)} files from query ({len(combined)} chars total)"
                )
                return combined

            except Exception as e:
                logger.error(f"Failed to execute Azure DevOps query: {e}")
                return None

    def _parse_azure_devops_query(self, query: str) -> Dict[str, Any]:
        """
        Parse Azure DevOps query pattern into search arguments.

        Examples:
        - "Nanoserver/merged/pkggen/Microsoft-NanoServer-Network.json" (single file)
          -> Direct file read (not a query)
        - "Nanoserver/merged/pkggen/Microsoft-NanoServer-Net*.json" (wildcard)
          -> {"path_pattern": "Nanoserver/merged/pkggen", "file_pattern": "Microsoft-NanoServer-Net*.json", "recursive": False}
        - "Nanoserver/merged/pkggen/" (folder, non-recursive)
          -> {"path_pattern": "Nanoserver/merged/pkggen", "recursive": False}
        - "Nanoserver/merged/pkggen/**" (folder, recursive)
          -> {"path_pattern": "Nanoserver/merged/pkggen", "recursive": True}
        - "Microsoft-NanoServer-PowerShell AND file:*.json"
          -> {"keyword": "Microsoft-NanoServer-PowerShell", "file_pattern": "*.json", "recursive": True}
        """
        import re

        has_keywords = any(
            kw in query for kw in ["file:", "ext:", "path:", "branch:", " AND ", " OR "]
        )

        # Handle simple path patterns (no explicit keywords)
        if not has_keywords:
            # Check for recursive folder pattern (ends with /**)
            if query.endswith("/**"):
                folder = query[:-3]  # Remove /**
                return {"path_pattern": folder, "recursive": True}

            # Check for non-recursive folder pattern (ends with /)
            elif query.endswith("/"):
                folder = query[:-1]  # Remove trailing /
                return {"path_pattern": folder, "recursive": False}

            # Check for wildcard pattern in filename
            elif "*" in query or "?" in query:
                # Parse wildcard patterns:
                # "/path/file*.json" -> search only in /path/ (recursive=False)
                # "/path/**/file*.json" -> search recursively under /path/ (recursive=True)

                # Check for /** pattern indicating recursive search
                recursive = "**" in query

                # Remove /** from path if present
                clean_query = query.replace("/**", "/") if "**" in query else query

                path_parts = clean_query.rsplit("/", 1)
                if len(path_parts) == 2:
                    # e.g., "/Nanoserver/merged/pkggen" + "Microsoft-NanoServer-Net*.json"
                    path = path_parts[0]
                    file_pattern = path_parts[1]

                    # Extract extension (e.g., ".json" -> "json")
                    extension = None
                    if "." in file_pattern:
                        extension = (
                            file_pattern.rsplit(".", 1)[1]
                            .replace("*", "")
                            .replace("?", "")
                        )

                    # Use "file:" prefix for filename pattern search in Azure DevOps Code Search
                    # This tells the API to search by filename, not file content
                    result = {
                        "path_pattern": path,  # Directory path for Path filter
                        "keyword": f"file:{file_pattern}",  # Use file: prefix for filename search
                        "recursive": recursive,  # False for /path/file*.json, True for /path/**/file*.json
                    }
                    # Don't send extension separately when using file: prefix
                    # The file pattern already includes the extension
                    return result
                else:
                    # No directory, just filename pattern
                    result = {
                        "keyword": f"file:{query}",  # Use file: prefix for filename search
                        "recursive": False,  # No path specified, search in root only
                    }
                    return result
                    return result

            # If we get here with no keywords and no patterns, it's a single file
            # This shouldn't happen as single files are handled by _read_azure_devops_file
            # But just in case, treat it as a search by filename
            return {"keyword": query, "recursive": True}

        # Handle explicit keyword-based queries
        args = {"recursive": True}  # Default to recursive for keyword searches

        # Split by semicolon for explicit parameters
        parts = [p.strip() for p in query.split(";")]
        keyword_parts = []

        for part in parts:
            if part.startswith("branch:"):
                args["branch"] = part[7:].strip()
            elif part.startswith("path:"):
                args["path_pattern"] = part[5:].strip()
            elif part.startswith("ext:"):
                args["extension"] = part[4:].strip()
            elif part.startswith("file:"):
                args["file_pattern"] = part[5:].strip()
            else:
                # Part of keyword search
                keyword_parts.append(part)

        # Process keyword parts for inline patterns (space-separated)
        if keyword_parts:
            combined = " ".join(keyword_parts)

            # Extract inline patterns
            import re

            # Extract file: pattern
            file_match = re.search(r"\bfile:(\S+)", combined)
            if file_match and "file_pattern" not in args:
                args["file_pattern"] = file_match.group(1)
                combined = re.sub(r"\bfile:\S+", "", combined)

            # Extract ext: pattern
            ext_match = re.search(r"\bext:(\S+)", combined)
            if ext_match and "extension" not in args:
                args["extension"] = ext_match.group(1)
                combined = re.sub(r"\bext:\S+", "", combined)

            # Extract path: pattern
            path_match = re.search(r"\bpath:(\S+)", combined)
            if path_match and "path_pattern" not in args:
                args["path_pattern"] = path_match.group(1)
                combined = re.sub(r"\bpath:\S+", "", combined)

            # Remaining text is keyword (remove AND/OR operators)
            keyword = re.sub(r"\b(AND|OR)\b", "", combined).strip()
            if keyword:
                args["keyword"] = keyword

        return args

    async def _read_azure_devops_file(self, file_path: str) -> Optional[str]:
        """Read file from Azure DevOps MCP server."""
        if not self.azure_devops_mcp_url:
            logger.error("Azure DevOps MCP URL not configured")
            return None

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                # Get branch from environment if available
                branch = os.getenv("AZURE_DEVOPS_BRANCH")
                logger.debug(
                    f"Calling Azure DevOps MCP: {self.azure_devops_mcp_url}/invoke (branch={branch})"
                )

                arguments = {"file_path": file_path}
                if branch:
                    arguments["branch"] = branch

                response = await client.post(
                    f"{self.azure_devops_mcp_url}/invoke",
                    json={
                        "tool_name": "get_azure_devops_file",
                        "arguments": arguments,
                    },
                )
                response.raise_for_status()
                result = response.json()

                if result.get("success"):
                    content = result["result"].get("content", "")
                    logger.info(
                        f"Successfully read Azure DevOps file: {file_path} ({len(content)} chars)"
                    )
                    return content
                else:
                    error_msg = result.get("error", "Unknown error")
                    logger.error(
                        f"Azure DevOps MCP returned error for {file_path}: {error_msg}"
                    )
                    return None

            except httpx.HTTPStatusError as e:
                logger.error(
                    f"HTTP error reading Azure DevOps file {file_path}: {e.response.status_code} - {e.response.text}"
                )
                return None
            except Exception as e:
                logger.error(f"Failed to read Azure DevOps file {file_path}: {e}")
                return None

    async def _list_files(
        self, folder_path: str, extension: str = "", recursive: bool = False
    ) -> Optional[List[Dict]]:
        """
        List files in a folder via MCP server (local or Azure DevOps).

        If folder_path starts with 'azdo:' or 'azure-devops:', use Azure DevOps MCP server.
        Otherwise, use local file MCP server.

        Args:
            folder_path: Path to folder
            extension: Optional file extension filter
            recursive: Whether to search subdirectories

        Returns:
            List of file info dicts with 'path' key, or None on error
        """
        # Check if this is an Azure DevOps path
        is_azure_devops = folder_path.startswith(("azdo:", "azure-devops:"))

        if is_azure_devops and self.azure_devops_mcp_url:
            # Strip prefix and use Azure DevOps MCP server
            clean_path = (
                folder_path.split(":", 1)[1] if ":" in folder_path else folder_path
            )
            return await self._list_azure_devops_files(clean_path, extension, recursive)

        # Use local file MCP server
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.mcp_url}/invoke",
                    json={
                        "tool_name": "list_files",
                        "arguments": {
                            "folder_path": folder_path,
                            "extension": extension,
                            "recursive": recursive,
                        },
                    },
                )
                response.raise_for_status()
                result = response.json()

                if result.get("success"):
                    files = result["result"].get("files", [])
                    # Ensure each file has a 'path' key
                    return [
                        {"path": f if isinstance(f, str) else f.get("path", f)}
                        for f in files
                    ]
                return None

            except Exception as e:
                logger.error(f"Failed to list files in {folder_path}: {e}")
                return None

    async def _list_azure_devops_files(
        self, path_pattern: str = "/", extension: str = "", recursive: bool = False
    ) -> Optional[List[Dict]]:
        """List files from Azure DevOps MCP server."""
        if not self.azure_devops_mcp_url:
            logger.error("Azure DevOps MCP URL not configured")
            return None

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                # Build arguments for search_azure_devops_files
                arguments = {
                    "path_pattern": path_pattern,
                    "recursive": recursive,
                }

                if extension:
                    # Remove leading dot if present
                    ext = extension.lstrip(".")
                    arguments["extension"] = ext

                response = await client.post(
                    f"{self.azure_devops_mcp_url}/invoke",
                    json={
                        "tool_name": "search_azure_devops_files",
                        "arguments": arguments,
                    },
                )
                response.raise_for_status()
                result = response.json()

                if result.get("success"):
                    files = result["result"].get("results", [])
                    # Convert to expected format with 'path' key
                    return [
                        {"path": f["path"] if isinstance(f, dict) else f} for f in files
                    ]
                return None

            except Exception as e:
                logger.error(
                    f"Failed to list Azure DevOps files in {path_pattern}: {e}"
                )
                return None

    async def _search_web(self, query: str) -> tuple[str, List[Dict]]:
        """
        Search the web using crawler's search API (no seed URLs).

        Args:
            query: The user's request text as search query

        Returns:
            (combined_text, sources)
        """
        # Call crawler with search query only (no seed URLs)
        docs = await self._crawl_with_query(query)

        # If we got docs, index them and retrieve relevant chunks
        if docs:
            await self._index_docs(docs)

            # Vector search with the query
            hits = await self._retrieve_docs(query, k=5)

            # Build context from hits
            web_text = "\n\n".join(
                [f"Source: {hit['url']}\n{hit['content']}" for hit in hits]
            )

            sources = [
                {"url": hit["url"], "title": hit.get("title", "")} for hit in hits
            ]

            return web_text, sources

        return "", []

    async def _gather_web_context(self, seed_urls: List[str]) -> tuple[str, List[Dict]]:
        """
        Crawl web content and retrieve relevant chunks via vector search.

        Args:
            seed_urls: URLs to crawl

        Returns:
            (combined_text, sources)
        """
        if not seed_urls:
            return "", []

        # Crawl provided URLs
        docs = await self._crawl_urls(seed_urls)

        # If we got docs, index them and retrieve relevant chunks
        if docs:
            await self._index_docs(docs)

            # Vector search with generic query - execution model will filter semantically
            hits = await self._retrieve_docs("documentation overview", k=5)

            # Build context from hits
            web_text = "\n\n".join(
                [f"Source: {hit['url']}\n{hit['content']}" for hit in hits]
            )

            sources = [
                {"url": hit["url"], "title": hit.get("title", "")} for hit in hits
            ]

            return web_text, sources

        return "", []

    async def _crawl_urls(self, urls: List[str]) -> List[Dict]:
        """Crawl specific seed URLs."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{self.crawler_url}/crawl",
                    json={
                        "query": "documentation",  # Generic query for seed URL crawling
                        "seed_urls": urls,
                        "max_results": 5,
                        "depth": 1,
                    },
                )
                response.raise_for_status()
                result = response.json()
                return result.get("docs", [])

            except Exception as e:
                logger.error(f"Crawling failed: {e}")
                return []

    async def _crawl_with_query(self, query: str) -> List[Dict]:
        """Search web using query only (no seed URLs)."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{self.crawler_url}/crawl",
                    json={
                        "query": query,  # Use actual request text as search query
                        "seed_urls": [],  # Empty - let crawler search
                        "max_results": 5,
                        "depth": 1,
                    },
                )
                response.raise_for_status()
                result = response.json()
                return result.get("docs", [])

            except Exception as e:
                logger.error(f"Web search failed: {e}")
                return []

    async def _index_docs(self, docs: List[Dict]):
        """Index documents in vector store."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                await client.post(f"{self.indexer_url}/index", json={"docs": docs})
            except Exception as e:
                logger.error(f"Indexing failed: {e}")

    async def _retrieve_docs(self, query: str, k: int = 5) -> List[Dict]:
        """Retrieve relevant documents."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{self.indexer_url}/retrieve",
                    json={"query": query, "k": k},
                )
                response.raise_for_status()
                result = response.json()
                return result.get("hits", [])

            except Exception as e:
                logger.error(f"Retrieval failed: {e}")
                return []

    def _build_workflow_prompt(
        self,
        workflow: WorkflowType,
        request: str,
        target_contents: List[Dict],
        reference_contents: List[Dict],
        web_context: str,
    ) -> str:
        """Build workflow-specific prompt with all context."""

        # Workflow-specific instructions
        workflow_instructions = {
            "understand": """
Analyze and document these files.
Unless the user request specifies otherwise, your response should:
1. Summarize what each file does (purpose and functionality)
2. Explain key components and their roles
3. Describe how files interact with each other
4. Highlight important implementation details
5. Create clear, comprehensive documentation
""",
            "inspect": """
Inspect these files for potential issues.
Unless the user request specifies otherwise, look for:
1. Bugs or logic errors
2. Security vulnerabilities
3. Performance issues
4. Code style violations
5. Maintainability concerns
6. Missing error handling
7. Anti-patterns or code smells

For each issue found, provide:
- Severity (critical/high/medium/low)
- Location (file and line if possible)
- Description of the problem
- Suggested fix
""",
            "generate": """
Learn patterns from the provided reference files and generate new code based on the request.

Your response should:
1. Analyze patterns and conventions in reference files
2. Understand the structure and style
3. Generate new code that follows the same patterns
4. Include appropriate comments and documentation
5. Ensure generated code is complete and functional

Format your response as:
```<language>
<generated code>
```
""",
        }

        prompt = f"""# Code Intelligence Request

## Workflow: {workflow.upper()}

## Default Workflow Guidelines:
{workflow_instructions.get(workflow, "")}

## User Request (PRIMARY INSTRUCTION - OVERRIDES GUIDELINES):
{request}

---

## TARGET FILES:

"""

        # Add target files
        for tc in target_contents:
            prompt += f"### File: {tc['file']}\n\n```\n{tc['content']}\n```\n\n"

        # Add reference files (guides, templates, examples)
        if reference_contents:
            prompt += "\n---\n\n## REFERENCE FILES (guides/templates/examples):\n\n"
            for rc in reference_contents:
                prompt += f"### {rc['file']}\n\n```\n{rc['content']}\n```\n\n"

        # Add web context
        if web_context:
            prompt += "\n---\n\n## RELATED DOCUMENTATION:\n\n"
            prompt += web_context

        prompt += "\n---\n\nPlease complete the request above."

        return prompt

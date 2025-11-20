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

import logging
import os
from typing import Any, Dict, List, Literal, Optional

import httpx

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
    ):
        self.mcp_url = mcp_url
        self.crawler_url = crawler_url
        self.indexer_url = indexer_url
        self.llm_client = llm_client

    async def execute_workflow(
        self,
        workflow: WorkflowType,
        target_files: List[str],
        request: str,
        model: str,
        reference_files: Optional[List[str]] = None,
        seed_urls: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a code intelligence workflow.

        Args:
            workflow: Type of workflow ("understand", "inspect", "generate")
            target_files: Primary files to operate on
            request: User's specific request/instruction
            model: LLM model to use (from client selection)
            reference_files: Optional reference files (guides, templates, examples)
            seed_urls: Optional URLs to crawl for additional context

        Returns:
            Result with content and sources
        """
        logger.info(f"Starting {workflow} workflow for {len(target_files)} files")
        logger.info(f"Using model: {model}")

        try:
            # Step 1: Read target files (expand folders to files if needed)
            target_contents = []
            for file_path in target_files:
                # Check if it's a folder - if so, list files in it
                if not file_path or "/" not in file_path and "\\" not in file_path:
                    # Could be folder without path separator
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
                        content = await self._read_file(file_path)
                        if content:
                            target_contents.append(
                                {"file": file_path, "content": content}
                            )
                        else:
                            logger.warning(f"Could not read file: {file_path}")
                else:
                    # Has path separator, treat as file
                    content = await self._read_file(file_path)
                    if content:
                        target_contents.append({"file": file_path, "content": content})
                    else:
                        # Maybe it's a folder path?
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

            if not target_contents:
                return {"error": "Could not read any target files"}

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

            # Step 3: Gather web context (if seed URLs provided)
            web_context = ""
            sources = []

            if seed_urls:
                # Crawl provided URLs and retrieve relevant content
                web_context, sources = await self._gather_web_context(seed_urls)

            # Step 4: Build workflow-specific prompt
            prompt = self._build_workflow_prompt(
                workflow=workflow,
                request=request,
                target_contents=target_contents,
                reference_contents=reference_contents,
                web_context=web_context,
            )

            # Step 5: Single LLM call for execution
            logger.info(
                f"Making single LLM {workflow} call "
                f"(~{len(prompt) // 4} tokens context)"
            )

            # Adjust temperature based on workflow
            temperature = {
                "understand": 0.1,  # Factual analysis
                "inspect": 0.0,  # Precise issue detection
                "generate": 0.3,  # Creative code generation
            }.get(workflow, 0.1)

            response = await self.llm_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=temperature,
                max_tokens=4000,
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
        """Read file from MCP server."""
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
                    return result["result"].get("content", "")
                return None

            except Exception as e:
                logger.error(f"Failed to read file {file_path}: {e}")
                return None

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
        """Crawl web pages."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{self.crawler_url}/crawl",
                    json={
                        "query": "documentation",
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
Analyze and document these files. Your response should:
1. Summarize what each file does (purpose and functionality)
2. Explain key components and their roles
3. Describe how files interact with each other
4. Highlight important implementation details
5. Create clear, comprehensive documentation
""",
            "inspect": """
Inspect these files for potential issues. Look for:
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

## User Request:
{request}

{workflow_instructions.get(workflow, "")}

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

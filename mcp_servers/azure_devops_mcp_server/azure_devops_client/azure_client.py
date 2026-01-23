"""
Azure DevOps client for code search and file retrieval.
Handles authentication via PAT (Personal Access Token) and API calls.

This client directly uses Azure DevOps Code Search API which performs
recursive search by default. No client-side recursive processing needed.
"""

import base64
import difflib
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class AzureDevOpsClient:
    """Client for Azure DevOps code search and file operations."""

    def __init__(
        self,
        organization: str,
        project: str,
        repository: str,
        branch: str,
        pat: str,
        max_results: int = 50,
    ):
        """
        Initialize Azure DevOps client.

        Args:
            organization: Azure DevOps organization name
            project: Project name
            repository: Repository name
            branch: Branch name (required)
            pat: Personal Access Token (required)
            max_results: Default maximum results per query (default: 50)
        """
        self.organization = organization
        self.project = project
        self.repository = repository
        self.branch = branch
        self.pat = pat
        self.max_results = max_results

        self.base_url = f"https://dev.azure.com/{organization}"
        self.api_version = "7.1-preview.1"  # Code Search API version

    async def authenticate(self) -> bool:
        """
        Authenticate with Azure DevOps using PAT.

        Returns:
            True if PAT is configured
        """
        if not self.pat:
            logger.error("No PAT configured for authentication")
            return False

        logger.info("Using Personal Access Token for authentication")
        return True

    def _get_auth_header(self) -> Dict[str, str]:
        """Get authorization header for API requests."""
        if not self.pat:
            raise RuntimeError("No PAT configured. Set pat in configuration.")

        # PAT uses Basic auth with empty username
        credentials = base64.b64encode(f":{self.pat}".encode()).decode()
        return {"Authorization": f"Basic {credentials}"}

    async def search_code(
        self,
        search_text: str,
        max_results: int = 20,
        branch: str = "",
        path: str = "/",
        project: Optional[str] = None,
        repository: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for code in the repository using Azure DevOps Code Search API.

        The search_text parameter is passed directly to Azure DevOps Code Search API.
        See: https://learn.microsoft.com/en-us/rest/api/azure/devops/search/code-search-results/fetch-code-search-results

        Search Text Syntax (passed directly to Azure API):
        ================================================
        - Keyword: myKeyword
        - File Extension: mySearchTerm ext:xml
        - File Name: mySearchTerm file:config OR file:*config.xml
        - Path (Keyword): mySearchTerm path:Services
        - Boolean Logic: mySearchTerm AND NOT ext:json
        - Code Element: mySearchTerm class:MyClass (C#, Java, etc.)
        - Aggregate: (keyword1 OR keyword2) ext:xml
        - File name specific: (keyword1 OR keyword2) file:*config.xml

        Args:
            search_text: Search query text, passed directly to Azure DevOps Code Search API.
                        Include filters like ext:, file:, path:, class:, etc. in this string.
            max_results: Maximum number of results
            branch: Branch to search (uses configured branch if empty string)
            path: Path scope filter - folder path like "/src/services" to limit search scope
            project: Project name override (default: use configured project)
            repository: Repository name override (default: use configured repository)

        Returns:
            List of search results with file path, content preview, etc.
        """
        if not self.pat:
            raise RuntimeError("Not authenticated - PAT required")

        # Use provided values or fall back to configured defaults
        search_branch = branch or self.branch
        search_path = path or "/"
        search_project = project or self.project
        search_repository = repository or self.repository

        try:
            url = f"https://almsearch.dev.azure.com/{self.organization}/_apis/search/codesearchresults"
            params = {"api-version": "6.0-preview.1"}

            # Build filters - always include Repository, Project, Branch, and Path
            filters = {
                "Repository": [search_repository],
                "Project": [search_project],
                "Branch": [search_branch],
                "Path": [search_path],
            }

            payload = {
                "searchText": search_text,
                "$top": max_results,
                "$skip": 0,
                "filters": filters,
            }

            logger.info(
                f"Azure DevOps Code Search: searchText='{search_text}', path='{search_path}', "
                f"project='{search_project}', repo='{search_repository}', branch='{search_branch}'"
            )

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers={
                        **self._get_auth_header(),
                        "Content-Type": "application/json",
                    },
                    params=params,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            # Parse results
            results = []
            for item in data.get("results", []):
                results.append(
                    {
                        "file_path": item.get("path", ""),
                        "file_name": item.get("fileName", ""),
                        "repository": item.get("repository", {}).get("name", ""),
                        "project": item.get("project", {}).get("name", ""),
                        "matches": item.get("matches", {}),
                        "preview": self._extract_preview(item),
                    }
                )

            logger.info(f"Code search returned {len(results)} results")
            return results

        except httpx.HTTPError as e:
            logger.error(f"Code search failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Code search error: {e}", exc_info=True)
            raise

    def _extract_preview(self, item: Dict[str, Any]) -> str:
        """Extract preview text from search result."""
        matches = item.get("matches", {})
        content = matches.get("content", [])

        if content and len(content) > 0:
            first_match = content[0]
            char_offset: str = first_match.get("charOffset", "")
            return char_offset

        return ""

    async def get_file_content(
        self,
        file_path: str,
        branch: Optional[str] = None,
        project: Optional[str] = None,
        repository: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get file content from repository.

        Args:
            file_path: Path to file in repository
            branch: Branch name (default: use configured branch or repository default)
            project: Project name override (default: use configured project)
            repository: Repository name override (default: use configured repository)

        Returns:
            Dict with file content and metadata
        """
        if not self.pat:
            raise RuntimeError("Not authenticated - PAT required")

        # Use configured values if not specified
        # Only use default branch if we're also using default project/repo
        get_project = project or self.project
        get_repository = repository or self.repository

        # If project or repo is overridden, don't use the default branch
        # (let Azure DevOps use the repo's default branch instead)
        if project or repository:
            get_branch = branch  # Use provided branch or None (repo default)
        else:
            get_branch = branch or self.branch  # Use provided or configured default

        try:
            url = (
                f"{self.base_url}/{get_project}/_apis/git/repositories/"
                f"{get_repository}/items"
            )
            params = {
                "path": file_path,
                "api-version": "7.0",
            }

            # Only add version descriptor if branch is specified
            if get_branch:
                params["versionDescriptor.version"] = get_branch
                params["versionDescriptor.versionType"] = "branch"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url, headers=self._get_auth_header(), params=params
                )
                response.raise_for_status()

                # Get content
                content = response.text

                # Get metadata from headers
                content_type = response.headers.get("Content-Type", "text/plain")
                object_id = response.headers.get("x-tfs-objectid", "")

                return {
                    "file_path": file_path,
                    "branch": branch or "default",
                    "content": content,
                    "content_type": content_type,
                    "object_id": object_id,
                    "size": len(content),
                }

        except httpx.HTTPError as e:
            logger.error(f"Failed to get file content: {e}")
            raise
        except Exception as e:
            logger.error(f"Get file content error: {e}", exc_info=True)
            raise

    async def get_commit_changes(
        self,
        commit_id: str,
        project: Optional[str] = None,
        repository: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get changes associated with a specific commit.

        See: https://learn.microsoft.com/en-us/rest/api/azure/devops/git/commits/get-changes

        Args:
            commit_id: The commit ID (SHA-1 hash)
            project: Project name override (default: use configured project)
            repository: Repository name override (default: use configured repository)

        Returns:
            Dict with commit changes including modified files and their changes
        """
        if not self.pat:
            raise RuntimeError("Not authenticated - PAT required")

        # Use configured values if not specified
        get_project = project or self.project
        get_repository = repository or self.repository

        try:
            url = (
                f"{self.base_url}/{get_project}/_apis/git/repositories/"
                f"{get_repository}/commits/{commit_id}/changes"
            )
            params = {"api-version": "7.1"}

            logger.info(
                f"Fetching commit changes: commit={commit_id}, "
                f"project={get_project}, repo={get_repository}"
            )

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url, headers=self._get_auth_header(), params=params
                )
                response.raise_for_status()
                data = response.json()

            # Extract relevant information
            changes = data.get("changes", [])
            commit_info = {
                "commit_id": commit_id,
                "change_count": data.get("changeCount", 0),
                "changes": [],
            }

            # Process each change
            change_types_count: Dict[str, int] = {}
            for change in changes:
                item = change.get("item", {})
                change_type = change.get("changeType", "")
                change_info = {
                    "change_type": change_type,
                    "path": item.get("path", ""),
                    "git_object_type": item.get("gitObjectType", ""),
                    "url": item.get("url", ""),
                }

                # Include source information if this is a rename
                if "sourceServerItem" in change:
                    change_info["source_path"] = change.get("sourceServerItem", "")

                commit_info["changes"].append(change_info)

                # Track change types for summary
                change_types_count[change_type] = (
                    change_types_count.get(change_type, 0) + 1
                )

            # Add a summary to help LLM generate a response
            summary_parts = [
                f"Found {len(changes)} file(s) changed in commit {commit_id[:8]}..."
            ]
            for change_type, count in change_types_count.items():
                summary_parts.append(f"{count} {change_type.lower()}")
            commit_info["summary"] = ". ".join(summary_parts) + "."

            logger.info(f"Retrieved {len(changes)} changes for commit {commit_id}")
            return commit_info

        except httpx.HTTPError as e:
            logger.error(f"Failed to get commit changes: {e}")
            raise
        except Exception as e:
            logger.error(f"Get commit changes error: {e}", exc_info=True)
            raise

    async def get_commit_file_diff(
        self,
        commit_id: str,
        file_path: str,
        project: Optional[str] = None,
        repository: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get line-level diff for a specific file in a commit.

        Fetches both original and modified blob content and computes unified diff client-side.
        This is the official supported method since Azure DevOps public API doesn't return
        diff blocks directly.

        Args:
            commit_id: The commit ID (SHA-1 hash)
            file_path: Path to the file in the repository
            project: Project name override (default: use configured project)
            repository: Repository name override (default: use configured repository)

        Returns:
            Dict with line-level diff in unified diff format
        """
        if not self.pat:
            raise RuntimeError("Not authenticated - PAT required")

        # Use configured values if not specified
        get_project = project or self.project
        get_repository = repository or self.repository

        # Normalize the file path - remove leading slash for comparison
        normalized_path = file_path.lstrip("/")

        try:
            # Step 1: Get the commit to find its parent
            commit_url = (
                f"{self.base_url}/{get_project}/_apis/git/repositories/"
                f"{get_repository}/commits/{commit_id}"
            )
            commit_params = {"api-version": "7.1"}

            async with httpx.AsyncClient(timeout=30.0) as client:
                commit_response = await client.get(
                    commit_url, headers=self._get_auth_header(), params=commit_params
                )
                commit_response.raise_for_status()
                commit_data = commit_response.json()

            # Get parent commit (compare against parent to show what this commit changed)
            parents = commit_data.get("parents", [])
            base_version = parents[0] if parents else None

            if not base_version:
                return {
                    "commit_id": commit_id,
                    "file_path": file_path,
                    "base_commit": None,
                    "diff": "",
                    "summary": f"Commit {commit_id[:8]}... has no parent (initial commit)",
                    "error": "Cannot show diff for initial commit (no parent to compare against)",
                }

            # Step 2: Get the changes list to find blob IDs
            changes_url = (
                f"{self.base_url}/{get_project}/_apis/git/repositories/"
                f"{get_repository}/commits/{commit_id}/changes"
            )
            changes_params = {"api-version": "7.1"}

            logger.info(
                f"Fetching changes for commit {commit_id[:8]}... to find blob IDs for {normalized_path}"
            )

            async with httpx.AsyncClient(timeout=30.0) as client:
                changes_response = await client.get(
                    changes_url, headers=self._get_auth_header(), params=changes_params
                )
                changes_response.raise_for_status()
                changes_data = changes_response.json()

            # Step 3: Find the specific file in changes
            target_change = None
            for change in changes_data.get("changes", []):
                item = change.get("item", {})
                item_path = item.get("path", "").lstrip("/")

                if item_path.lower() == normalized_path.lower():
                    target_change = change
                    break

            if not target_change:
                return {
                    "commit_id": commit_id,
                    "file_path": file_path,
                    "base_commit": base_version,
                    "diff": "",
                    "summary": f"File {file_path} not found in commit {commit_id[:8]}... changes",
                    "warning": "File not modified in this commit",
                }

            # Get blob IDs
            item = target_change.get("item", {})
            change_type = target_change.get("changeType", "")
            original_object_id = item.get("originalObjectId")  # Parent version blob ID
            object_id = item.get("objectId")  # Current version blob ID

            logger.info(
                f"Found file: change_type={change_type}, "
                f"original_blob={original_object_id[:8] if original_object_id else 'None'}..., "
                f"new_blob={object_id[:8] if object_id else 'None'}..."
            )

            # Step 4: Fetch blob content for both versions
            original_content = ""
            new_content = ""

            async with httpx.AsyncClient(timeout=30.0) as client:
                # Fetch original version (if exists)
                if original_object_id and change_type != "add":
                    original_blob_url = (
                        f"{self.base_url}/{get_project}/_apis/git/repositories/"
                        f"{get_repository}/blobs/{original_object_id}"
                    )
                    blob_params = {"api-version": "7.1"}
                    try:
                        original_response = await client.get(
                            original_blob_url,
                            headers=self._get_auth_header(),
                            params=blob_params,
                        )
                        original_response.raise_for_status()
                        original_content = original_response.text
                    except httpx.HTTPError as e:
                        logger.warning(f"Failed to fetch original blob: {e}")
                        original_content = ""

                # Fetch new version (if exists)
                if object_id and change_type != "delete":
                    new_blob_url = (
                        f"{self.base_url}/{get_project}/_apis/git/repositories/"
                        f"{get_repository}/blobs/{object_id}"
                    )
                    blob_params = {"api-version": "7.1"}
                    try:
                        new_response = await client.get(
                            new_blob_url,
                            headers=self._get_auth_header(),
                            params=blob_params,
                        )
                        new_response.raise_for_status()
                        new_content = new_response.text
                    except httpx.HTTPError as e:
                        logger.warning(f"Failed to fetch new blob: {e}")
                        new_content = ""

            # Step 5: Compute unified diff using Python's difflib
            original_lines = original_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)

            diff_lines = list(
                difflib.unified_diff(
                    original_lines,
                    new_lines,
                    fromfile=f"a/{file_path}",
                    tofile=f"b/{file_path}",
                    lineterm="",
                )
            )

            # Join diff lines into single string
            unified_diff = "\n".join(diff_lines)

            # Count additions and deletions
            lines_added = sum(
                1
                for line in diff_lines
                if line.startswith("+") and not line.startswith("+++")
            )
            lines_removed = sum(
                1
                for line in diff_lines
                if line.startswith("-") and not line.startswith("---")
            )

            # Build summary
            summary_parts = [f"Diff for {file_path} in commit {commit_id[:8]}..."]
            if lines_added > 0:
                summary_parts.append(f"+{lines_added} lines")
            if lines_removed > 0:
                summary_parts.append(f"-{lines_removed} lines")
            summary = ". ".join(summary_parts) + "."

            logger.info(
                f"Generated diff for {file_path}: +{lines_added} -{lines_removed} lines"
            )

            return {
                "commit_id": commit_id,
                "file_path": file_path,
                "base_commit": base_version,
                "change_type": change_type,
                "lines_added": lines_added,
                "lines_removed": lines_removed,
                "diff": unified_diff,
                "summary": summary,
            }

        except httpx.HTTPError as e:
            logger.error(f"Failed to get commit file diff: {e}")
            raise
        except Exception as e:
            logger.error(f"Get commit file diff error: {e}", exc_info=True)
            raise

    async def test_connection(self) -> bool:
        """
        Test connection to Azure DevOps.

        Returns:
            True if connection successful
        """
        try:
            url = f"{self.base_url}/_apis/projects/{self.project}"
            params = {"api-version": "7.0"}

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url, headers=self._get_auth_header(), params=params
                )
                response.raise_for_status()
                logger.info("Connection test successful")
                return True

        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

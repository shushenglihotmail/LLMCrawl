"""
Azure DevOps client for code search and file retrieval.
Handles authentication (interactive OAuth or PAT) and API calls.
"""

import base64
import logging
import webbrowser
from typing import Any, Dict, List, Optional

import httpx
from azure.devops.connection import Connection
from msal import PublicClientApplication

logger = logging.getLogger(__name__)


class AzureDevOpsClient:
    """Client for Azure DevOps code search and file operations."""

    # Azure DevOps public client ID (for interactive auth)
    CLIENT_ID = "499b84ac-1321-427f-aa17-267ca6975798"  # VS Code client ID
    AUTHORITY = "https://login.microsoftonline.com/organizations"
    SCOPES = ["499b84ac-1321-427f-aa17-267ca6975798/.default"]

    def __init__(
        self,
        organization: str,
        project: str,
        repository: str,
        branch: str,
        pat: Optional[str] = None,
        max_results: int = 50,
    ):
        """
        Initialize Azure DevOps client.

        Args:
            organization: Azure DevOps organization name
            project: Project name
            repository: Repository name
            branch: Branch name (required)
            pat: Personal Access Token (optional, interactive auth if None)
            max_results: Default maximum results per query (default: 50)
        """
        self.organization = organization
        self.project = project
        self.repository = repository
        self.branch = branch
        self.pat = pat
        self.max_results = max_results
        self._access_token: Optional[str] = None
        self._connection: Optional[Connection] = None

        self.base_url = f"https://dev.azure.com/{organization}"
        self.api_version = "7.1-preview.1"  # Code Search API version

    async def authenticate(self, use_interactive: bool = True) -> bool:
        """
        Authenticate with Azure DevOps.

        Args:
            use_interactive: Use interactive browser-based OAuth flow

        Returns:
            True if authentication successful
        """
        if self.pat:
            logger.info("Using Personal Access Token for authentication")
            self._access_token = self.pat
            return True

        if use_interactive:
            logger.info("Starting interactive authentication...")
            return await self._interactive_auth()

        logger.error("No authentication method available")
        return False

    async def _interactive_auth(self) -> bool:
        """
        Perform interactive OAuth authentication.

        Returns:
            True if authentication successful
        """
        try:
            app = PublicClientApplication(
                client_id=self.CLIENT_ID, authority=self.AUTHORITY
            )

            # Try to get cached token first
            accounts = app.get_accounts()
            if accounts:
                logger.info("Found cached account, attempting silent auth...")
                result = app.acquire_token_silent(self.SCOPES, account=accounts[0])
                if result and "access_token" in result:
                    self._access_token = result["access_token"]
                    logger.info("Silent authentication successful")
                    return True

            # No cached token, initiate device code flow
            logger.info("No cached token found, initiating device code flow...")
            flow = app.initiate_device_flow(scopes=self.SCOPES)

            if "user_code" not in flow:
                logger.error("Failed to create device flow")
                return False

            # Display user code and open browser
            print("\n" + "=" * 60)
            print("AZURE DEVOPS AUTHENTICATION REQUIRED")
            print("=" * 60)
            print(f"\nPlease visit: {flow['verification_uri']}")
            print(f"And enter code: {flow['user_code']}\n")
            print("Opening browser automatically...")
            print("=" * 60 + "\n")

            # Open browser
            webbrowser.open(flow["verification_uri"])

            # Wait for user to authenticate
            result = app.acquire_token_by_device_flow(flow)

            if "access_token" in result:
                self._access_token = result["access_token"]
                logger.info("Interactive authentication successful")
                print("\n✅ Authentication successful!\n")
                return True
            else:
                error = result.get("error_description", "Unknown error")
                logger.error(f"Authentication failed: {error}")
                print(f"\n❌ Authentication failed: {error}\n")
                return False

        except Exception as e:
            logger.error(f"Interactive authentication error: {e}", exc_info=True)
            return False

    def _get_auth_header(self) -> Dict[str, str]:
        """Get authorization header for API requests."""
        if not self._access_token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        if self.pat:
            # PAT uses Basic auth
            credentials = base64.b64encode(f":{self.pat}".encode()).decode()
            return {"Authorization": f"Basic {credentials}"}
        else:
            # OAuth uses Bearer token
            return {"Authorization": f"Bearer {self._access_token}"}

    async def search_code(
        self,
        query: str,
        file_type: Optional[str] = None,
        max_results: int = 20,
        branch: str = "",
        path: str = "/",
        project: Optional[str] = None,
        repository: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for code in the repository.

        Args:
            query: Search query
            file_type: Filter by file extension (e.g., "*.cpp", "*.h")
            max_results: Maximum number of results
            branch: Branch to search (uses configured branch if empty string)
            path: Path filter (default: "/" for root)
            project: Project name override (default: use configured project)
            repository: Repository name override (default: use configured repository)

        Returns:
            List of search results with file path, content preview, etc.
        """
        if not self._access_token:
            raise RuntimeError("Not authenticated")

        # Use provided values or fall back to configured defaults
        search_branch = branch or self.branch
        search_path = path or "/"
        search_project = project or self.project
        search_repository = repository or self.repository

        try:
            # Build search request
            search_text = query
            if file_type:
                search_text = f"{query} ext:{file_type}"

            url = f"https://almsearch.dev.azure.com/{self.organization}/_apis/search/codesearchresults"
            params = {"api-version": "6.0-preview.1"}

            # Build filters - always include Repository, Project, Branch, and Path
            filters = {
                "Repository": [search_repository],
                "Project": [search_project],
                "Branch": [search_branch],  # Always include branch filter
                "Path": [search_path],  # Always include path filter
            }

            payload = {
                "searchText": search_text,
                "$top": max_results,
                "$skip": 0,
                "filters": filters,
            }

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

    async def search_files(
        self,
        path_pattern: Optional[str] = None,
        file_pattern: Optional[str] = None,
        extension: Optional[str] = None,
        keyword: Optional[str] = None,
        branch: Optional[str] = None,
        max_results: Optional[int] = None,
        recursive: bool = False,
        project: Optional[str] = None,
        repository: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for files in the repository with flexible filtering.

        IMPORTANT: By default, searches only the root directory (non-recursive).
        Set recursive=True to search subdirectories (slower for large repos).

        Supports:
        - Path patterns: path:src/, path:**/pipelines/** (requires recursive=True for **)
        - File patterns: file:azure-pipelines*, file:*test*, file:"README.md"
        - Extensions: ext:yml, ext:json, ext:cs
        - Keywords: Search in file content with wildcards (requires recursive=True)
        - Glob patterns: ** (any depth), * (any chars in segment), ? (single char)

        Args:
            path_pattern: Path filter (e.g., "src/", "path:**/pipelines/**")
            file_pattern: File name filter (e.g., "file:azure-pipelines*", "*test*")
            extension: File extension filter (e.g., "ext:yml", "yml", ".yml")
            keyword: Keyword to search in file content (supports wildcards)
            branch: Branch to search (default: configured branch)
            max_results: Max results to return (default: configured max_results)
            recursive: If True, search subdirectories recursively (default: False for safety)
            project: Project name override (default: use configured project)
            repository: Repository name override (default: use configured repository)

        Returns:
            List of matching files with path and metadata
        """
        if not self._access_token:
            raise RuntimeError("Not authenticated")

        branch = branch or self.branch
        max_results = max_results or self.max_results
        search_project = project or self.project
        search_repository = repository or self.repository

        try:
            # If keyword or file_pattern with recursive search, use Code Search API (fast & indexed)
            # Code Search API is much faster than listing all files recursively
            if keyword or (file_pattern and recursive):
                logger.info(
                    f"Using Azure DevOps Code Search API (keyword={keyword}, file_pattern={file_pattern}, recursive={recursive})"
                )

                # For file_pattern searches, extract the pattern as search query
                search_query = keyword if keyword else ""
                if file_pattern and not keyword:
                    # Convert file pattern to filename search
                    # Remove "file:" prefix if present
                    pattern = file_pattern.replace("file:", "").strip()
                    # Extract base name without wildcards for search
                    # e.g., "Microsoft-Windows-Runtime-Metadata-NanoServer.*" -> "Microsoft-Windows-Runtime-Metadata-NanoServer"
                    base_name = pattern.replace("*", "").replace("?", "").strip(".")
                    search_query = base_name

                file_ext = None
                if extension:
                    file_ext = extension.replace("ext:", "").replace(".", "").strip()

                # Prepare path filter for Code Search API
                search_path = "/"
                if path_pattern:
                    # Remove "path:" prefix if present
                    search_path = (
                        path_pattern.replace("path:", "").strip().strip('"').lstrip("/")
                    )
                    # For Code Search API, ensure path starts with /
                    if not search_path.startswith("/"):
                        search_path = "/" + search_path

                code_results = await self.search_code(
                    query=search_query,
                    file_type=file_ext,
                    max_results=max_results,
                    branch=branch,
                    path=search_path,
                    project=search_project,
                    repository=search_repository,
                )

                # Convert code search results to file search format
                results = [
                    {
                        "path": item["file_path"],
                        "name": item["file_name"],
                        "size": 0,  # Not provided by code search
                        "objectId": "",
                        "url": "",
                        "preview": item.get("preview", ""),
                    }
                    for item in code_results
                ]

                # If file_pattern was specified, filter results by pattern match
                if file_pattern and results:
                    pattern = file_pattern.replace("file:", "").strip()
                    import fnmatch

                    results = [
                        r for r in results if fnmatch.fnmatch(r["name"], pattern)
                    ]

                logger.info(f"Code search returned {len(results)} results")
                return results

            # Otherwise use Git Items API to list files with filters (for non-recursive or no pattern searches)
            url = f"{self.base_url}/{search_project}/_apis/git/repositories/{search_repository}/items"
            params = {
                "recursionLevel": "Full" if recursive else "OneLevel",
                "api-version": "7.0",
            }

            # Add scopePath if path_pattern is a simple folder path (not a glob pattern)
            if path_pattern:
                pattern = path_pattern.replace("path:", "").strip().strip('"')
                # If it's a simple path (no wildcards), use it as scopePath for efficient API query
                if "**" not in pattern and "*" not in pattern and "?" not in pattern:
                    scope_path = pattern if pattern.startswith("/") else "/" + pattern
                    params["scopePath"] = scope_path

            # Only add version descriptor if branch is specified
            if branch:
                params["versionDescriptor.version"] = branch
                params["versionDescriptor.versionType"] = "branch"

            # Use longer timeout for recursive searches in large repos
            timeout = 120.0 if recursive else 30.0
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    url, headers=self._get_auth_header(), params=params
                )
                response.raise_for_status()
                data = response.json()

            items = data.get("value", [])
            results = []

            for item in items:
                # Skip folders
                if item.get("isFolder", False):
                    continue

                file_path = item.get("path", "").lstrip("/")
                file_name = file_path.split("/")[-1] if "/" in file_path else file_path

                # Apply path pattern filter (both simple and glob)
                if path_pattern:
                    pattern = (
                        path_pattern.replace("path:", "").strip().strip('"').lstrip("/")
                    )
                    # For simple path prefix, check if it starts with pattern
                    if (
                        "**" not in pattern
                        and "*" not in pattern
                        and "?" not in pattern
                    ):
                        if not file_path.startswith(pattern):
                            continue
                    # For glob patterns, use glob matching
                    else:
                        if not self._match_glob_pattern(file_path, pattern):
                            continue

                # Apply file pattern filter
                if file_pattern:
                    pattern = file_pattern.replace("file:", "").strip().strip('"')
                    if not self._match_pattern(file_name, pattern):
                        continue

                # Apply extension filter
                if extension:
                    ext = extension.replace("ext:", "").replace(".", "").strip()
                    if not file_name.endswith(f".{ext}"):
                        continue

                results.append(
                    {
                        "path": file_path,
                        "name": file_name,
                        "size": item.get("size", 0),
                        "objectId": item.get("objectId", ""),
                        "url": item.get("url", ""),
                    }
                )

                if len(results) >= max_results:
                    break

            logger.info(f"File search returned {len(results)} results")
            return results[:max_results]

        except httpx.HTTPError as e:
            logger.error(f"File search failed: {e}")
            raise
        except Exception as e:
            logger.error(f"File search error: {e}", exc_info=True)
            raise

    def _extract_preview(self, item: Dict[str, Any]) -> str:
        """Extract preview text from search result."""
        matches = item.get("matches", {})
        content = matches.get("content", [])

        if content and len(content) > 0:
            first_match = content[0]
            return first_match.get("charOffset", "")

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
        if not self._access_token:
            raise RuntimeError("Not authenticated")

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

    def _match_pattern(self, text: str, pattern: str) -> bool:
        """
        Match text against a pattern with wildcards (* and ?).

        Args:
            text: Text to match
            pattern: Pattern with * (any chars) and ? (single char)

        Returns:
            True if matches
        """
        import re

        # Convert glob pattern to regex
        regex_pattern = pattern.replace(".", r"\.")
        regex_pattern = regex_pattern.replace("*", ".*")
        regex_pattern = regex_pattern.replace("?", ".")
        regex_pattern = f"^{regex_pattern}$"
        return bool(re.match(regex_pattern, text, re.IGNORECASE))

    def _match_glob_pattern(self, path: str, pattern: str) -> bool:
        """
        Match path against glob pattern with ** support.

        Args:
            path: File path to match
            pattern: Glob pattern (e.g., "**/Doc**/Framework/**/Test*.txt")

        Returns:
            True if matches
        """
        import re

        # Convert glob to regex
        regex_pattern = pattern.replace(".", r"\.")
        regex_pattern = regex_pattern.replace("**", "§DOUBLESTAR§")
        regex_pattern = regex_pattern.replace("*", "[^/]*")
        regex_pattern = regex_pattern.replace("§DOUBLESTAR§", ".*")
        regex_pattern = regex_pattern.replace("?", ".")
        regex_pattern = f"^{regex_pattern}$"
        return bool(re.match(regex_pattern, path, re.IGNORECASE))

"""
Azure DevOps URI parser for multi-repository support.

URI Format: azdo://[<project>/<repo>/]<path>[?branch=<branch_name>]

Examples:
  azdo:/path/to/file.cpp              - Use default project, repo, and branch
  azdo:/path/to/file.cpp?branch=main  - Use default project, repo; override branch
  azdo://OS/os.2020/path/to/file.cpp  - Use specified project, repo; default branch
  azdo://OS/os.2020/path/to/file.cpp?branch=official/main  - Fully specified

Note: project and repo must appear together or both be absent.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


@dataclass
class AzdoUri:
    """Parsed Azure DevOps URI components."""

    path: str  # File path (always present, starts with /)
    project: Optional[str] = None  # Project name (optional)
    repository: Optional[str] = None  # Repository name (optional)
    branch: Optional[str] = None  # Branch name (optional)

    def has_repo_override(self) -> bool:
        """Check if this URI specifies a non-default repo."""
        return self.project is not None and self.repository is not None


def parse_azdo_uri(uri: str) -> Optional[AzdoUri]:
    """
    Parse an azdo:// URI into its components.

    Args:
        uri: URI string starting with 'azdo:' or 'azdo://'

    Returns:
        AzdoUri object if valid, None if invalid

    Examples:
        >>> parse_azdo_uri("azdo:/src/main.cpp")
        AzdoUri(path='/src/main.cpp', project=None, repository=None, branch=None)

        >>> parse_azdo_uri("azdo://OS/os.2020/src/main.cpp?branch=main")
        AzdoUri(path='/src/main.cpp', project='OS', repository='os.2020', branch='main')
    """
    if not uri:
        return None

    # Normalize: ensure we have azdo:// prefix for urlparse
    if uri.startswith("azdo://"):
        normalized = uri
    elif uri.startswith("azdo:/"):
        # azdo:/path -> treat as path only (no host/project/repo)
        normalized = "azdo:///" + uri[6:]  # Add empty host
    elif uri.startswith("azdo:"):
        # azdo:path -> treat as path only
        normalized = "azdo:///" + uri[5:]
    else:
        logger.warning(f"Invalid azdo URI - must start with 'azdo:': {uri}")
        return None

    try:
        parsed = urlparse(normalized)

        # Extract query parameters (branch)
        query_params = parse_qs(parsed.query)
        branch = query_params.get("branch", [None])[0]

        # Parse the path portion
        # For azdo://project/repo/path - netloc is project, path starts with /repo/...
        # For azdo:/path - netloc is empty, path is the file path

        if parsed.netloc:
            # Has project specified: azdo://project/repo/path
            project = parsed.netloc
            path_parts = parsed.path.split("/", 2)  # ['', 'repo', 'rest/of/path']

            if len(path_parts) < 2 or not path_parts[1]:
                logger.warning(
                    f"Invalid azdo URI - project specified but no repo: {uri}"
                )
                return None

            repository = path_parts[1]
            # File path is the rest, or root if nothing else
            file_path = "/" + path_parts[2] if len(path_parts) > 2 else "/"

            return AzdoUri(
                path=file_path, project=project, repository=repository, branch=branch
            )
        else:
            # No project/repo specified: azdo:/path
            file_path = parsed.path if parsed.path else "/"

            # Ensure path starts with /
            if not file_path.startswith("/"):
                file_path = "/" + file_path

            return AzdoUri(path=file_path, project=None, repository=None, branch=branch)

    except Exception as e:
        logger.error(f"Failed to parse azdo URI '{uri}': {e}")
        return None


def is_azdo_uri(text: str) -> bool:
    """Check if a string looks like an azdo:// URI."""
    return text.startswith("azdo:") if text else False


def extract_azdo_uris(text: str) -> list[str]:
    """
    Extract all azdo:// URIs from a text string.

    Args:
        text: Input text that may contain azdo URIs

    Returns:
        List of azdo URI strings found in the text
    """
    # Match azdo: followed by non-whitespace characters
    pattern = r"azdo:[^\s]+"
    return re.findall(pattern, text)

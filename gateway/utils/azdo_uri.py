"""
Azure DevOps URI parser for multi-repository support.

URI Format: azdo://[<project>/<repo>/]<path>[:<search_text>][?branch=<branch_name>]

The path is used as the scope filter for Azure DevOps Code Search API.
The search_text (after colon) is passed directly to Azure DevOps Code Search API.

Search Text Syntax (Azure DevOps API):
  - ext:xml           -> File Extension
  - file:config       -> File Name
  - file:*config.xml  -> File Name with wildcard
  - path:Services     -> Path keyword
  - class:MyClass     -> Code element (C#, Java)
  - (term1 OR term2)  -> Boolean logic
  - myTerm AND NOT ext:json -> Exclude pattern

Examples:
  azdo:/path:ext:xml                  - Search for XML files in /path
  azdo:/vm/compute:file:*manifest*    - Search for files with 'manifest' in name
  azdo:/:ext:cpp                      - Search entire repo for C++ files
  azdo://OS/os.2020/src:ext:h?branch=main  - Specific repo and branch

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

    path: str  # Path scope for search (always present, starts with /)
    search_text: Optional[str] = None  # Search text passed to Azure DevOps API
    project: Optional[str] = None  # Project name (optional)
    repository: Optional[str] = None  # Repository name (optional)
    branch: Optional[str] = None  # Branch name (optional)

    def has_repo_override(self) -> bool:
        """Check if this URI specifies a non-default repo."""
        return self.project is not None and self.repository is not None

    def is_search_query(self) -> bool:
        """Check if this URI contains a search query."""
        return self.search_text is not None


def parse_azdo_uri(uri: str) -> Optional[AzdoUri]:
    """
    Parse an azdo:// URI into its components.

    URI Format: azdo://[<project>/<repo>/]<path>[:<search_text>][?branch=<branch_name>]

    Args:
        uri: URI string starting with 'azdo:' or 'azdo://'

    Returns:
        AzdoUri object if valid, None if invalid

    Examples:
        >>> parse_azdo_uri("azdo:/src:ext:cpp")
        AzdoUri(path='/src', search_text='ext:cpp', project=None, repository=None, branch=None)

        >>> parse_azdo_uri("azdo://OS/os.2020/src:file:*manifest*?branch=main")
        AzdoUri(path='/src', search_text='file:*manifest*', project='OS', repository='os.2020', branch='main')

        >>> parse_azdo_uri("azdo:/path/to/file.cpp")  # Exact file path (no search)
        AzdoUri(path='/path/to/file.cpp', search_text=None, project=None, repository=None, branch=None)
    """
    if not uri:
        return None

    # Extract query parameters first (everything after ?)
    query_part = ""
    main_part = uri
    if "?" in uri:
        main_part, query_part = uri.split("?", 1)

    # Parse query parameters
    branch = None
    if query_part:
        query_params = parse_qs(query_part)
        branch = query_params.get("branch", [None])[0]

    # Extract search_text (everything after the colon separator)
    # Pattern: azdo:/path:searchText or azdo://project/repo/path:searchText
    # The colon separates path from search_text
    # Search text can contain spaces (e.g., "HCS ext:md", "keyword1 AND keyword2 ext:xml")
    search_text = None
    path_part = main_part

    # Find the colon that separates path from search_text
    # We look for a colon that is NOT part of "azdo:" or "azdo://" prefix
    # and is followed by search content (not another path segment)

    # Remove the azdo: prefix first to find the path:search separator
    if main_part.startswith("azdo://"):
        prefix = "azdo://"
        rest = main_part[7:]
    elif main_part.startswith("azdo:/"):
        prefix = "azdo:/"
        rest = main_part[6:]
    elif main_part.startswith("azdo:"):
        prefix = "azdo:"
        rest = main_part[5:]
    else:
        logger.warning(f"Invalid azdo URI - must start with 'azdo:': {uri}")
        return None

    # Find the last colon in the rest part (path:searchText separator)
    # But be careful - we want the colon that separates path from search, not colons within path
    # Strategy: Find a colon followed by a space or search keyword (ext:, file:, path:, class:, etc.)
    colon_idx = -1
    for i, ch in enumerate(rest):
        if ch == ":":
            # Check if this looks like a search separator
            # It should be followed by: space, letter, *, (, or "
            remaining = rest[i + 1 :].lstrip()  # Remove leading spaces after colon
            if remaining and (remaining[0].isalpha() or remaining[0] in '*("'):
                colon_idx = i
                break

    if colon_idx >= 0:
        path_part = prefix + rest[:colon_idx]
        search_text = rest[colon_idx + 1 :].strip()  # Strip spaces around search text
        if not search_text:
            search_text = None

    # Now parse the path_part for project/repo/path
    if path_part.startswith("azdo://"):
        # Has project: azdo://project/repo/path
        rest = path_part[7:]  # Remove "azdo://"
        parts = rest.split("/", 2)

        if len(parts) >= 2:
            project = parts[0]
            repository = parts[1]
            file_path = "/" + parts[2] if len(parts) > 2 and parts[2] else "/"
        else:
            logger.warning(f"Invalid azdo URI - project specified but no repo: {uri}")
            return None

        return AzdoUri(
            path=file_path,
            search_text=search_text,
            project=project,
            repository=repository,
            branch=branch,
        )

    elif path_part.startswith("azdo:/"):
        # No project: azdo:/path
        file_path = path_part[5:]  # Remove "azdo:"
        if not file_path.startswith("/"):
            file_path = "/" + file_path

        return AzdoUri(
            path=file_path,
            search_text=search_text,
            project=None,
            repository=None,
            branch=branch,
        )

    elif path_part.startswith("azdo:"):
        # No leading slash: azdo:path
        file_path = "/" + path_part[5:]

        return AzdoUri(
            path=file_path,
            search_text=search_text,
            project=None,
            repository=None,
            branch=branch,
        )

    else:
        logger.warning(f"Invalid azdo URI - must start with 'azdo:': {uri}")
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

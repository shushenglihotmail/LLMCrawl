"""Compatibility re-export.

Historically the embedded bridge host lived in this module.
The authoritative implementation now lives in
`wcd_bridge_mcp_server.windows_composition_bridge`.
"""

from __future__ import annotations

from .windows_composition_bridge import (  # noqa: F401
    PowerShellSession,
    QueryRequest,
    create_app,
)

__all__ = ["PowerShellSession", "QueryRequest", "create_app"]

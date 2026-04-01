"""Compatibility shim for the Windows Composition Bridge.

The bridge implementation has moved to the wheel-buildable MCP package at:

`mcp_servers/wcd_bridge_mcp_server/wcd_bridge_mcp_server/windows_composition_bridge.py`

This file remains so existing flows continue to work:
- `llmcrawl wcd-bridge ...` (imports `tools.windows_composition_bridge:app`)
- Gateway on-demand bridge startup (imports `create_app` via this shim)
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_wcd_bridge_mcp_server_on_path() -> None:
    # When running from the repo source tree, the MCP server package lives under:
    #   mcp_servers/wcd_bridge_mcp_server/
    repo_root = Path(__file__).resolve().parents[1]
    candidate = repo_root / "mcp_servers" / "wcd_bridge_mcp_server"
    if candidate.exists():
        sys.path.insert(0, str(candidate))


_ensure_wcd_bridge_mcp_server_on_path()


try:
    from wcd_bridge_mcp_server.windows_composition_bridge import app, main  # noqa: F401
except Exception as e:  # pragma: no cover
    raise ImportError(
        "Could not import the Windows Composition Bridge implementation from "
        "wcd_bridge_mcp_server. Ensure the WCD bridge MCP package is available "
        "(from source tree or installed wheel)."
    ) from e


if __name__ == "__main__":
    main()

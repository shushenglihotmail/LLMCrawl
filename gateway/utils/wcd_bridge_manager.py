"""
WCD Bridge Manager - on-demand Windows Composition Bridge lifecycle.

On first WCD tool call, starts the bridge (FastAPI + persistent PowerShell
session) in a daemon thread and keeps it running for the gateway's lifetime.

The bridge implementation lives in the MCP server package
(wcd_bridge_mcp_server.windows_composition_bridge) and is imported via the
tools/windows_composition_bridge.py compatibility shim.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Default listen address for the in-process bridge
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8005


def _detect_wcd_env() -> tuple[Optional[str], Optional[str]]:
    """Detect WCD configuration from environment variables.

    Returns (init_cmd, ps_command) — at most one will be set.
    If neither is available, WCD is not configured.
    """
    # Direct env vars (highest priority)
    ps_command = os.getenv("WIN_COMP_PS_COMMAND")
    if ps_command:
        return None, ps_command

    share_cmd = os.getenv("WIN_COMP_SHARE_CMD")
    if share_cmd:
        return share_cmd, None

    # Construct from WIN_COMP_PATH + arch
    win_comp_path = os.getenv("WIN_COMP_PATH")
    if win_comp_path:
        arch = os.getenv("WIN_COMP_ARCH", "amd64fre")
        full_cmd = os.path.join(
            win_comp_path,
            arch,
            "WindowsCompositionData",
            "SDK",
            "InteractViaPowerShell.cmd",
        )
        return full_cmd, None

    # WCDaaS local detection
    build_name = os.getenv("WCD_BUILD_NAME")
    if build_name:
        localappdata = os.environ.get("LOCALAPPDATA", "")
        wcdaas_base = os.path.join(localappdata, "Temp", "wcdaas")
        if os.path.isdir(wcdaas_base):
            # Use specific folder GUID if provided, else find most recent
            wcdaas_folder_guid = os.getenv("WCDAAS_FOLDER")
            try:
                if wcdaas_folder_guid:
                    target_folder = os.path.join(wcdaas_base, wcdaas_folder_guid)
                    ps1 = os.path.join(target_folder, "InteractViaPowershell.ps1")
                    if os.path.isfile(ps1):
                        folders = [wcdaas_folder_guid]
                    else:
                        logger.warning(
                            "WCDAAS_FOLDER %s missing InteractViaPowershell.ps1",
                            wcdaas_folder_guid,
                        )
                        folders = []
                else:
                    folders = [
                        f
                        for f in os.listdir(wcdaas_base)
                        if os.path.isdir(os.path.join(wcdaas_base, f))
                        and os.path.isfile(
                            os.path.join(wcdaas_base, f, "InteractViaPowershell.ps1")
                        )
                    ]
                if folders and not wcdaas_folder_guid:
                    folders.sort(
                        key=lambda f: os.path.getmtime(os.path.join(wcdaas_base, f)),
                        reverse=True,
                    )
                if folders:
                    ps1_path = os.path.join(
                        wcdaas_base, folders[0], "InteractViaPowershell.ps1"
                    )
                    branch = os.getenv("WCD_BRANCH", "rs_sparc_ctr_exp")
                    arch_short = os.getenv("WIN_COMP_ARCH", "amd64fre")
                    arch_short = arch_short.replace("fre", "").replace("chk", "")
                    cmd = (
                        f"& '{ps1_path}' "
                        f"-branch {branch} "
                        f"-buildName {build_name} "
                        f"-arch {arch_short}"
                    )
                    return None, cmd
            except Exception as exc:
                logger.warning("Failed scanning WCDaaS folders: %s", exc)

    return None, None


class WcdBridgeManager:
    """Manages the in-process Windows Composition Bridge."""

    def __init__(self) -> None:
        self.available: bool = False
        self._bridge_url: Optional[str] = None
        self._server: object = None  # uvicorn.Server
        self._thread: Optional[threading.Thread] = None
        self._init_cmd: Optional[str] = None
        self._ps_command: Optional[str] = None

    @property
    def bridge_url(self) -> Optional[str]:
        return self._bridge_url

    def detect(self) -> bool:
        """Check whether WCD environment is configured (no startup)."""
        init_cmd, ps_command = _detect_wcd_env()
        if init_cmd or ps_command:
            self._init_cmd = init_cmd
            self._ps_command = ps_command
            return True
        return False

    async def start(self) -> bool:
        """Start the bridge in a daemon thread. Blocks until healthy or timeout."""
        if self.available and self._bridge_url:
            return True

        if not self._init_cmd and not self._ps_command:
            if not self.detect():
                logger.info(
                    "WCD not configured — set WIN_COMP_PATH, "
                    "WIN_COMP_SHARE_CMD, WIN_COMP_PS_COMMAND, "
                    "or WCD_BUILD_NAME to enable"
                )
                return False

        # Set env vars so the bridge's lifespan picks them up
        if self._ps_command:
            os.environ["WIN_COMP_PS_COMMAND"] = self._ps_command
        elif self._init_cmd:
            os.environ["WIN_COMP_SHARE_CMD"] = self._init_cmd

        try:
            # Import the bridge via the existing compatibility shim
            _ensure_bridge_importable()
            import uvicorn
            from wcd_bridge_mcp_server.windows_composition_bridge import create_app

            app = create_app()
            config = uvicorn.Config(
                app,
                host=_DEFAULT_HOST,
                port=_DEFAULT_PORT,
                log_level="warning",
                access_log=False,
            )
            server = uvicorn.Server(config)
            self._server = server

            def _serve() -> None:
                server.run()

            self._thread = threading.Thread(target=_serve, daemon=True)
            self._thread.start()

            self._bridge_url = f"http://{_DEFAULT_HOST}:{_DEFAULT_PORT}"

            # Wait for the bridge to become healthy (PowerShell init can be slow)
            deadline = time.time() + 90
            last_err: Optional[Exception] = None
            while time.time() < deadline:
                try:
                    async with httpx.AsyncClient(timeout=2) as client:
                        r = await client.get(f"{self._bridge_url}/health")
                        if r.status_code == 200:
                            data = r.json()
                            if data.get("session_active", False):
                                self.available = True
                                logger.info(
                                    "WCD Bridge started — %s (session active)",
                                    self._bridge_url,
                                )
                                return True
                except Exception as e:
                    last_err = e
                await _async_sleep(1.0)

            logger.error("WCD Bridge did not become healthy within 90s: %s", last_err)
            return False

        except ImportError as e:
            logger.warning("Cannot import WCD bridge module: %s", e)
            return False
        except Exception as e:
            logger.error("Failed to start WCD Bridge: %s", e)
            return False

    def stop(self) -> None:
        """Signal the bridge to shut down."""
        if self._server is not None:
            self._server.should_exit = True  # type: ignore[attr-defined]
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._server = None
        self._bridge_url = None
        self.available = False
        logger.info("WCD Bridge stopped")


def _ensure_bridge_importable() -> None:
    """Ensure the MCP server package is on sys.path."""
    repo_root = Path(__file__).resolve().parents[2]
    candidate = repo_root / "mcp_servers" / "wcd_bridge_mcp_server"
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


async def _async_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_manager: Optional[WcdBridgeManager] = None


def get_wcd_bridge_manager() -> WcdBridgeManager:
    """Get or create the global WcdBridgeManager."""
    global _manager
    if _manager is None:
        _manager = WcdBridgeManager()
    return _manager

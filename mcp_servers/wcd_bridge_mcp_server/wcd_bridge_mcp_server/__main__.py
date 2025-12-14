"""CLI entry point for WCD Bridge MCP Server."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import threading
import time

import httpx
import uvicorn


def main() -> None:
    # IMPORTANT: Direct ALL logging to stderr to avoid corrupting MCP
    # protocol on stdout. MCP uses Content-Length framed JSON on stdout.
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,  # Ensure logs go to stderr, not stdout
    )

    parser = argparse.ArgumentParser(
        description=(
            "WCD Bridge MCP Server (stdio) - "
            "forwards to Windows Composition Bridge HTTP API"
        )
    )
    parser.add_argument(
        "--win-comp-path",
        type=str,
        default=os.getenv("WIN_COMP_PATH"),
        help=(
            "Base path to Windows build release folder "
            "(e.g., \\\\winbuilds\\release\\rs_sparc_ctr_exp\\29498.1001.251201-1700). "
            "The full CMD path is constructed as: "
            "<path>/<arch>/WindowsCompositionData/SDK/InteractViaPowerShell.cmd"
        ),
    )
    parser.add_argument(
        "--arch",
        type=str,
        default=os.getenv("WIN_COMP_ARCH", "amd64fre"),
        help=(
            "Architecture folder name (default: amd64fre). "
            "Examples: arm64fre, x86fre"
        ),
    )
    # WCDaaS (WCD-as-a-Service) options - alternative to local share
    parser.add_argument(
        "--use-wcdaas-local",
        action="store_true",
        help=(
            "Use existing WCDaaS local download from %%LOCALAPPDATA%%\\Temp\\wcdaas. "
            "Requires --branch and --build-name to load the correct database. "
            "Run the WCDaaS URL in a browser first to download the tools."
        ),
    )
    parser.add_argument(
        "--wcdaas-folder",
        type=str,
        default=os.getenv("WCDAAS_FOLDER"),
        help=(
            "Specific WCDaaS folder GUID to use "
            "(e.g., 9360d3ea-ecba-4a58-b7eb-0eb86d309b94). "
            "If not specified with --use-wcdaas-local, "
            "the most recent folder is used."
        ),
    )
    parser.add_argument(
        "--branch",
        type=str,
        default=os.getenv("WCD_BRANCH", "rs_sparc_ctr_exp"),
        help=(
            "WCD branch name (default: rs_sparc_ctr_exp). "
            "Required for --use-wcdaas-local."
        ),
    )
    parser.add_argument(
        "--build-name",
        type=str,
        default=os.getenv("WCD_BUILD_NAME"),
        help=(
            "WCD build name (e.g., 29503.1000.251209-1700). "
            "Required for --use-wcdaas-local."
        ),
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.getenv("WCD_BRIDGE_URL", "http://localhost:8005"),
        help=(
            "Base URL of the Windows Composition Bridge "
            "(default: http://localhost:8005)"
        ),
    )
    parser.add_argument(
        "--no-bridge",
        action="store_true",
        help=(
            "Do not start the embedded Windows Composition Bridge HTTP service. "
            "Use this only if you are running the bridge separately."
        ),
    )
    parser.add_argument(
        "--bridge-host",
        type=str,
        default=os.getenv("WCD_BRIDGE_LISTEN_HOST", "127.0.0.1"),
        help="Host to bind the embedded bridge (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--bridge-port",
        type=int,
        default=int(os.getenv("WCD_BRIDGE_LISTEN_PORT", "8005")),
        help="Port to bind the embedded bridge (default: 8005)",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=float(os.getenv("WCD_BRIDGE_TIMEOUT_S", "60")),
        help="HTTP timeout in seconds (default: 60)",
    )

    args = parser.parse_args()

    # Determine WCD initialization method
    if args.use_wcdaas_local:
        # Validate required parameters
        if not args.build_name:
            parser.error(
                "--build-name is required when using --use-wcdaas-local\n"
                "Example: --build-name 29503.1000.251209-1700"
            )

        # Use existing WCDaaS local download
        wcdaas_base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp", "wcdaas")
        if not os.path.isdir(wcdaas_base):
            wcdaas_url = (
                "https://wcdaas-pme.azurewebsites.net/default.aspx"
                f"?action=wcd&branch={args.branch}"
                f"&buildName={args.build_name}&arch=amd64"
            )
            parser.error(
                f"WCDaaS temp folder not found: {wcdaas_base}\n"
                "Run the WCDaaS URL in a browser first to download the tools:\n"
                f"  {wcdaas_url}"
            )

        if args.wcdaas_folder:
            # Use specific folder
            wcdaas_folder = os.path.join(wcdaas_base, args.wcdaas_folder)
        else:
            # Find most recent folder that contains InteractViaPowershell.ps1
            # (some folders may be empty/incomplete downloads)
            try:
                folders = [
                    f
                    for f in os.listdir(wcdaas_base)
                    if os.path.isdir(os.path.join(wcdaas_base, f))
                    and os.path.isfile(
                        os.path.join(wcdaas_base, f, "InteractViaPowershell.ps1")
                    )
                ]
                if not folders:
                    parser.error(
                        f"No valid WCDaaS folders found in {wcdaas_base}\n"
                        "Valid folders must contain InteractViaPowershell.ps1"
                    )
                # Sort by modification time, most recent first
                folders.sort(
                    key=lambda f: os.path.getmtime(os.path.join(wcdaas_base, f)),
                    reverse=True,
                )
                wcdaas_folder = os.path.join(wcdaas_base, folders[0])
                logging.info(
                    "Using most recent valid WCDaaS folder: %s "
                    "(found %d valid folders)",
                    folders[0],
                    len(folders),
                )
            except Exception as e:
                parser.error(f"Failed to find WCDaaS folders: {e}")

        # Use the .ps1 script with parameters (not the .cmd wrapper)
        ps1_path = os.path.join(wcdaas_folder, "InteractViaPowershell.ps1")
        if not os.path.isfile(ps1_path):
            parser.error(
                f"InteractViaPowershell.ps1 not found in {wcdaas_folder}\n"
                "The WCDaaS download may be incomplete or corrupted."
            )

        # Map arch format: amd64fre -> amd64
        arch_short = args.arch.replace("fre", "").replace("chk", "")

        # Construct the full PowerShell command with parameters
        # The script needs -branch, -buildName, -arch to load the correct database
        ps_command = (
            f"& '{ps1_path}' "
            f"-branch {args.branch} "
            f"-buildName {args.build_name} "
            f"-arch {arch_short}"
        )
        os.environ["WIN_COMP_PS_COMMAND"] = ps_command
        logging.info("Using WCDaaS local with command: %s", ps_command)
    elif args.win_comp_path:
        # Construct WIN_COMP_SHARE_CMD from --win-comp-path and --arch
        full_cmd_path = os.path.join(
            args.win_comp_path,
            args.arch,
            "WindowsCompositionData",
            "SDK",
            "InteractViaPowerShell.cmd",
        )
        os.environ["WIN_COMP_SHARE_CMD"] = full_cmd_path
        logging.info("Constructed WIN_COMP_SHARE_CMD: %s", full_cmd_path)
    elif not os.getenv("WIN_COMP_SHARE_CMD") and not args.no_bridge:
        parser.error(
            "One of the following is required (unless --no-bridge is used):\n"
            "  --win-comp-path: Path to Windows build release folder\n"
            "  --use-wcdaas-local: Use existing WCDaaS download from temp folder\n"
            "  WIN_COMP_SHARE_CMD environment variable"
        )

    async def _run() -> None:
        server: uvicorn.Server | None = None
        thread: threading.Thread | None = None

        base_url = args.base_url
        if not args.no_bridge:
            from .bridge_host import create_app

            # Always point MCP to the embedded bridge unless user disables it.
            base_url = f"http://{args.bridge_host}:{args.bridge_port}"

            # IMPORTANT: Redirect uvicorn logs to stderr to avoid corrupting
            # the MCP protocol on stdout. MCP uses Content-Length framing on
            # stdout, so any stray output breaks the protocol.
            config = uvicorn.Config(
                create_app(),
                host=args.bridge_host,
                port=args.bridge_port,
                log_level="warning",  # Reduce log noise
                access_log=False,  # Disable access logs that go to stdout
            )
            server = uvicorn.Server(config)

            def _serve() -> None:
                assert server is not None
                server.run()

            thread = threading.Thread(target=_serve, daemon=True)
            thread.start()

            # Wait for bridge to become responsive.
            # The PowerShell session initialization can take up to 60 seconds
            # (loading WCD tools from network share), so we allow 90 seconds total.
            deadline = time.time() + 90
            last_err: Exception | None = None
            while time.time() < deadline:
                try:
                    async with httpx.AsyncClient(timeout=2) as c:
                        r = await c.get(f"{base_url.rstrip('/')}/health")
                        if r.status_code == 200:
                            break
                except Exception as e:
                    last_err = e
                await asyncio.sleep(0.5)
            else:
                raise RuntimeError(
                    f"Embedded WCD bridge did not start or become healthy: {last_err}"
                )

        try:
            from .stdio_server import run_stdio_server

            await run_stdio_server(base_url=base_url, timeout_s=args.timeout_s)
        finally:
            if server is not None:
                server.should_exit = True
            if thread is not None:
                thread.join(timeout=5)

    asyncio.run(_run())


if __name__ == "__main__":
    main()

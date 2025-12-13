"""Windows Composition Bridge (WCD Bridge).

This is the FastAPI host service that runs on a Windows machine and bridges
access to Windows Composition Database tooling via a persistent PowerShell
session.

This module is intentionally compatible with the historical
`tools/windows_composition_bridge.py` entrypoint (which now acts as a thin
compatibility shim).
"""

from __future__ import annotations

import atexit
import logging
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("WinCompBridge")


class QueryRequest(BaseModel):
    query: str


class PowerShellSession:
    """Manages a persistent PowerShell session for Windows Composition Database.

    Uses a background thread for reading stdout to avoid blocking.
    Supports two initialization modes:
    1. init_cmd: Path to a .cmd/.ps1 file to execute (runs as `& "path"`)
    2. ps_command: Full PowerShell command string to execute directly
    """

    def __init__(
        self, init_cmd: Optional[str] = None, ps_command: Optional[str] = None
    ):
        self.init_cmd = init_cmd
        self.ps_command = ps_command
        self.process: Optional[subprocess.Popen] = None
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.reader_thread: Optional[threading.Thread] = None
        self._stop_reader = threading.Event()
        self._lock = threading.Lock()
        self._initialize_session()

    def _stdout_reader(self) -> None:
        """Background thread to read stdout and put lines in queue."""
        while not self._stop_reader.is_set():
            if not self.process or not self.process.stdout:
                break
            try:
                line = self.process.stdout.readline()
                if line:
                    self.output_queue.put(line)
                elif self.process.poll() is not None:
                    break
            except Exception:
                break

    def _initialize_session(self) -> None:
        """Initialize the PowerShell session."""
        # Determine startup command
        if self.ps_command:
            # Full PowerShell command provided (e.g., for WCDaaS local with params)
            startup_command = self.ps_command
            logger.info(
                "Initializing PowerShell session with command: %s", startup_command
            )
        elif self.init_cmd:
            # File path provided - wrap in & "path"
            if not os.path.exists(self.init_cmd) and not self.init_cmd.startswith(
                "\\\\"
            ):
                logger.warning("Initialization command not found at %s", self.init_cmd)
            startup_command = f'& "{self.init_cmd}"'
            logger.info("Initializing PowerShell session with %s...", self.init_cmd)
        else:
            logger.error("No initialization command configured")
            return

        try:
            shell_cmd = [
                "powershell.exe",
                "-NoExit",
                "-Command",
                startup_command,
            ]

            self.process = subprocess.Popen(
                shell_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
            )

            self._stop_reader.clear()
            self.reader_thread = threading.Thread(
                target=self._stdout_reader, daemon=True
            )
            self.reader_thread.start()

            handshake = "BRIDGE_READY"
            logger.info("Waiting for PowerShell session to initialize...")

            if self.process.stdin:
                self.process.stdin.write(f'Write-Output "{handshake}"\n')
                self.process.stdin.flush()

            start_time = time.time()
            timeout = 60
            while time.time() - start_time < timeout:
                try:
                    line = self.output_queue.get(timeout=1)
                    clean_line = line.strip()
                    if clean_line:
                        logger.info("Startup: %s", clean_line)
                    if clean_line == handshake:
                        logger.info(
                            "PowerShell Environment Ready (Handshake received)."
                        )
                        return
                except queue.Empty:
                    if self.process.poll() is not None:
                        logger.error("Process exited during initialization")
                        break

            logger.error("Timeout waiting for PowerShell initialization")

        except Exception as e:
            logger.error("Failed to start PowerShell session: %s", e)
            self.process = None

    def terminate(self) -> None:
        """Terminate the PowerShell session."""
        self._stop_reader.set()
        if self.reader_thread and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=2)

        if self.process:
            logger.info("Terminating PowerShell session...")
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("PowerShell didn't terminate, killing...")
                    self.process.kill()
                    self.process.wait(timeout=2)
            except Exception as e:
                logger.error("Error terminating PowerShell: %s", e)
            finally:
                self.process = None
            logger.info("PowerShell session terminated.")

    def run_query(self, script_block: str, timeout: int = 55) -> str:
        """Run a PS command and return the result string."""
        with self._lock:
            if not self.process or self.process.poll() is not None:
                logger.warning("PowerShell session died or not started. Restarting...")
                self._initialize_session()
                if not self.process:
                    return "Error: Could not establish PowerShell session."

            start_marker = "START_OF_RESPONSE"
            end_marker = "END_OF_RESPONSE"
            full_command = (
                f'Write-Output "{start_marker}"\n'
                f"{script_block} | Out-String -Width 4096\n"
                f'Write-Output "{end_marker}"\n'
            )

            try:
                while not self.output_queue.empty():
                    try:
                        self.output_queue.get_nowait()
                    except queue.Empty:
                        break

                if self.process.stdin:
                    self.process.stdin.write(full_command)
                    self.process.stdin.flush()

                output: list[str] = []
                started = False
                start_time = time.time()

                while time.time() - start_time < timeout:
                    try:
                        line = self.output_queue.get(timeout=1)
                        clean_line = line.strip()

                        if start_marker in clean_line:
                            started = True
                            continue

                        if end_marker in clean_line:
                            break

                        if started:
                            output.append(line)

                    except queue.Empty:
                        if self.process.poll() is not None:
                            logger.error("PowerShell process died during query")
                            return "Error: PowerShell process terminated unexpectedly"
                        continue
                else:
                    logger.error("Query timed out after %s seconds", timeout)
                    return f"Error: Query timed out after {timeout} seconds"

                return "".join(output)

            except Exception as e:
                logger.error("Error running query: %s", e)
                return f"Error executing query: {str(e)}"


session: Optional[PowerShellSession] = None


def cleanup_session() -> None:
    global session
    if session:
        session.terminate()


atexit.register(cleanup_session)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    global session
    share_cmd = os.getenv("WIN_COMP_SHARE_CMD")
    ps_command = os.getenv("WIN_COMP_PS_COMMAND")

    if not share_cmd and not ps_command:
        logger.error(
            "Either WIN_COMP_SHARE_CMD or WIN_COMP_PS_COMMAND "
            "environment variable must be set"
        )
        sys.exit(1)

    session = PowerShellSession(init_cmd=share_cmd, ps_command=ps_command)
    yield
    cleanup_session()


def create_app() -> FastAPI:
    application = FastAPI(title="Windows Composition Bridge", lifespan=lifespan)

    @application.post("/query")
    async def query_db(request: QueryRequest) -> dict:
        if not session:
            raise HTTPException(status_code=503, detail="Session not initialized")

        result = session.run_query(request.query)
        return {"result": result}

    @application.get("/health")
    async def health() -> dict:
        return {
            "status": "healthy",
            "session_active": session is not None and session.process is not None,
        }

    return application


app = create_app()


def _configure_logging_for_host() -> None:
    # Avoid clobbering app/user logging configuration.
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main() -> None:
    """Run the bridge as a standalone HTTP service."""
    _configure_logging_for_host()

    # Import here so importing this module doesn't require uvicorn.
    import uvicorn

    def signal_handler(sig: int, frame: object) -> None:
        logger.info("Received shutdown signal, cleaning up...")
        cleanup_session()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("Starting Windows Composition Bridge...")
    print("Make sure to set WIN_COMP_SHARE_CMD environment variable.")

    log_config = uvicorn.config.LOGGING_CONFIG
    access_fmt = (
        "%(asctime)s - %(levelname)s - %(client_addr)s - "
        '"%(request_line)s" %(status_code)s'
    )
    log_config["formatters"]["access"]["fmt"] = access_fmt
    log_config["formatters"]["access"]["datefmt"] = "%Y-%m-%d %H:%M:%S"

    uvicorn.run(app, host="0.0.0.0", port=8005, log_config=log_config)


if __name__ == "__main__":
    main()

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

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# =============================================================================
# Windows Composition Bridge
# =============================================================================
# This service runs on the Windows Host to bridge the gap between the
# Dockerized Gateway (Linux) and the Windows Composition Database (Host).
#
# Dependencies:
#   pip install fastapi uvicorn
#
# Usage:
#   $env:WIN_COMP_SHARE_CMD = "\\server\share\InteractViaPowerShell.cmd"
#   python tools/windows_composition_bridge.py
# =============================================================================

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("WinCompBridge")

app = FastAPI(title="Windows Composition Bridge")


class QueryRequest(BaseModel):
    query: str


class PowerShellSession:
    """
    Manages a persistent PowerShell session for Windows Composition Database.
    Uses a background thread for reading stdout to avoid blocking.
    """

    def __init__(self, init_cmd: str):
        self.init_cmd = init_cmd
        self.process: Optional[subprocess.Popen] = None
        self.output_queue: queue.Queue = queue.Queue()
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
                    # Process has exited
                    break
            except Exception:
                break

    def _initialize_session(self) -> None:
        """Initialize the PowerShell session."""
        if not os.path.exists(self.init_cmd) and not self.init_cmd.startswith("\\\\"):
            logger.warning(f"Initialization command not found at {self.init_cmd}")

        logger.info(f"Initializing PowerShell session with {self.init_cmd}...")

        startup_command = f'& "{self.init_cmd}"'

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

            # Start background reader thread
            self._stop_reader.clear()
            self.reader_thread = threading.Thread(
                target=self._stdout_reader, daemon=True
            )
            self.reader_thread.start()

            # Handshake to clear startup noise and ensure session is ready
            handshake = "BRIDGE_READY"
            logger.info("Waiting for PowerShell session to initialize...")

            if self.process.stdin:
                self.process.stdin.write(f'Write-Output "{handshake}"\n')
                self.process.stdin.flush()

            # Wait for handshake with timeout
            start_time = time.time()
            timeout = 60  # 60 second timeout for initialization
            while time.time() - start_time < timeout:
                try:
                    line = self.output_queue.get(timeout=1)
                    clean_line = line.strip()
                    if clean_line:
                        logger.info(f"Startup: {clean_line}")
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
            logger.error(f"Failed to start PowerShell session: {e}")
            self.process = None

    def terminate(self) -> None:
        """Terminate the PowerShell session."""
        # Stop the reader thread first
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
                logger.error(f"Error terminating PowerShell: {e}")
            finally:
                self.process = None
            logger.info("PowerShell session terminated.")

    def run_query(self, script_block: str, timeout: int = 55) -> str:
        """
        Runs a PS command and returns the result string.
        Uses non-blocking I/O with timeout to prevent deadlocks.
        """
        with self._lock:  # Serialize queries
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
                # Clear any pending output in queue
                while not self.output_queue.empty():
                    try:
                        self.output_queue.get_nowait()
                    except queue.Empty:
                        break

                if self.process.stdin:
                    self.process.stdin.write(full_command)
                    self.process.stdin.flush()

                output = []
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
                        # Check if process is still alive
                        if self.process.poll() is not None:
                            logger.error("PowerShell process died during query")
                            return "Error: PowerShell process terminated unexpectedly"
                        continue
                else:
                    logger.error(f"Query timed out after {timeout} seconds")
                    return f"Error: Query timed out after {timeout} seconds"

                return "".join(output)

            except Exception as e:
                logger.error(f"Error running query: {e}")
                return f"Error executing query: {str(e)}"


# Global session
session: Optional[PowerShellSession] = None


def cleanup_session() -> None:
    """Cleanup function to terminate PowerShell on exit."""
    global session
    if session:
        session.terminate()


# Register cleanup for normal exit
atexit.register(cleanup_session)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Lifespan context manager for startup/shutdown."""
    global session
    share_cmd = os.getenv("WIN_COMP_SHARE_CMD")
    if not share_cmd:
        logger.error("WIN_COMP_SHARE_CMD environment variable not set")
        sys.exit(1)

    session = PowerShellSession(share_cmd)
    yield
    # Shutdown
    cleanup_session()


app = FastAPI(title="Windows Composition Bridge", lifespan=lifespan)


@app.post("/query")
async def query_db(request: QueryRequest) -> dict:
    if not session:
        raise HTTPException(status_code=503, detail="Session not initialized")

    result = session.run_query(request.query)
    return {"result": result}


@app.get("/health")
async def health() -> dict:
    return {
        "status": "healthy",
        "session_active": session is not None and session.process is not None,
    }


if __name__ == "__main__":
    # Handle Ctrl+C gracefully
    def signal_handler(sig: int, frame: object) -> None:
        logger.info("Received shutdown signal, cleaning up...")
        cleanup_session()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("Starting Windows Composition Bridge...")
    print("Make sure to set WIN_COMP_SHARE_CMD environment variable.")

    # Configure uvicorn with timestamp in access log
    log_config = uvicorn.config.LOGGING_CONFIG
    access_fmt = (
        "%(asctime)s - %(levelname)s - %(client_addr)s - "
        '"%(request_line)s" %(status_code)s'
    )
    log_config["formatters"]["access"]["fmt"] = access_fmt
    log_config["formatters"]["access"]["datefmt"] = "%Y-%m-%d %H:%M:%S"

    uvicorn.run(app, host="0.0.0.0", port=8005, log_config=log_config)

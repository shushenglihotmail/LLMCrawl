import logging
import os
import subprocess
import sys
import time
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
    """

    def __init__(self, init_cmd: str):
        self.init_cmd = init_cmd
        self.process: Optional[subprocess.Popen] = None
        self._initialize_session()

    def _initialize_session(self) -> None:
        """Initialize the PowerShell session."""
        if not os.path.exists(self.init_cmd) and not self.init_cmd.startswith("\\\\"):
            logger.warning(f"Initialization command not found at {self.init_cmd}")

        logger.info(f"Initializing PowerShell session with {self.init_cmd}...")

        # Construct the startup command
        # We use -Command to run the script and remain in the session
        # On Windows Host, we can run .cmd files directly or via cmd /c, but usually
        # if it's a .cmd that launches PowerShell, we might need to be careful.
        # Assuming the .cmd sets up environment and drops into PS.

        # If init_cmd is a .cmd file, we should probably run it via cmd.exe
        # But we want to interact with the PowerShell session it spawns.
        # If the .cmd file ends with "powershell -NoExit ...", then running it will start PS.

        # Strategy: Run the command as is.
        startup_command = f'& "{self.init_cmd}"'

        try:
            # Use powershell.exe (Windows PowerShell) or pwsh.exe (Core)
            # Default to powershell.exe for maximum compatibility with legacy WCD tools
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
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding="utf-8",  # Windows might need cp1252 or utf-8 depending on config
            )

            # Give it a moment to load the DB
            time.sleep(5)
            logger.info("PowerShell Environment Ready.")

        except Exception as e:
            logger.error(f"Failed to start PowerShell session: {e}")
            self.process = None

    def run_query(self, script_block: str) -> str:
        """
        Runs a PS command and returns JSON string.
        """
        if not self.process or self.process.poll() is not None:
            logger.warning("PowerShell session died or not started. Restarting...")
            self._initialize_session()
            if not self.process:
                return "Error: Could not establish PowerShell session."

        end_marker = "END_OF_RESPONSE"
        # Force output to JSON, compress to single line, print marker
        full_command = (
            f"{script_block} | ConvertTo-Json -Depth 5 -Compress; "
            f'Write-Output "{end_marker}"\n'
        )

        try:
            if self.process.stdin:
                self.process.stdin.write(full_command)
                self.process.stdin.flush()

            output = []
            while True:
                if not self.process.stdout:
                    break

                line = self.process.stdout.readline()
                if end_marker in line:
                    break
                if line == "":
                    break
                output.append(line.strip())

            return "".join(output)

        except Exception as e:
            logger.error(f"Error running query: {e}")
            return f"Error executing query: {str(e)}"


# Global session
session: Optional[PowerShellSession] = None


@app.on_event("startup")
async def startup_event() -> None:
    global session
    share_cmd = os.getenv("WIN_COMP_SHARE_CMD")
    if not share_cmd:
        logger.error("WIN_COMP_SHARE_CMD environment variable not set")
        sys.exit(1)

    session = PowerShellSession(share_cmd)


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
    print("Starting Windows Composition Bridge...")
    print("Make sure to set WIN_COMP_SHARE_CMD environment variable.")
    uvicorn.run(app, host="0.0.0.0", port=8005)

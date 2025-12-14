"""Test MCP client to verify stdio protocol works correctly.

This simulates what VS Code does when communicating with an MCP server.
Uses simple newline-delimited JSON (same as local_access_mcp_server).
"""

import json
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional


def send_message(proc: subprocess.Popen[bytes], message: Dict[str, Any]) -> None:
    """Send a newline-delimited JSON message to the process."""
    content = json.dumps(message) + "\n"

    print(f"[CLIENT] Sending: {content.strip()[:200]}...")
    if proc.stdin:
        proc.stdin.write(content.encode("utf-8"))
        proc.stdin.flush()


def read_message(
    proc: subprocess.Popen[bytes], timeout: float = 30.0
) -> Optional[Dict[str, Any]]:
    """Read a newline-delimited JSON message from the process."""
    start_time = time.time()

    while True:
        if time.time() - start_time > timeout:
            print("[CLIENT] Timeout waiting for response")
            return None

        if not proc.stdout:
            return None
        line = proc.stdout.readline()
        if not line:
            print("[CLIENT] EOF while reading")
            return None

        line_str = line.decode("utf-8", errors="replace").strip()
        if not line_str:
            continue  # Skip empty lines

        print(f"[CLIENT] Received: {line_str[:200]}...")

        try:
            result: Dict[str, Any] = json.loads(line_str)
            return result
        except json.JSONDecodeError as e:
            print(f"[CLIENT] Invalid JSON: {e} - line was: {line_str[:100]}")
            continue


def stderr_reader(proc: subprocess.Popen[bytes]) -> None:
    """Read stderr in background thread."""
    while True:
        if not proc.stderr:
            break
        line = proc.stderr.readline()
        if not line:
            break
        print(f"[STDERR] {line.decode('utf-8', errors='replace').rstrip()}")


def main() -> None:
    # Start the MCP server
    cmd = [
        sys.executable,
        "-m",
        "wcd_bridge_mcp_server",
        "--use-wcdaas-local",
        "--build-name",
        "29503.1000.251209-1700",
        "--branch",
        "rs_sparc_ctr_exp",
        "--arch",
        "amd64",
    ]

    print(f"[CLIENT] Starting MCP server: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Start stderr reader thread
    stderr_thread = threading.Thread(target=stderr_reader, args=(proc,), daemon=True)
    stderr_thread.start()

    try:
        # Wait a moment for server to start
        print("[CLIENT] Waiting for server to initialize...")
        time.sleep(2)

        # Send initialize request
        print("\n[CLIENT] === Sending initialize request ===")
        send_message(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            },
        )

        # Read response
        print("[CLIENT] Waiting for initialize response...")
        response = read_message(proc, timeout=120)  # Long timeout for bridge init

        if response:
            print("\n[CLIENT] === Got initialize response ===")
            print(json.dumps(response, indent=2))

            # Send initialized notification
            print("\n[CLIENT] === Sending initialized notification ===")
            send_message(
                proc, {"jsonrpc": "2.0", "method": "notifications/initialized"}
            )

            # Request tools list
            print("\n[CLIENT] === Sending tools/list request ===")
            send_message(
                proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            )

            response = read_message(proc, timeout=30)
            if response:
                print("\n[CLIENT] === Got tools/list response ===")
                print(json.dumps(response, indent=2))
            else:
                print("[CLIENT] No response to tools/list")
        else:
            print("[CLIENT] No response to initialize!")

    except KeyboardInterrupt:
        print("\n[CLIENT] Interrupted")
    finally:
        print("\n[CLIENT] Terminating server...")
        proc.terminate()
        proc.wait(timeout=5)
        print("[CLIENT] Done")


if __name__ == "__main__":
    main()

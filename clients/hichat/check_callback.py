import logging
import socket
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("callback_test")


class TestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Success! Localhost callback is working.</h1>")
        print("\n\n[SUCCESS] Received request from browser!\n")


def check_port(port=54545):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("127.0.0.1", port))
    sock.close()
    return result == 0


def main():
    port = 49861
    print(f"--- Callback Server Diagnostic ---")

    if check_port(port):
        print(f"WARNING: Port {port} is ALREADY IN USE.")
        print("Please stop any running HiChat instances or python processes.")
        return

    print(f"Starting test server on http://127.0.0.1:{port}...")
    try:
        server = HTTPServer(("127.0.0.1", port), TestHandler)

        url = f"http://localhost:{port}/callback?test=1"
        print(f"\n1. Opening browser to: {url}")
        print(
            "   If you see a 'Success' message in the browser, local networking is fine."
        )
        print(
            "   If the browser fails to connect, we have a local firewall/proxy issue."
        )

        webbrowser.open(url)

        print("\nWaiting for request... (Press Ctrl+C to stop)")
        server.handle_request()  # Handle one request

    except KeyboardInterrupt:
        print("\nCancelled.")
    except Exception as e:
        print(f"\nError starting server: {e}")


if __name__ == "__main__":
    main()

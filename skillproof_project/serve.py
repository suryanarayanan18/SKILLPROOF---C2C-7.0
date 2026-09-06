#!/usr/bin/env python3
"""
SkillProof Local Development Server
Serves the Google Stitch frontend prototype on port 3000.
No external dependencies or build steps required.
"""

import http.server
import socketserver
import os
import sys
import webbrowser

PORT = 3000
DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, format, *args):
        # Clean terminal logging
        sys.stdout.write(f"[{self.log_date_time_string()}] {format % args}\n")
        sys.stdout.flush()

def main():
    if not os.path.exists(DIRECTORY):
        print(f"Error: Frontend directory '{DIRECTORY}' not found.")
        sys.exit(1)

    # Allow port reuse
    socketserver.TCPServer.allow_reuse_address = True

    try:
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            url = f"http://localhost:{PORT}"
            print("=" * 60)
            print("  SkillProof — Verifying Skills Without Certificates")
            print("  Code2Create 7.0 Hackathon Prototype")
            print("=" * 60)
            print(f"  Frontend serving from: {DIRECTORY}")
            print(f"  Access local app at:   {url}")
            print("  Press Ctrl+C to stop the server.")
            print("=" * 60)

            # Try opening browser automatically
            try:
                webbrowser.open(url)
            except Exception:
                pass

            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer gracefully stopped.")
        sys.exit(0)
    except OSError as e:
        if e.errno == 98 or e.errno == 10048:
            print(f"\nError: Port {PORT} is already in use. Please terminate existing processes or change PORT.")
        else:
            print(f"\nServer error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

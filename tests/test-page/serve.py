#!/usr/bin/env python3
"""Local test server for the ClaudeCodeBrowser feature test page.

Serves this directory on http://localhost:8899 plus a few API endpoints the
page uses to exercise network logging:

  GET/POST /api/echo        -> 200, echoes method, query and body as JSON
  GET      /api/slow?ms=N   -> 200 after N ms (default 1500)
  GET      /api/status/<n>  -> responds with HTTP status <n> (e.g. 404, 500)

Usage:  python tests/test-page/serve.py [port]
"""
import json
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api(self, method):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/api/echo":
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode() if length else None
            return self._json(200, {"method": method, "query": query, "body": body})
        if url.path == "/api/slow":
            ms = int(query.get("ms", 1500))
            time.sleep(min(ms, 10000) / 1000)
            return self._json(200, {"slept_ms": ms})
        if url.path.startswith("/api/status/"):
            code = int(url.path.rsplit("/", 1)[-1])
            return self._json(code, {"status": code})
        return False

    def do_GET(self):
        if self.path.startswith("/api/"):
            if self._api("GET") is False:
                self._json(404, {"error": "unknown endpoint"})
            return
        super().do_GET()

    def do_POST(self):
        if self._api("POST") is False:
            self._json(404, {"error": "unknown endpoint"})

    def log_message(self, fmt, *args):
        sys.stderr.write("[test-server] " + (fmt % args) + "\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    print(f"Serving ClaudeCodeBrowser test page on http://localhost:{port}/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()

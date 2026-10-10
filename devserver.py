"""Local dev server that mimics the Vercel routes, for running the app offline.

Serves the static frontend from /public and the analysis endpoint at
/api/analyze, using the exact same `engine` code the serverless function uses.

Usage:
    python devserver.py            # serves on http://localhost:8000
    python devserver.py 5000       # custom port
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine.api import analyze, popular, scan_watchlist  # noqa: E402

PUBLIC = os.path.join(_ROOT, "public")

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quieter console
        pass

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self, rel_path: str) -> None:
        if rel_path in ("", "/"):
            rel_path = "index.html"
        rel_path = rel_path.lstrip("/")
        full = os.path.normpath(os.path.join(PUBLIC, rel_path))
        if not full.startswith(PUBLIC) or not os.path.isfile(full):
            self._json(404, {"error": "not found"})
            return
        ext = os.path.splitext(full)[1]
        ctype = _CONTENT_TYPES.get(ext, "application/octet-stream")
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/analyze":
            query = parse_qs(parsed.query)
            if query.get("list") == ["1"]:
                self._json(200, {"popular": popular()})
                return
            timeframe = (query.get("timeframe", ["daily"])[0] or "daily").strip()
            if query.get("watch") == ["1"]:
                self._json(200, {"watch": scan_watchlist(timeframe=timeframe)})
                return
            ticker = (query.get("ticker", [""])[0] or "").strip()
            if not ticker:
                self._json(400, {"error": "Provide ?ticker=SYMBOL"})
                return
            try:
                self._json(200, analyze(ticker, timeframe=timeframe))
            except Exception as exc:  # noqa: BLE001
                self._json(500, {"error": f"Analysis failed: {exc}"})
            return
        self._static(parsed.path)


def main(argv=None):
    argv = argv or sys.argv[1:]
    port = int(argv[0]) if argv else 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Grok stock-signal app running at http://localhost:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()

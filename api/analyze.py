"""Vercel Python serverless function: GET /api/analyze?ticker=RELIANCE

Returns the full BUY/SELL/HOLD analysis as JSON. Pure stdlib; imports the
`engine` package from the project root.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Make the project-root `engine` package importable from the /api function.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine.api import analyze, popular, scan_watchlist  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (Vercel/stdlib naming)
        query = parse_qs(urlparse(self.path).query)
        ticker = (query.get("ticker", [""])[0] or "").strip()

        if query.get("list") == ["1"]:
            self._send(200, {"popular": popular()})
            return

        timeframe = (query.get("timeframe", ["daily"])[0] or "daily").strip()

        if query.get("watch") == ["1"]:
            self._send(200, {"watch": scan_watchlist(timeframe=timeframe)})
            return

        if not ticker:
            self._send(400, {"error": "Provide ?ticker=SYMBOL (e.g. RELIANCE)."})
            return

        try:
            result = analyze(ticker, timeframe=timeframe)
            self._send(200, result)
        except Exception as exc:  # noqa: BLE001 - surface a clean error to the UI
            self._send(500, {"error": f"Analysis failed: {exc}"})

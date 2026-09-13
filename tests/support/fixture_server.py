"""A real HTTP server on loopback that speaks the OpenAI-compatible protocol.

It stands in for LM Studio, vLLM or llama.cpp behind a `[providers.NAME]` block,
so the config-only path goes through a real socket and a real client, and is held
to the same contract as the named providers [PRV-12]. It plays back exchanges in
order and keeps each request it received.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import netguard
from cassettes import Captured


class FixtureServer:
    def __init__(self, exchanges: list[dict[str, Any]] | None = None) -> None:
        self.queue = list(exchanges or [])
        self.requests: list[Captured] = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = int(self.httpd.server_address[1])
        serve = self.httpd.serve_forever
        self.thread = threading.Thread(target=serve, args=(0.01,), daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    @property
    def address(self) -> str:
        return f"127.0.0.1:{self.port}"

    def __enter__(self) -> FixtureServer:
        netguard.allow("127.0.0.1", self.port)
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        netguard.disallow("127.0.0.1", self.port)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.do_POST()

            def do_POST(self) -> None:
                length = int(self.headers.get("content-length", 0))
                body = json.loads(self.rfile.read(length) or b"null")
                server.requests.append(Captured(self.path, dict(self.headers), body))
                exchange = server.queue.pop(0)
                self.send_response(exchange["status"])
                for key, value in exchange["headers"].items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    for part in exchange["body"].split("\n\n"):
                        if not part:
                            continue
                        time.sleep(exchange.get("delay_s", 0.0))
                        self.wfile.write((part + "\n\n").encode())
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the client cancelled: exactly what the cancel test wants

            def log_message(self, format: str, *args: Any) -> None:
                pass

        return Handler

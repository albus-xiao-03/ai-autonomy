"""FakeAnthropic: a loopback contract fake of the Messages endpoint (skeleton).

Reached through the real SDK's `base_url` (docs/engine-plan.md §8.2). M0 checks the credential and
version headers and returns one minimal valid Message; M5 adds structured output, refusals,
`max_tokens`, 429 with `retry-after`, 5xx errors and timeouts.
"""

import itertools
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Self


class FakeAnthropic:
    def __init__(self, api_key: str, reply_text: str = "{}") -> None:
        self.api_key = api_key
        self.reply_text = reply_text
        self.requests: list[dict[str, Any]] = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}"

    def start(self) -> Self:
        self._thread.start()
        return self

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _message(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            number = next(self._ids)
        return {
            "id": f"msg_fake_{number:06d}",
            "type": "message",
            "role": "assistant",
            "model": request.get("model", "fake-model"),
            "content": [{"type": "text", "text": self.reply_text}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def _send(self, status: int, body: dict[str, Any]) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("request-id", "req_fake")
                self.end_headers()
                self.wfile.write(data)

            def _error(self, status: int, kind: str, message: str) -> None:
                self._send(status, {"type": "error", "error": {"type": kind, "message": message}})

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                with fake._lock:
                    fake.requests.append(
                        {
                            "path": self.path,
                            "headers": {k.lower(): v for k, v in self.headers.items()},
                            "body": body,
                        }
                    )
                if self.path.split("?", 1)[0] != "/v1/messages":
                    self._error(404, "not_found_error", f"no route {self.path}")
                elif self.headers.get("x-api-key") != fake.api_key:
                    self._error(401, "authentication_error", "invalid x-api-key")
                elif not self.headers.get("anthropic-version"):
                    self._error(400, "invalid_request_error", "missing anthropic-version")
                else:
                    self._send(200, fake._message(body))

        return Handler

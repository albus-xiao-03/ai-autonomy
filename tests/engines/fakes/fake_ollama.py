"""FakeOllama: a loopback HTTP server implementing the subset of `/api/chat` the engine uses.

Scriptable per request (docs/engine-plan.md §8.2): a valid choice, malformed JSON, a wrong schema, a
delay, or a hang (released when the server closes). Unscripted requests get a valid choice:
for every property of the request's `format` schema that has an `enum`, its first value.
"""

import json
import threading
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Self

DEFAULT_MODEL = "qwen3-1.7b-q8"


@dataclass(frozen=True)
class Reply:
    kind: str  # valid | malformed | wrong_schema | delay | hang
    content: dict[str, Any] | None = None
    delay_s: float = 0.0


def valid(content: dict[str, Any] | None = None) -> Reply:
    return Reply("valid", content)


def malformed() -> Reply:
    return Reply("malformed")


def wrong_schema() -> Reply:
    return Reply("wrong_schema")


def delay(seconds: float, content: dict[str, Any] | None = None) -> Reply:
    return Reply("delay", content, seconds)


def hang() -> Reply:
    return Reply("hang")


def default_choice(request: dict[str, Any]) -> dict[str, Any]:
    schema = request.get("format")
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    choice = {
        name: spec["enum"][0]
        for name, spec in properties.items()
        if isinstance(spec, dict) and spec.get("enum")
    }
    return choice or {"option_id": "wait"}


class FakeOllama:
    """Usage: `with FakeOllama() as fake: fake.script(valid(), hang()); ... fake.url`."""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self.requests: list[dict[str, Any]] = []
        self._script: deque[Reply] = deque()
        self._lock = threading.Lock()
        self._release = threading.Event()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host!s}:{port}"

    def script(self, *replies: Reply) -> None:
        with self._lock:
            self._script.extend(replies)

    def start(self) -> Self:
        self._thread.start()
        return self

    def close(self) -> None:
        self._release.set()
        self._server.shutdown()
        self._server.server_close()

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _next_reply(self, request: dict[str, Any]) -> Reply:
        with self._lock:
            self.requests.append(request)
            return self._script.popleft() if self._script else valid()

    def _chat_body(self, text: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "created_at": "2026-01-01T00:00:00Z",
            "message": {"role": "assistant", "content": text},
            "done": True,
            "done_reason": "stop",
            "total_duration": 1_000_000,
            "load_duration": 0,
            "prompt_eval_count": 1,
            "prompt_eval_duration": 1,
            "eval_count": 1,
            "eval_duration": 1,
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
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                if self.path == "/api/version":
                    self._send(200, {"version": "0.0.0-fake"})
                elif self.path == "/api/tags":
                    self._send(200, {"models": [{"name": fake.model, "model": fake.model}]})
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self) -> None:
                if self.path != "/api/chat":
                    self._send(404, {"error": "not found"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    request = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    self._send(400, {"error": "invalid JSON body"})
                    return
                reply = fake._next_reply(request)
                if reply.kind == "hang":
                    fake._release.wait()
                    return
                if reply.kind == "delay" and fake._release.wait(reply.delay_s):
                    return
                if reply.kind == "malformed":
                    text = '{"option_id": '
                elif reply.kind == "wrong_schema":
                    text = json.dumps({"unexpected": True})
                else:
                    text = json.dumps(reply.content or default_choice(request))
                self._send(200, fake._chat_body(text))

        return Handler

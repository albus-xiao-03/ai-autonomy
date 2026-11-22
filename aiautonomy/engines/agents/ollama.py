"""Loopback-only Ollama chat client shared by the resident and local-mayor routes.

The endpoint must be a loopback address: residents never use remote inference (LOCAL-01, LOCAL-02).
Calls run in a worker thread so the asyncio loop keeps serving other requests.
"""

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from aiautonomy.engines.agents.clients import register_client

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


class OllamaError(RuntimeError):
    """Ollama is unreachable or returned something unusable."""


class OllamaClient:
    def __init__(self, route: str, endpoint: str = DEFAULT_ENDPOINT) -> None:
        host = urllib.parse.urlparse(endpoint).hostname or ""
        if host not in LOOPBACK_HOSTS:
            raise OllamaError(f"Ollama endpoint must be loopback, got {host!r}")
        register_client(route)
        self.endpoint = endpoint.rstrip("/")

    def _post(self, path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        request = urllib.request.Request(
            self.endpoint + path,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                result: dict[str, Any] = json.loads(reply.read())
                return result
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise OllamaError(str(error)) from error

    def _get(self, path: str, timeout: float) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(self.endpoint + path, timeout=timeout) as reply:
                result: dict[str, Any] = json.loads(reply.read())
                return result
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise OllamaError(str(error)) from error

    async def models(self, wait_s: float = 2.0) -> list[str]:
        data = await asyncio.to_thread(self._get, "/api/tags", wait_s)
        return [str(m.get("name")) for m in data.get("models", [])]

    async def chat_json(
        self,
        model: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        wait_s: float = 30.0,
        num_predict: int = 200,
    ) -> dict[str, Any]:
        """One non-streaming chat call constrained to `schema`; returns the parsed JSON object."""
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user + " /no_think"},
            ],
            "stream": False,
            "think": False,
            "format": schema,
            "keep_alive": "30m",
            "options": {"temperature": 0.4, "num_predict": num_predict, "num_ctx": 4096},
        }
        data = await asyncio.to_thread(self._post, "/api/chat", body, wait_s)
        try:
            parsed: dict[str, Any] = json.loads(data["message"]["content"].strip())
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise OllamaError("model returned non-JSON content") from error
        return parsed

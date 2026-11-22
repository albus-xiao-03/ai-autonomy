"""Only one Ollama model is in memory at a time (SPEC.md Section 2)."""

import asyncio
import json
import time
from typing import Any

import pytest

from aiautonomy.engines.agents import ollama
from aiautonomy.engines.agents.ollama import OllamaClient


class FakeOllama:
    """Stands in for Ollama's HTTP API: tracks loaded models and overlapping chats."""

    def __init__(self, loaded: list[str]) -> None:
        self.loaded = list(loaded)
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0

    def get(self, path: str, _wait: float) -> dict[str, Any]:
        assert path == "/api/ps"
        return {"models": [{"name": name} for name in self.loaded]}

    def post(self, path: str, body: dict[str, Any], _wait: float) -> dict[str, Any]:
        if path == "/api/generate" and body.get("keep_alive") == 0:
            self.loaded.remove(body["model"])
            self.calls.append("unload " + body["model"])
            return {}
        assert path == "/api/chat"
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        assert self.loaded in ([], [body["model"]]), f"two models in memory: {self.loaded}"
        if body["model"] not in self.loaded:
            self.loaded.append(body["model"])
        self.calls.append("chat " + body["model"])
        time.sleep(0.02)
        self.active -= 1
        return {"message": {"content": json.dumps({"ok": True})}}


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeOllama:
    server = FakeOllama(loaded=["qwen3:8b"])
    monkeypatch.setattr(OllamaClient, "_get", server.get)
    monkeypatch.setattr(OllamaClient, "_post", server.post)
    monkeypatch.setattr(ollama, "_model_lock", None)
    return server


def chat(model: str) -> Any:
    return OllamaClient("resident").chat_json(model, "system", "user", {"type": "object"})


def test_switching_model_unloads_the_previous_one(fake: FakeOllama) -> None:
    asyncio.run(chat("qwen3:1.7b"))
    assert fake.calls == ["unload qwen3:8b", "chat qwen3:1.7b"]
    assert fake.loaded == ["qwen3:1.7b"]


def test_same_model_is_not_reloaded(fake: FakeOllama) -> None:
    asyncio.run(chat("qwen3:8b"))
    assert fake.calls == ["chat qwen3:8b"]


def test_concurrent_mayor_and_resident_calls_take_turns(fake: FakeOllama) -> None:
    async def both() -> None:
        await asyncio.gather(chat("qwen3:8b"), chat("qwen3:1.7b"), chat("qwen3:8b"))

    asyncio.run(both())
    assert fake.max_active == 1
    assert len(fake.loaded) == 1

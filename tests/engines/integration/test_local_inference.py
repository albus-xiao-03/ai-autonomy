"""Resident inference stays local with the engine-configured model (LOCAL-01/02/06)."""

import asyncio
import json
from pathlib import Path
from typing import Any

import anthropic
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aiautonomy.engines.agents.ollama import OllamaClient, same_model
from aiautonomy.engines.api.brain import router
from aiautonomy.engines.mayor.providers import ApiProvider
from aiautonomy.engines.residents.llm import LocalResidentProvider, ResidentBatch
from aiautonomy.engines.sim.config import InferenceSettings, load_inference_settings
from tests.engines.conftest import DUMMY_ANTHROPIC_API_KEY
from tests.engines.fakes.fake_anthropic import FakeAnthropic
from tests.engines.fakes.fake_ollama import FakeOllama, valid
from tests.engines.hybrid_support import hybrid_client, incident, launch, post_tick, routes

BATCH = ResidentBatch(
    batch_id="rbatch-000001",
    residents=[{"id": 1, "activity": "home", "mood": 40.0}, {"id": 4, "activity": "work",
                                                             "mood": 20.0}],
    offered=["follow_routine", "go_home", "peaceful_protest", "road_blockade"],
    context={"tick": 3},
)  # fmt: skip


@pytest.mark.req("HW-02", "LOCAL-01")
def test_models_come_from_the_engine_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_inference_settings()
    assert (settings.mayor_local_model, settings.resident_model) == ("qwen3:8b", "qwen3:1.7b")
    monkeypatch.setenv("AIA_RESIDENT_MODEL", "qwen3-1.7b-q8")
    assert load_inference_settings().resident_model == "qwen3-1.7b-q8"
    assert same_model("qwen3-1.7b-q8:latest", "qwen3-1.7b-q8")
    assert not same_model("qwen3:1.7b", "qwen3:8b")


@pytest.mark.req("LOCAL-01", "LOCAL-03")
def test_the_configured_installed_model_answers_through_local_ollama() -> None:
    answer = {"decisions": [{"id": 1, "action": "go_home", "thought": "Long day."},
                            {"id": 4, "action": "road_blockade", "thought": "Enough."},
                            {"id": 9, "action": "go_home", "thought": "not in the batch"},
                            {"id": 1, "action": "vandalism", "thought": "duplicate"}]}  # fmt: skip
    with FakeOllama(model="qwen3:1.7b") as fake:
        fake.script(valid(answer))
        provider = LocalResidentProvider("qwen3:1.7b", 5.0, endpoint=fake.url)
        reply = asyncio.run(provider.decide(BATCH))
    assert reply.error is None
    assert reply.decisions == {1: ("go_home", "Long day."), 4: ("road_blockade", "Enough.")}
    [request] = fake.requests
    assert request["model"] == "qwen3:1.7b"
    assert request["think"] is False
    assert request["keep_alive"] == "5m"
    items = request["format"]["properties"]["decisions"]["items"]["properties"]
    assert items["action"]["enum"] == BATCH.offered
    assert items["id"]["enum"] == [1, 4]


@pytest.mark.req("LOCAL-01", "LOCAL-02")
def test_a_missing_model_falls_back_without_any_remote_call() -> None:
    with FakeOllama(model="qwen3-1.7b-q8") as fake:
        provider = LocalResidentProvider("qwen3:1.7b", 5.0, endpoint=fake.url)
        reply = asyncio.run(provider.decide(BATCH))
    assert reply.decisions == {}
    assert reply.error is not None
    assert "not installed" in reply.error
    assert fake.requests == []  # no chat was attempted
    assert fake.gets == ["/api/tags"]


@pytest.mark.req("LOCAL-01", "HW-02")
def test_a_pinned_digest_must_match() -> None:
    with FakeOllama(model="qwen3:1.7b", digest="a" * 64) as fake:
        pinned = LocalResidentProvider("qwen3:1.7b", 5.0, digest="b" * 64, endpoint=fake.url)
        reply = asyncio.run(pinned.decide(BATCH))
        assert reply.error is not None
        assert "digest" in reply.error
        assert fake.requests == []
        matching = LocalResidentProvider("qwen3:1.7b", 5.0, digest="a" * 64, endpoint=fake.url)
        assert asyncio.run(matching.decide(BATCH)).error is None


@pytest.mark.req("LOCAL-01")
def test_remote_endpoints_are_refused_for_residents() -> None:
    provider = LocalResidentProvider("qwen3:1.7b", 5.0, endpoint="http://ollama.example.com:11434")
    reply = asyncio.run(provider.decide(BATCH))
    assert reply.error is not None
    assert "loopback" in reply.error


def legacy_client(monkeypatch: pytest.MonkeyPatch, installed: bool) -> TestClient:
    async def check(*_args: object, **_kwargs: object) -> tuple[bool, str]:
        return installed, "" if installed else "model qwen3:1.7b is not installed"

    async def chat(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return {"decisions": [{"id": 1, "action": "go_home", "thought": "tired"}]}

    monkeypatch.setattr(OllamaClient, "installed", check)
    monkeypatch.setattr(OllamaClient, "chat_json", chat)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.mark.req("LOCAL-01", "LOCAL-02")
def test_the_legacy_resident_route_uses_only_the_configured_local_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = legacy_client(monkeypatch, installed=True)
    body = {"residents": [{"id": 1, "mood": 30}], "context": {}}
    other = client.post("/api/brain/residents", json=body | {"model": "claude-opus-5-5"})
    assert (other.status_code, other.json()["error"]["code"]) == (422, "model_not_configured")
    ok = client.post("/api/brain/residents", json=body | {"model": "qwen3:1.7b"}).json()
    assert (ok["model"], ok["decisions"][0]["action"]) == ("qwen3:1.7b", "go_home")
    missing = legacy_client(monkeypatch, installed=False)
    reply = missing.post("/api/brain/residents", json=body).json()
    assert reply["decisions"] == []
    assert "not installed" in reply["error"]
    mayor = client.post("/api/brain/mayor", json={"backend": "local", "model": "qwen3:32b",
                                                  "allowed": ["outreach"]})  # fmt: skip
    assert mayor.json()["error"]["code"] == "model_not_configured"


@pytest.mark.req("LOCAL-06", "MAY-07", "HOST-08")
def test_an_api_mayor_never_carries_resident_inference(tmp_path: Path) -> None:
    reply = '{"action": "HOLD", "statement": "ok"}'
    with (
        FakeAnthropic(DUMMY_ANTHROPIC_API_KEY, reply_text=reply) as api,
        FakeOllama(model="qwen3:1.7b") as ollama,
        hybrid_client(tmp_path) as client,
    ):
        store = client.app.state.runs  # type: ignore[attr-defined]
        store.inference = InferenceSettings(
            mayor_local_model="qwen3:8b", mayor_api_model="claude-test",
            resident_model="qwen3:1.7b", mayor_wait_s=5.0, resident_wait_s=5.0,
            resident_batch_max=8,
        )  # fmt: skip
        store.providers = lambda backend, settings: ApiProvider(
            "claude-test",
            client_factory=lambda: anthropic.AsyncAnthropic(
                base_url=api.url, api_key=DUMMY_ANTHROPIC_API_KEY, max_retries=0
            ),
        )
        store.resident_providers = lambda settings: LocalResidentProvider(
            settings.resident_model, settings.resident_wait_s, endpoint=ollama.url
        )
        run = launch(client, mayor_backend="api")
        llm = run["residents"]["llm_ids"]
        answer = [{"id": rid, "action": "go_home", "thought": "home"} for rid in llm]
        ollama.script(valid({"decisions": answer}))
        severe = [incident("game-s", "protest", 90, 1)]
        post_tick(client, run, 1, incidents=severe, routes=routes("game-s", {"pd-a1-1": 3}))
        observed = [{"id": rid, "activity": "home", "mood": 30.0} for rid in llm]
        body = {"run_epoch": 1, "tick": 1, "residents": observed}
        assert client.post(f"/api/runs/{run['run_id']}/residents", json=body).status_code == 202
        for tick in range(2, 7):
            outcome = post_tick(client, run, tick, incidents=severe).json()
            if tick == 3:
                assert {a["fallback"] for a in outcome["resident_actions"]} == {False}
    mayor_calls = [json.dumps(r["body"]) for r in api.requests]
    assert len(mayor_calls) == 1
    assert "autonomous mayor" in mayor_calls[0]
    assert [r["model"] for r in ollama.requests] == ["qwen3:1.7b"]  # residents went local
    assert "decide what residents" in ollama.requests[0]["messages"][0]["content"]

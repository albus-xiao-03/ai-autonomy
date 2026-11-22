"""Brain routes used by the browser game: baseline mayor, paid-API interlock, residents offline."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aiautonomy.engines.agents.ollama import OllamaClient, OllamaError
from aiautonomy.engines.api.brain import router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_baseline_mayor_mediates_protest(client: TestClient) -> None:
    reply = client.post(
        "/api/brain/mayor",
        json={
            "backend": "baseline",
            "prompt": {"satisfaction": 60, "incident": {"kind": "protest"}},
            "allowed": ["outreach", "mediate"],
            "fallback": "outreach",
        },
    ).json()
    assert reply["order"] == "mediate"
    assert reply["fallback_used"] is False
    assert reply["score_before"] == 60


def test_api_backend_refused_without_interlock(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AIA_ALLOW_PAID_API", raising=False)
    reply = client.post(
        "/api/brain/mayor",
        json={"backend": "api", "allowed": ["outreach"], "fallback": "outreach"},
    ).json()
    assert reply["fallback_used"] is True
    assert reply["order"] == "outreach"
    assert "paid API disabled" in reply["error"]


def test_score_after_is_recorded(client: TestClient) -> None:
    decision = client.post(
        "/api/brain/mayor",
        json={"backend": "baseline", "prompt": {"satisfaction": 50}, "allowed": ["outreach"]},
    ).json()
    updated = client.post(
        "/api/brain/mayor/outcome", json={"id": decision["id"], "score_after": 64}
    ).json()
    assert updated["score_after"] == 64


def test_residents_return_empty_when_ollama_unreachable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def offline(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise OllamaError("offline")

    monkeypatch.setattr(OllamaClient, "chat_json", offline)
    reply = client.post(
        "/api/brain/residents", json={"residents": [{"id": 1, "mood": 20}], "context": {}}
    ).json()
    assert reply["decisions"] == []
    assert reply["error"] == "offline"


def test_remote_ollama_endpoint_rejected() -> None:
    with pytest.raises(OllamaError):
        OllamaClient("resident", endpoint="http://example.com:11434")

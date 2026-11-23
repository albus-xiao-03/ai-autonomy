"""Brain routes used by the browser game: baseline mayor, paid-API interlock, residents offline."""

from pathlib import Path

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

    async def installed(*_args: object, **_kwargs: object) -> tuple[bool, str]:
        return True, ""

    monkeypatch.setattr(OllamaClient, "installed", installed)
    monkeypatch.setattr(OllamaClient, "chat_json", offline)
    reply = client.post(
        "/api/brain/residents", json={"residents": [{"id": 1, "mood": 20}], "context": {}}
    ).json()
    assert reply["decisions"] == []
    assert reply["error"] == "offline"


def test_remote_ollama_endpoint_rejected() -> None:
    with pytest.raises(OllamaError):
        OllamaClient("resident", endpoint="http://example.com:11434")


@pytest.mark.req("ARCH-02")
def test_legacy_decisions_are_scoped_per_app_and_run() -> None:
    def fresh() -> TestClient:
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    one, two = fresh(), fresh()
    body = {"backend": "baseline", "prompt": {"satisfaction": 50}, "allowed": ["outreach"]}
    assert [one.post("/api/brain/mayor", json=body).json()["id"] for _ in range(2)] == [0, 1]
    assert two.post("/api/brain/mayor", json=body).json()["id"] == 0  # no shared global log
    assert len(one.get("/api/brain/decisions").json()) == 2
    assert len(two.get("/api/brain/decisions").json()) == 1
    entry = one.get("/api/brain/decisions").json()[1]
    assert (entry["run_id"], entry["decision_id"]) == ("legacy", "legacy-1")


@pytest.mark.req("ARCH-02")
def test_legacy_outcomes_are_validated_and_idempotent(client: TestClient) -> None:
    body = {"backend": "baseline", "prompt": {"satisfaction": 50}, "allowed": ["outreach"]}
    decision = client.post("/api/brain/mayor", json=body).json()
    outcome = {"id": decision["id"], "score_after": 61}
    assert client.post("/api/brain/mayor/outcome", json=outcome).json()["score_after"] == 61
    assert client.post("/api/brain/mayor/outcome", json=outcome).status_code == 200  # repost
    conflict = client.post("/api/brain/mayor/outcome", json=outcome | {"score_after": 40})
    assert (conflict.status_code, conflict.json()["error"]["code"]) == (409, "outcome_conflict")
    missing = client.post("/api/brain/mayor/outcome", json={"id": 99, "score_after": 1})
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "unknown_decision")
    other_run = client.post("/api/brain/mayor/outcome", json=outcome | {"run_id": "r2"})
    assert other_run.status_code == 404
    out_of_range = client.post("/api/brain/mayor/outcome", json=outcome | {"score_after": 140})
    assert out_of_range.status_code == 422


@pytest.mark.req("SIM-05")
def test_legacy_decisions_can_name_a_live_hybrid_run(tmp_path: Path) -> None:
    from tests.engines.hybrid_support import hybrid_client, launch

    with hybrid_client(tmp_path) as hybrid:
        run = launch(hybrid)
        body = {"backend": "baseline", "prompt": {"satisfaction": 50}, "allowed": ["outreach"],
                "run_id": run["run_id"], "run_epoch": 1}  # fmt: skip
        entry = hybrid.post("/api/brain/mayor", json=body).json()
        assert (entry["run_id"], entry["id"]) == (run["run_id"], 0)
        scoped = hybrid.get("/api/brain/decisions", params={"run_id": run["run_id"]}).json()
        assert [item["decision_id"] for item in scoped] == ["legacy-0"]
        assert hybrid.get("/api/brain/decisions").json() == []
        stale = hybrid.post("/api/brain/mayor", json=body | {"run_epoch": 2})
        assert stale.json()["error"]["code"] == "stale_epoch"
        hybrid.post(f"/api/runs/{run['run_id']}/reset", json={"run_epoch": 1})
        ended = hybrid.post("/api/brain/mayor", json=body)
        assert ended.json()["error"]["code"] == "run_ended"
        log = (tmp_path / "runs" / run["run_id"] / "decisions.jsonl").read_text()
        assert '"legacy_mayor"' in log

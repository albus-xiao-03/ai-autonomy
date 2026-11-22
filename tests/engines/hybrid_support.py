"""Helpers for hybrid-run tests: launching runs and posting game observations over HTTP."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from httpx import Response

from aiautonomy.engines.api.app import create_app
from aiautonomy.engines.api.session import SessionOptions
from aiautonomy.engines.core.paths import repo_root

UNITS = ("ems-mgh-1", "ems-mgh-2", "fd-e4-engine", "fd-e4-ladder", "pd-a1-1", "pd-a1-2")


def map_ref(map_id: str = "boston-template", revision: int = 1) -> dict[str, Any]:
    path = repo_root() / "data" / "maps" / map_id / f"r{revision}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    return {"id": map_id, "revision": revision, "sha256": document["sha256"]}


@contextmanager
def hybrid_client(tmp_path: Path) -> Iterator[TestClient]:
    options = SessionOptions(runs_dir=tmp_path / "runs", maps_dir=tmp_path / "maps")
    with TestClient(create_app(options, serve_frontend=False)) as client:
        yield client


def launch(client: TestClient, **fields: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "map": map_ref(),
        "population": 6,
        "llm_ratio_bp": 5000,
        "mayor_backend": "baseline",
        "seed": 7,
        "duration": 120,
        "disruptions": {"automatic": False, "scheduled": []},
    }
    body |= fields
    response = client.post("/api/runs", json=body)
    assert response.status_code == 201, response.text
    handle: dict[str, Any] = response.json()
    return handle


def observation(run: dict[str, Any], tick: int, **fields: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"run_epoch": run["run_epoch"], "tick": tick, "satisfaction": 80.0}
    return body | fields


def post_tick(client: TestClient, run: dict[str, Any], tick: int, **fields: Any) -> Response:
    return client.post(f"/api/runs/{run['run_id']}/ticks", json=observation(run, tick, **fields))


def advance(client: TestClient, run: dict[str, Any], start: int, stop: int) -> list[dict[str, Any]]:
    """Post empty observations for ticks start..stop and return the outcomes."""
    outcomes = []
    for tick in range(start, stop + 1):
        response = post_tick(client, run, tick)
        assert response.status_code == 200, response.text
        outcomes.append(response.json())
    return outcomes


def routes(incident: str, travel: dict[str, int | None]) -> list[dict[str, Any]]:
    return [
        {"unit_id": unit, "incident_id": incident, "reachable": ticks is not None,
         "travel_ticks": ticks}
        for unit, ticks in sorted(travel.items())
    ]  # fmt: skip


def incident(
    incident_id: str, kind: str, severity: int, opened: int, status: str = "active", **fields: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": incident_id,
        "kind": kind,
        "severity": severity,
        "opened_tick": opened,
        "status": status,
        "x": 360.0,
        "z": 560.0,
        "district": "Downtown",
    }
    return body | fields

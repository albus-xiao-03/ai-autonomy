"""The seven disruption types: catalog, sources, timing, recovery and validation (contract §8)."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from aiautonomy.engines.core.datafiles import DataFileError, load_data_file
from aiautonomy.engines.core.paths import repo_root
from aiautonomy.engines.hybrid.catalogs import DisruptionCatalog
from tests.engines.hybrid_support import (
    hybrid_client,
    incident,
    launch,
    map_ref,
    post_tick,
    routes,
)

SEVEN = ["traffic", "outage", "gas_leakage", "flood", "storm", "snowstorm", "heavy_rain"]
GOV = {"x": 411.0, "z": 479.0}  # Government Center
CITY_HALL = {"x": 600.42, "z": 634.524}
ALL_NEAR = {"pd-a1-1": 3, "pd-a1-2": 4, "fd-e4-engine": 4, "fd-e4-ladder": 5,
            "ems-mgh-1": 6, "ems-mgh-2": 7}  # fmt: skip


def scheduled(kind: str, at_tick: int, **fields: Any) -> dict[str, Any]:
    return {"type": kind, "at_tick": at_tick} | GOV | fields


def interventions(tmp_path: Path, run: dict[str, Any]) -> list[dict[str, Any]]:
    path = tmp_path / "runs" / run["run_id"] / "interventions.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.req("EVT-01", "EVT-02")
def test_catalog_lists_exactly_the_seven_types(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        catalog = client.get("/api/catalogs/disruptions").json()
        kinds = client.get("/api/catalogs/incidents").json()
    assert [entry["id"] for entry in catalog["types"]] == SEVEN
    needs = {entry["kind"]: entry["needs"] for entry in kinds["kinds"]}
    for entry in catalog["types"]:
        assert entry["incident"]["kind"] == entry["id"]
        assert entry["incident"]["needs"] == needs[entry["id"]]  # one source of truth
    data = yaml.safe_load((repo_root() / "data/catalogs/disruptions.v1.yaml").read_text())
    extra = dict(data["types"][0], id="earthquake")
    broken = tmp_path / "disruptions.v1.yaml"
    broken.write_text(yaml.safe_dump(data | {"types": [*data["types"], extra]}))
    with pytest.raises(DataFileError):
        load_data_file(broken, DisruptionCatalog)


def run_until(
    client: TestClient, run: dict[str, Any], start: int, stop: int, active: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    outcomes = []
    for tick in range(start, stop + 1):
        response = post_tick(client, run, tick, incidents=active)
        assert response.status_code == 200, response.text
        outcomes.append(response.json())
    return outcomes


@pytest.mark.req("EVT-01", "EVT-02", "EVT-05", "CUSTOM-07")
@pytest.mark.parametrize("kind", SEVEN)
def test_each_disruption_starts_spawns_dispatch_and_ends(tmp_path: Path, kind: str) -> None:
    with hybrid_client(tmp_path) as client:
        catalog = {e["id"]: e for e in client.get("/api/catalogs/disruptions").json()["types"]}
        spec = catalog[kind]
        run = launch(client, duration=400, disruptions={
            "automatic": False, "scheduled": [scheduled(kind, 3, duration_ticks=20)]})  # fmt: skip
        [record] = run["scheduled_disruptions"]
        assert (record["start_tick"], record["end_tick"], record["status"]) == (3, 23, "scheduled")
        assert record["incident_id"] == "inc-000001"
        assert record["effects"] == spec["effects"]
        quiet = post_tick(client, run, 1).json()
        assert quiet["disruptions_started"] == []
        announced = post_tick(client, run, 2).json()
        assert [r["id"] for r in announced["disruptions_started"]] == [record["id"]]
        # The game spawns the incident from tick 3 with the engine's incident id.
        spawned = incident("inc-000001", kind, record["incident"]["severity"], 3,
                           disruption_id=record["id"], **GOV)  # fmt: skip
        outcome = post_tick(client, run, 3, incidents=[spawned],
                            routes=routes("inc-000001", ALL_NEAR)).json()  # fmt: skip
        needs = record["incident"]["needs"]
        sent = {a["department"] for a in outcome["assignments"]}
        assert sent == {department for department, count in needs.items() if count}
        mode = spec["recovery"]["mode"]
        if mode == "on_clear":
            # Resolving the incident ends the disruption at once.
            resolved = [dict(spawned, status="resolved", severity=0)]
            cleared = post_tick(client, run, 4, incidents=resolved).json()
            assert [r["id"] for r in cleared["disruptions_ended"]] == [record["id"]]
            assert cleared["disruptions_ended"][0]["status"] == "ended"
        else:
            last_active = 22 if mode == "on_duration" else 22 + spec["recovery"]["gradual_ticks"]
            outcomes = run_until(client, run, 4, last_active, [spawned])
            ended = [o["tick"] for o in outcomes if o["disruptions_ended"]]
            assert ended == [last_active]  # announced the tick before its effects end
        entries = interventions(tmp_path, run)
        assert [(e["source"], e["record"]["id"]) for e in entries] == [("scheduled", record["id"])]


@pytest.mark.req("CUSTOM-01", "CUSTOM-07")
def test_injection_starts_two_ticks_later_and_is_idempotent(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        run = launch(client)
        for tick in (1, 2, 3):
            post_tick(client, run, tick)
        url = f"/api/runs/{run['run_id']}/disruptions"
        body = {"run_epoch": 1, "request_id": "ui-1", "disruption": {"type": "flood"} | GOV}
        first = client.post(url, json=body)
        assert first.status_code == 201
        record = first.json()["disruption"]
        assert (record["source"], record["start_tick"], record["status"]) == (
            "injected",
            5,
            "scheduled",
        )
        again = client.post(url, json=body)
        assert again.status_code == 200
        assert again.json() == {"disruption": record, "duplicate": True}
        changed = client.post(url, json=body | {"disruption": {"type": "storm"} | GOV})
        assert changed.json()["error"]["code"] == "request_conflict"
        far_spec = {"type": "storm", "x": 5000, "z": 0}
        far = client.post(url, json={"run_epoch": 1, "request_id": "ui-2", "disruption": far_spec})
        assert far.json()["error"]["code"] == "out_of_bounds"
        past_spec = {"type": "storm", "at_tick": 4} | GOV
        past = client.post(
            url, json={"run_epoch": 1, "request_id": "ui-3", "disruption": past_spec}
        )
        assert past.json()["error"]["code"] == "invalid_start_tick"
        stale = client.post(url, json=body | {"run_epoch": 2})
        assert stale.json()["error"]["code"] == "stale_epoch"
        retired = client.post(url, json={"run_epoch": 1, "request_id": "ui-4",
                                         "disruption": {"type": "earthquake"} | GOV})  # fmt: skip
        assert retired.status_code == 422
        announced = post_tick(client, run, 4).json()
        assert [r["id"] for r in announced["disruptions_started"]] == [record["id"]]
        [entry] = interventions(tmp_path, run)
        assert (entry["source"], entry["accepted_after_tick"], entry["request_id"]) == (
            "injected", 3, "ui-1")  # fmt: skip
        assert entry["spec"]["type"] == "flood"


@pytest.mark.req("EVT-02", "EVAL-02")
def test_automatic_disruptions_are_seeded_and_hidden_until_announced(tmp_path: Path) -> None:
    def automatic(seed: int) -> list[tuple[int, int, str, float, float]]:
        with hybrid_client(tmp_path / f"s{seed}") as client:
            run = launch(client, seed=seed, duration=600,
                         disruptions={"automatic": True, "scheduled": []})  # fmt: skip
            assert run["scheduled_disruptions"] == []  # automatic ones stay hidden
            seen = []
            for tick in range(1, 601):
                outcome = post_tick(client, run, tick).json()
                seen += [(tick, r["start_tick"], r["type"], r["x"], r["z"])
                         for r in outcome["disruptions_started"]]  # fmt: skip
            return seen

    first, again, other = automatic(4), automatic(4), automatic(5)
    assert first
    assert first == again
    assert first != other
    for announced_at, start, kind, _, _ in first:
        assert announced_at == start - 1
        assert kind in SEVEN


@pytest.mark.req("CUSTOM-01")
def test_scheduled_disruptions_are_validated_at_launch(tmp_path: Path) -> None:
    base: dict[str, Any] = {"map": map_ref(), "population": 6, "llm_ratio_bp": 5000}
    cases = [
        ({"type": "storm"} | GOV, 422, "invalid_start_tick"),
        (scheduled("storm", 1), 422, "invalid_start_tick"),
        (scheduled("storm", 5) | {"x": -4000.0}, 422, "out_of_bounds"),
        (scheduled("blizzard", 5), 422, "invalid_body"),
    ]
    with hybrid_client(tmp_path) as client:
        for spec, status, code in cases:
            body = base | {"disruptions": {"automatic": False, "scheduled": [spec]}}
            response = client.post("/api/runs", json=body)
            assert (response.status_code, response.json()["error"]["code"]) == (status, code)


@pytest.mark.req("EVT-02")
def test_disruption_incidents_must_match_their_disruption(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        run = launch(client, disruptions={"automatic": False,
                                          "scheduled": [scheduled("gas_leakage", 3)]})  # fmt: skip
        early = post_tick(client, run, 1, incidents=[incident("inc-000001", "gas_leakage", 60, 1)])
        assert early.json()["error"]["code"] == "unknown_disruption_incident"
        post_tick(client, run, 1)
        post_tick(client, run, 2)
        wrong_kind = post_tick(client, run, 3, incidents=[incident("inc-000001", "flood", 60, 3)])
        assert wrong_kind.json()["error"]["code"] == "incident_kind_mismatch"
        wrong_owner = post_tick(client, run, 3, incidents=[
            incident("inc-000001", "gas_leakage", 60, 3, disruption_id="dis-000009")])  # fmt: skip
        assert wrong_owner.json()["error"]["code"] == "disruption_mismatch"
        game_owned = post_tick(client, run, 3, incidents=[
            incident("game-1", "crime", 30, 3, disruption_id="dis-000001")])  # fmt: skip
        assert game_owned.json()["error"]["code"] == "disruption_mismatch"
        made_up = post_tick(client, run, 3, incidents=[incident("inc-000077", "storm", 50, 3)])
        assert made_up.json()["error"]["code"] == "unknown_disruption_incident"
        ok = post_tick(client, run, 3, incidents=[incident("inc-000001", "gas_leakage", 60, 3)])
        assert ok.status_code == 200


@pytest.mark.req("HOST-05", "EVT-03")
def test_an_outage_over_city_hall_takes_the_mayor_office_offline(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        outage = {"type": "outage", "at_tick": 3, "duration_ticks": 4} | CITY_HALL
        far = {"type": "outage", "at_tick": 3, "duration_ticks": 4, "x": -300.0, "z": 700.0}
        run = launch(client, disruptions={"automatic": False, "scheduled": [outage, far]})
        engine_run = client.app.state.runs.get(run["run_id"])  # type: ignore[attr-defined]
        assert [engine_run.mayor_office_outage(t) for t in (2, 3, 6, 7)] == [
            False,
            True,
            True,
            False,
        ]
        storm_spec = scheduled("storm", 3) | CITY_HALL
        storm = launch(client, disruptions={"automatic": False, "scheduled": [storm_spec]})
        storm_run = client.app.state.runs.get(storm["run_id"])  # type: ignore[attr-defined]
        assert not storm_run.mayor_office_outage(4)  # only outages take the office down

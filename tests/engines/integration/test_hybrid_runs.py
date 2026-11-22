"""Hybrid run lifecycle over HTTP (docs/contract.md §3, §4, §10, §11)."""

import json
from pathlib import Path

import pytest

from tests.engines.hybrid_support import (
    UNITS,
    advance,
    hybrid_client,
    incident,
    launch,
    map_ref,
    post_tick,
    routes,
)


@pytest.mark.req("RES-06", "CITY-04")
def test_launch_pins_the_map_and_assigns_exactly_three_of_six(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        run = launch(client)
        again = launch(client)
        assert run["map"] == map_ref()
        assert run["residents"]["population"] == 6
        assert run["residents"]["llm_count"] == 3
        assert len(run["residents"]["llm_ids"]) == 3
        assert run["residents"]["llm_ids"] == again["residents"]["llm_ids"]  # same seed
        assert run["run_id"] != again["run_id"]
        assert [unit["id"] for unit in run["units"]] == list(UNITS)
        assert {unit["state"] for unit in run["units"]} == {"available"}
        assert run["controller"] == "baseline"
        assert run["contract_version"] == 1
        manifest = json.loads((tmp_path / "runs" / run["run_id"] / "manifest.json").read_text())
        assert manifest["kind"] == "boston_hybrid"
        assert manifest["map"] == map_ref()
        assert manifest["launch"]["population"] == 6
        assert "ANTHROPIC" not in json.dumps(manifest)


@pytest.mark.req("SIM-03", "END-01")
def test_ticks_advance_until_the_duration_then_the_run_ends(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        run = launch(client, duration=3)
        outcomes = advance(client, run, 1, 3)
        assert [o["effective_tick"] for o in outcomes] == [2, 3, 4]
        assert [o["status"] for o in outcomes] == ["running", "running", "completed"]
        late = post_tick(client, run, 4)
        assert late.status_code == 409
        assert late.json()["error"]["code"] == "run_ended"
        run_dir = tmp_path / "runs" / run["run_id"]
        ticks = [json.loads(line) for line in (run_dir / "ticks.jsonl").read_text().splitlines()]
        assert [line["tick"] for line in ticks] == [0, 1, 2, 3]
        assert ticks[-1]["hash"] == outcomes[-1]["state_hash"]
        assert len((run_dir / "observations.jsonl").read_text().splitlines()) == 3
        report = json.loads((run_dir / "final_report.json").read_text())
        assert (report["outcome"], report["final_tick"]) == ("completed", 3)
        manifest = json.loads((run_dir / "manifest.json").read_text())
        assert manifest["status"] == "completed"


@pytest.mark.req("ARCH-02", "SIM-05")
def test_retries_are_idempotent_and_conflicts_are_refused(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        run = launch(client)
        first = post_tick(client, run, 1)
        assert first.status_code == 200
        assert post_tick(client, run, 1).json() == first.json()  # identical repost
        conflict = post_tick(client, run, 1, satisfaction=12.0)
        assert (conflict.status_code, conflict.json()["error"]["code"]) == (409, "tick_conflict")
        gap = post_tick(client, run, 3)
        assert (gap.status_code, gap.json()["error"]["code"]) == (409, "tick_gap")
        stale = client.post(
            f"/api/runs/{run['run_id']}/ticks",
            json={"run_epoch": 2, "tick": 2, "satisfaction": 80.0},
        )
        assert (stale.status_code, stale.json()["error"]["code"]) == (409, "stale_epoch")
        unknown = client.post(
            "/api/runs/nope/ticks", json={"run_epoch": 1, "tick": 1, "satisfaction": 1.0}
        )
        assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, "unknown_run")
        assert post_tick(client, run, 2).status_code == 200


@pytest.mark.req("ARCH-02")
def test_invalid_observations_change_nothing(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        run = launch(client)
        bad = post_tick(
            client,
            run,
            1,
            incidents=[incident("game-1", "crime", 30, 1)],
            routes=routes("game-1", {"nobody": 3}),
        )
        assert bad.status_code == 422
        assert {failure["code"] for failure in bad.json()["failures"]} == {"unknown_unit"}
        invalid_id = post_tick(client, run, 1, incidents=[incident("fire-1", "crime", 30, 1)])
        assert invalid_id.json()["error"]["code"] == "invalid_incident_id"
        ok = post_tick(client, run, 1, incidents=[incident("game-1", "crime", 30, 1)])
        assert ok.status_code == 200  # the rejected bodies did not advance the run
        vanished = post_tick(client, run, 2)
        assert vanished.json()["error"]["code"] == "incident_vanished"
        resolved = post_tick(
            client, run, 2, incidents=[incident("game-1", "crime", 0, 1, "resolved")]
        )
        assert resolved.status_code == 200
        reopened = post_tick(client, run, 3, incidents=[incident("game-1", "crime", 30, 1)])
        assert reopened.json()["error"]["code"] == "incident_reopened"
        moods = post_tick(client, run, 3, resident_moods=[{"id": 99, "mood": 50.0}])
        assert moods.json()["error"]["code"] == "unknown_resident"


@pytest.mark.req("RES-06")
def test_residents_joining_mid_run_are_topped_up(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        run = launch(client)
        outcome = post_tick(client, run, 1, residents_joined=list(range(6, 12))).json()
        modes = outcome["resident_modes"]
        assert sorted(modes, key=int) == [str(i) for i in range(6, 12)]
        assert sum(modes.values()) == 3  # 12 residents at 50 % -> 6 LLM in total
        duplicate = post_tick(client, run, 2, residents_joined=[3])
        assert duplicate.json()["error"]["code"] == "duplicate_resident"


@pytest.mark.req("SIM-05", "SIM-04")
def test_runs_are_isolated_and_reset_starts_a_new_epoch(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        a, b = launch(client), launch(client)
        a_out = advance(client, a, 1, 3)
        b_out = advance(client, b, 1, 2)
        # Same seed, same observations: identical state hashes in separate runs.
        assert [o["state_hash"] for o in a_out[:2]] == [o["state_hash"] for o in b_out]
        reset = client.post(f"/api/runs/{a['run_id']}/reset", json={"run_epoch": 1})
        assert reset.status_code == 201
        a2 = reset.json()
        assert (a2["run_epoch"], a2["tick"]) == (2, 0)
        assert a2["run_id"] != a["run_id"]
        old = post_tick(client, a, 4)
        assert old.json()["error"]["code"] == "run_ended"
        assert client.get(f"/api/runs/{a['run_id']}").json()["status"] == "interrupted"
        stale = client.post(f"/api/runs/{a2['run_id']}/ticks",
                            json={"run_epoch": 1, "tick": 1, "satisfaction": 80.0})  # fmt: skip
        assert stale.json()["error"]["code"] == "stale_epoch"
        assert advance(client, a2, 1, 1)[0]["state_hash"] == a_out[0]["state_hash"]
        assert post_tick(client, b, 3).status_code == 200  # b never noticed
        cancel = client.post(f"/api/runs/{b['run_id']}/cancel", json={"run_epoch": 1})
        assert cancel.json()["status"] == "interrupted"
        manifest = json.loads((tmp_path / "runs" / a["run_id"] / "manifest.json").read_text())
        assert manifest["status"] == "interrupted"


def test_launch_refusals(tmp_path: Path) -> None:
    base = {"map": map_ref(), "population": 6, "llm_ratio_bp": 5000}
    cases = [
        (base | {"map": map_ref() | {"sha256": "0" * 64}}, 409, "map_sha_mismatch"),
        (base | {"map": {"id": "nope", "revision": 1, "sha256": "0" * 64}}, 404, "unknown_map"),
        (base | {"mayor_backend": "api"}, 409, "paid_api_disabled"),
        (base | {"scenario": "toy"}, 422, "invalid_scenario"),
    ]
    with hybrid_client(tmp_path) as client:
        for body, status, code in cases:
            response = client.post("/api/runs", json=body)
            assert (response.status_code, response.json()["error"]["code"]) == (status, code)

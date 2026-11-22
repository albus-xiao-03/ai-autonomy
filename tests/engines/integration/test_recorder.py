import hashlib
import json
from pathlib import Path

import pytest

from aiautonomy.engines.core.canonical import hash_state
from aiautonomy.engines.core.paths import repo_root
from aiautonomy.engines.record.recorder import (
    Recorder,
    read_json,
    read_snapshot,
    relabel_stale_runs,
)
from aiautonomy.engines.sim.config import ResolvedConfig
from aiautonomy.engines.sim.run import Run, run_headless
from aiautonomy.engines.sim.status import RunState

DUMMY_KEY_FRAGMENT = "sk-ant-test"


def recorded_run(resolved: ResolvedConfig, runs_dir: Path, run_id: str = "rec-1") -> Run:
    return Run(resolved, run_id=run_id, sinks=[Recorder(runs_dir)])


def ticks_of(run_dir: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in (run_dir / "ticks.jsonl").read_text().splitlines()]


@pytest.mark.req("SIM-04", "EVAL-04", "END-01")
def test_a_completed_run_writes_every_record(toy_config: ResolvedConfig, runs_dir: Path) -> None:
    run = recorded_run(toy_config, runs_dir)
    final = run_headless(run)
    run_dir = runs_dir / "rec-1"
    assert sorted(path.name for path in run_dir.iterdir()) == [
        "decisions.jsonl",
        "final_report.json",
        "interventions.jsonl",
        "manifest.json",
        "snapshots",
        "ticks.jsonl",
    ]
    lines = ticks_of(run_dir)
    assert [line["tick"] for line in lines] == list(range(301))
    assert lines[-1]["hash"] == final.state_hash.value
    assert set(lines[5]["subsystems"]) == {"clock", "ids", "metrics", "movers"}  # type: ignore[arg-type]
    snapshots = sorted(path.name for path in (run_dir / "snapshots").iterdir())
    assert snapshots == [f"tick-{tick:06d}.json.gz" for tick in range(0, 301, 30)]
    snapshot = read_snapshot(run_dir / "snapshots" / "tick-000150.json.gz")
    assert snapshot["tick"] == 150
    assert hash_state(snapshot["state"]).value == snapshot["hash"] == lines[150]["hash"]
    report = read_json(run_dir / "final_report.json")
    assert (report["outcome"], report["final_tick"]) == ("completed", 300)
    assert report["metrics"] == dict(final.metrics)
    assert (run_dir / "decisions.jsonl").read_text() == ""


@pytest.mark.req("SIM-04")
def test_the_manifest_pins_versions_seeds_and_config(
    toy_config: ResolvedConfig, runs_dir: Path
) -> None:
    run = recorded_run(toy_config, runs_dir)
    run_headless(run)
    run_dir = runs_dir / "rec-1"
    manifest = read_json(run_dir / "manifest.json")
    assert manifest["status"] == "completed"
    assert set(manifest["engine"]) == {"version", "git_sha", "dirty", "label"}
    assert manifest["seeds"]["run_seed"] == 1
    assert len(manifest["seeds"]["streams"]) == 12
    assert manifest["config"] == run.config.model_dump(mode="json")
    assert manifest["backends"] == {"resident": "none", "mayor": "none"}
    root = repo_root()
    assert {entry["id"] for entry in manifest["data_files"]} == {"engine", "toy"}
    for entry in manifest["data_files"]:
        assert entry["sha256"] == hashlib.sha256((root / entry["path"]).read_bytes()).hexdigest()
    for path in run_dir.rglob("*.json*"):
        if path.suffix != ".gz":
            assert DUMMY_KEY_FRAGMENT not in path.read_text()


@pytest.mark.req("END-05")
def test_an_interrupted_run_is_labelled_with_a_final_snapshot(
    toy_config: ResolvedConfig, runs_dir: Path
) -> None:
    run = recorded_run(toy_config, runs_dir)
    run.begin()
    run.state = RunState.running
    for _ in range(45):
        run.step()
    run.finish(RunState.interrupted, "cancelled by the user")
    run_dir = runs_dir / "rec-1"
    manifest = read_json(run_dir / "manifest.json")
    assert (manifest["status"], manifest["final_tick"]) == ("interrupted", 45)
    assert manifest["end_reason"] == "cancelled by the user"
    assert (run_dir / "snapshots" / "tick-000045.json.gz").is_file()
    assert read_json(run_dir / "final_report.json")["outcome"] == "interrupted"


@pytest.mark.req("END-05")
def test_runs_left_running_are_relabelled_at_startup(
    toy_config: ResolvedConfig, runs_dir: Path
) -> None:
    run = recorded_run(toy_config, runs_dir, run_id="crashed")
    run.begin()
    run.state = RunState.running
    for _ in range(10):
        run.step()
    assert read_json(runs_dir / "crashed" / "manifest.json")["status"] == "running"
    assert relabel_stale_runs(runs_dir) == ["crashed"]
    manifest = read_json(runs_dir / "crashed" / "manifest.json")
    assert (manifest["status"], manifest["final_tick"]) == ("interrupted", 10)
    assert read_json(runs_dir / "crashed" / "final_report.json")["outcome"] == "interrupted"
    assert relabel_stale_runs(runs_dir) == []


def test_an_unstarted_run_records_nothing(toy_config: ResolvedConfig, runs_dir: Path) -> None:
    run = recorded_run(toy_config, runs_dir)
    run.finish(RunState.interrupted, "reset")
    assert not runs_dir.exists()


def test_decision_and_intervention_logs_are_append_only(
    toy_config: ResolvedConfig, runs_dir: Path
) -> None:
    recorder = Recorder(runs_dir)
    run = Run(toy_config, run_id="logs", sinks=[recorder])
    run.begin()
    recorder.record_decision({"decision_id": "d-1", "outcome": "accepted"})
    recorder.record_decision({"decision_id": "d-2", "outcome": "rejected"})
    recorder.record_intervention({"event": "storm", "apply_tick": 5})
    decisions = (runs_dir / "logs" / "decisions.jsonl").read_text().splitlines()
    assert [json.loads(line)["decision_id"] for line in decisions] == ["d-1", "d-2"]
    assert len((runs_dir / "logs" / "interventions.jsonl").read_text().splitlines()) == 1

"""M0 exit criterion: a 300-tick headless toy run replays with identical hashes."""

import json
from pathlib import Path

import pytest

from aiautonomy.engines import cli
from aiautonomy.engines.agents import clients
from aiautonomy.engines.record.recorder import Recorder, read_json, write_json_atomic
from aiautonomy.engines.record.replay import replay_run
from aiautonomy.engines.sim import run as run_module
from aiautonomy.engines.sim.config import ResolvedConfig
from aiautonomy.engines.sim.run import Run, run_headless
from aiautonomy.engines.sim.status import RunState

pytestmark = pytest.mark.req("EVAL-04", "SIM-04")


@pytest.fixture
def recorded(toy_config: ResolvedConfig, runs_dir: Path) -> Path:
    run_headless(Run(toy_config, run_id="toy-300", sinks=[Recorder(runs_dir)]))
    return runs_dir / "toy-300"


def rewrite_tick(run_dir: Path, tick: int, **changes: object) -> None:
    path = run_dir / "ticks.jsonl"
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    for key, value in changes.items():
        if key == "subsystem_movers":
            lines[tick]["subsystems"]["movers"] = value
        elif key == "metric":
            lines[tick]["metrics"]["distance_walked_km"] = value
        else:
            lines[tick][key] = value
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))


def test_cli_headless_run_then_replay_is_identical(
    runs_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["run", "--headless", "--scenario", "toy", "--runs-dir", str(runs_dir)]) == 0
    (run_dir,) = runs_dir.iterdir()
    assert read_json(run_dir / "manifest.json")["status"] == "completed"
    capsys.readouterr()
    assert cli.main(["replay", run_dir.name, "--runs-dir", str(runs_dir)]) == 0
    assert "300 ticks identical" in capsys.readouterr().out


def test_replay_matches_hashes_metrics_and_outcome(recorded: Path) -> None:
    created = clients.clients_created()
    report = replay_run(recorded)
    assert report.ok, report.divergence
    assert report.ticks_compared == 300
    assert (report.recorded_outcome, report.replayed_outcome) == ("completed", "completed")
    assert report.final_hash == read_json(recorded / "final_report.json")["final_hash"]
    assert clients.clients_created() == created


def test_replay_creates_no_inference_client(
    recorded: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = run_module.create_toy_world

    def world_with_a_client(*args: object, **kwargs: object) -> object:
        clients.register_client("resident")
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(run_module, "create_toy_world", world_with_a_client)
    with pytest.raises(clients.InferenceForbiddenError):
        replay_run(recorded)


def test_a_tampered_hash_names_the_first_divergent_tick_and_subsystem(
    recorded: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rewrite_tick(recorded, 57, hash="f" * 64, subsystem_movers="0" * 64)
    rewrite_tick(recorded, 90, hash="e" * 64)
    report = replay_run(recorded)
    assert report.divergence is not None
    assert (report.divergence.tick, report.divergence.subsystems) == (57, ("movers",))
    assert cli.main(["replay", str(recorded)]) == 1
    assert "DIVERGED at tick 57 in movers" in capsys.readouterr().out


def test_a_changed_stream_seed_diverges_in_the_movers(recorded: Path) -> None:
    manifest = read_json(recorded / "manifest.json")
    manifest["seeds"]["streams"]["traffic_background"] += 1
    write_json_atomic(recorded / "manifest.json", manifest)
    report = replay_run(recorded)
    assert report.divergence is not None
    assert report.divergence.tick >= 1  # placement does not use this stream
    assert "movers" in report.divergence.subsystems


def test_a_tampered_metric_is_reported(recorded: Path) -> None:
    rewrite_tick(recorded, 100, metric=-1.0)
    report = replay_run(recorded)
    assert report.divergence is not None
    assert (report.divergence.tick, report.divergence.subsystems) == (100, ("metrics",))


def test_an_interrupted_run_replays_up_to_its_last_tick(
    toy_config: ResolvedConfig, runs_dir: Path
) -> None:
    run = Run(toy_config, run_id="cut", sinks=[Recorder(runs_dir)])
    run.begin()
    run.state = RunState.running
    for _ in range(40):
        run.step()
    run.finish(RunState.interrupted, "cancelled by the user")
    report = replay_run(runs_dir / "cut")
    assert report.ok
    assert (report.ticks_compared, report.recorded_outcome) == (40, "interrupted")

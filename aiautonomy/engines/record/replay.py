"""Replay a recorded run without inference (docs/engine-plan.md §4.2, §4.7).

Rebuilds the run from its manifest (frozen config, recorded stream seeds, data file
versions), interventions and decisions, inside `no_inference_clients()`. Compares the tick
hashes, metrics and terminal outcome with the recording and reports the first divergent
tick and the subsystem(s) whose hash differs.

REQ: EVAL-04, SIM-04
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiautonomy.engines.agents.clients import no_inference_clients
from aiautonomy.engines.core.datafiles import DataFileRef, sha256_file
from aiautonomy.engines.core.paths import repo_root
from aiautonomy.engines.core.version import engine_version
from aiautonomy.engines.record.recorder import DECISIONS, INTERVENTIONS, MANIFEST, TICKS, read_json
from aiautonomy.engines.sim.config import ResolvedConfig, RunConfig
from aiautonomy.engines.sim.run import Run, TickResult
from aiautonomy.engines.sim.status import RunState

TERMINAL_OUTCOMES = frozenset({RunState.completed.value, RunState.removed.value})


class ReplayError(Exception):
    """The recording cannot be replayed (missing or malformed files)."""


@dataclass(frozen=True, slots=True)
class Divergence:
    tick: int
    subsystems: tuple[str, ...]
    detail: str


@dataclass(slots=True)
class ReplayReport:
    run_id: str
    run_dir: Path
    ticks_compared: int = 0
    recorded_outcome: str | None = None
    replayed_outcome: str | None = None
    final_hash: str | None = None
    divergence: Divergence | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.divergence is None


def resolve_run_dir(ref: str, runs_dir: Path) -> Path:
    """Accept a run directory path or a run id under `runs_dir`."""
    for candidate in (Path(ref), runs_dir / ref):
        if (candidate / MANIFEST).is_file():
            return candidate
    raise ReplayError(f"no recorded run {ref!r} (looked for {MANIFEST} in {ref} and {runs_dir})")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ReplayError(f"missing {path}")
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as lines:
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReplayError(f"{path}:{number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ReplayError(f"{path}:{number}: expected a JSON object")
            records.append(record)
    return records


def _differing(recorded: Mapping[str, Any], replayed: Mapping[str, Any]) -> tuple[str, ...]:
    keys = sorted(set(recorded) | set(replayed))
    return tuple(key for key in keys if recorded.get(key) != replayed.get(key))


def _compare(line: Mapping[str, Any], result: TickResult) -> Divergence | None:
    subsystems = _differing(line.get("subsystems", {}), result.state_hash.subsystems)
    if line.get("hash") != result.state_hash.value:
        return Divergence(
            result.tick, subsystems or ("state",), "state hash differs from the recording"
        )
    if subsystems:
        return Divergence(result.tick, subsystems, "subsystem hashes differ from the recording")
    metrics = _differing(line.get("metrics", {}), result.metrics)
    if metrics:
        return Divergence(result.tick, ("metrics",), f"metrics differ: {', '.join(metrics)}")
    return None


def _check_versions(manifest: Mapping[str, Any], report: ReplayReport) -> None:
    recorded_engine = manifest.get("engine", {})
    current = engine_version()
    recorded_identity = (recorded_engine.get("version"), recorded_engine.get("git_sha"))
    if recorded_identity != (current.version, current.git_sha):
        report.warnings.append(
            f"engine version differs: recorded {recorded_engine.get('label')}, "
            f"replaying with {current.label}"
        )
    elif recorded_engine.get("dirty"):
        report.warnings.append("the recording was made from a dirty working tree")
    try:
        root = repo_root()
    except FileNotFoundError:
        return
    for entry in manifest.get("data_files", []):
        path = root / entry.get("path", "")
        if not path.is_file():
            report.warnings.append(f"data file {entry.get('path')} is no longer present")
        elif sha256_file(path) != entry.get("sha256"):
            report.warnings.append(f"data file {entry.get('path')} changed since the recording")


def replay_run(run_dir: Path) -> ReplayReport:
    """Re-simulate a recorded run and compare it with the recording."""
    manifest = read_json(run_dir / MANIFEST)
    report = ReplayReport(run_id=str(manifest.get("run_id", run_dir.name)), run_dir=run_dir)
    report.recorded_outcome = manifest.get("status")
    recorded = _load_jsonl(run_dir / TICKS)
    decisions = _load_jsonl(run_dir / DECISIONS)
    interventions = _load_jsonl(run_dir / INTERVENTIONS)
    if decisions or interventions:
        raise ReplayError("recorded decisions or interventions need M2+/M4+ replay support")
    if not recorded or recorded[0].get("tick") != 0:
        raise ReplayError(f"{run_dir / TICKS}: must start with tick 0")
    _check_versions(manifest, report)
    try:
        config = RunConfig.model_validate(manifest["config"])
        data_files = tuple(DataFileRef.model_validate(entry) for entry in manifest["data_files"])
        stream_seeds = {str(k): int(v) for k, v in manifest["seeds"]["streams"].items()}
    except (KeyError, TypeError, ValueError) as exc:
        raise ReplayError(f"{run_dir / MANIFEST}: incomplete manifest: {exc}") from exc

    with no_inference_clients():
        run = Run(
            ResolvedConfig(config=config, data_files=data_files),
            run_id=report.run_id,
            run_epoch=int(manifest.get("run_epoch", 1)),
            stream_seeds=stream_seeds,
        )
        run.begin()
        run.state = RunState.running
        report.divergence = _compare(recorded[0], run.last_result)
        for line in recorded[1:]:
            if report.divergence is not None:
                break
            if run.state.terminal:
                report.divergence = Divergence(
                    run.tick,
                    ("outcome",),
                    f"replay ended as {run.state} before tick {line['tick']}",
                )
                break
            result = run.step()
            report.ticks_compared = result.tick
            if line.get("tick") != result.tick:
                report.divergence = Divergence(
                    result.tick, ("ticks",), f"recording has tick {line.get('tick')} here"
                )
                break
            report.divergence = _compare(line, result)

    report.replayed_outcome = run.state.value if run.state.terminal else "not_ended"
    report.final_hash = run.last_result.state_hash.value
    if (
        report.divergence is None
        and report.recorded_outcome in TERMINAL_OUTCOMES
        and report.replayed_outcome != report.recorded_outcome
    ):
        report.divergence = Divergence(
            run.tick,
            ("outcome",),
            f"recorded {report.recorded_outcome}, replay {report.replayed_outcome}",
        )
    return report

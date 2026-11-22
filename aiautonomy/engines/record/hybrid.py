"""Recorder of hybrid runs (docs/contract.md §11).

`runs/<run_id>/` holds:

- `manifest.json`: kind `boston_hybrid`, status, the pinned map, the launch request, the frozen
  config, per-stream seeds, every data file's hash, backends and the engine version. Never
  credentials.
- `observations.jsonl`: every accepted game observation with its digest.
- `outcomes.jsonl`: every tick outcome the engine returned.
- `decisions.jsonl`, `interventions.jsonl`: decision lifecycle and disruption records.
- `ticks.jsonl`: the state hash and per-subsystem hashes of every tick, from tick 0.
- `final_report.json`: the terminal outcome.

REQ: SIM-04, EVAL-04, CUSTOM-07, END-05, ARCH-05
"""

import platform
from collections.abc import Mapping
from pathlib import Path
from typing import IO, Any

from aiautonomy.engines.contract.common import CONTRACT_VERSION, RunStatusLabel
from aiautonomy.engines.contract.runs import TickOutcome
from aiautonomy.engines.core.canonical import StateHash, canonical_json
from aiautonomy.engines.core.version import engine_version
from aiautonomy.engines.hybrid.run import HybridRun
from aiautonomy.engines.record.recorder import (
    DECISIONS,
    FINAL_REPORT,
    INTERVENTIONS,
    MANIFEST,
    TICKS,
    read_json,
    utc_now,
    write_json_atomic,
)

KIND = "boston_hybrid"
FORMAT_VERSION = 2
OBSERVATIONS = "observations.jsonl"
OUTCOMES = "outcomes.jsonl"


def tick_line(tick: int, state_hash: StateHash) -> dict[str, Any]:
    return {"tick": tick, "hash": state_hash.value, "subsystems": dict(state_hash.subsystems)}


class HybridRecorder:
    """HybridSink writing one run directory."""

    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.run_dir: Path | None = None
        self._files: dict[str, IO[str]] = {}

    def _append(self, name: str, entry: Mapping[str, Any]) -> None:
        if self.run_dir is None:
            return
        handle = self._files.get(name)
        if handle is None:
            handle = (self.run_dir / name).open("a", encoding="utf-8")
            self._files[name] = handle
        handle.write(canonical_json(dict(entry)) + "\n")
        handle.flush()

    def on_launch(self, run: HybridRun) -> None:
        run_dir = self.runs_dir / run.run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        self.run_dir = run_dir
        version = engine_version()
        manifest = {
            "format": "aia-run",
            "format_version": FORMAT_VERSION,
            "kind": KIND,
            "contract_version": CONTRACT_VERSION,
            "run_id": run.run_id,
            "run_epoch": run.run_epoch,
            "status": "running",
            "created_at": utc_now(),
            "ended_at": None,
            "end_reason": None,
            "final_tick": None,
            "engine": {**version.to_dict(), "label": version.label},
            "python": platform.python_version(),
            "map": run.setup.map_ref.model_dump(mode="json"),
            "launch": run.setup.request.model_dump(mode="json"),
            "config": run.config.model_dump(mode="json"),
            "data_files": [ref.model_dump() for ref in run.setup.data_files],
            "seeds": {"run_seed": run.config.seed, "streams": dict(run.stream_seeds)},
            "backends": {"mayor": run.mayor_backend, "resident": "local"},
        }
        write_json_atomic(run_dir / MANIFEST, manifest)
        for name in (OBSERVATIONS, OUTCOMES, DECISIONS, INTERVENTIONS):
            (run_dir / name).touch()
        self._append(TICKS, tick_line(0, run.last_hash))

    def on_observation(self, run: HybridRun, record: Mapping[str, Any]) -> None:
        self._append(OBSERVATIONS, record)

    def on_tick(self, run: HybridRun, outcome: TickOutcome, state_hash: StateHash) -> None:
        self._append(OUTCOMES, outcome.model_dump(mode="json"))
        self._append(TICKS, tick_line(outcome.tick, state_hash))

    def on_decision(self, run: HybridRun, record: Mapping[str, Any]) -> None:
        self._append(DECISIONS, record)

    def on_intervention(self, run: HybridRun, record: Mapping[str, Any]) -> None:
        self._append(INTERVENTIONS, record)

    def on_end(self, run: HybridRun, status: RunStatusLabel, reason: str | None) -> None:
        if self.run_dir is None:
            return
        report = {
            "run_id": run.run_id,
            "kind": KIND,
            "outcome": status,
            "reason": reason,
            "final_tick": run.tick,
            "duration": run.config.duration,
            "final_hash": run.last_hash.value,
            "authority": run.state.authority,
            "summary": run.summary().model_dump(mode="json"),
        }
        write_json_atomic(self.run_dir / FINAL_REPORT, report)
        manifest = read_json(self.run_dir / MANIFEST)
        manifest |= {
            "status": status,
            "ended_at": utc_now(),
            "end_reason": reason,
            "final_tick": run.tick,
        }
        write_json_atomic(self.run_dir / MANIFEST, manifest)
        for handle in self._files.values():
            handle.close()
        self._files.clear()

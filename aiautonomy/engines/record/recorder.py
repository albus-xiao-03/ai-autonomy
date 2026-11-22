"""Run recorder (docs/engine-plan.md §4.7).

Each started run writes `runs/<run_id>/`:

- `manifest.json`: status (`running|completed|removed|interrupted`), engine version, every
  data file's id/version/sha256, per-stream seeds, frozen config and backend modes. Never
  credentials. Rewritten atomically when the status changes.
- `interventions.jsonl`, `decisions.jsonl`, `ticks.jsonl`: append-only logs; `ticks.jsonl`
  holds the state hash, per-subsystem hashes and metrics of every tick, from tick 0.
- `snapshots/tick-NNNNNN.json.gz`: full state every `snapshot_interval` ticks and at the end.
- `final_report.json`: terminal outcome and metrics.

REQ: SIM-04, EVAL-04, END-01, END-05
"""

import gzip
import hashlib
import itertools
import json
import os
import platform
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from aiautonomy.engines.core.canonical import canonical_json
from aiautonomy.engines.core.version import engine_version
from aiautonomy.engines.sim.run import Run, TickResult
from aiautonomy.engines.sim.status import RunState

FORMAT = "aia-run"
FORMAT_VERSION = 1
MANIFEST = "manifest.json"
TICKS = "ticks.jsonl"
DECISIONS = "decisions.jsonl"
INTERVENTIONS = "interventions.jsonl"
FINAL_REPORT = "final_report.json"
SNAPSHOTS = "snapshots"
DEFAULT_BACKENDS: Mapping[str, str] = {"resident": "none", "mayor": "none"}

_run_counter = itertools.count()


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def make_run_id(scenario: str, seed: int, now: datetime | None = None) -> str:
    """Wall-clock based, unique run id; excluded from every hash."""
    now = now or datetime.now(UTC)
    stamp = now.strftime("%Y%m%dT%H%M%S") + f"{now.microsecond // 1000:03d}Z"
    nonce_source = f"{time.time_ns()}:{os.getpid()}:{next(_run_counter)}".encode()
    nonce = hashlib.blake2b(nonce_source, digest_size=3).hexdigest()
    return f"{stamp}-{scenario}-s{seed}-{nonce}"


def snapshot_name(tick: int) -> str:
    return f"tick-{tick:06d}.json.gz"


def tick_record(result: TickResult) -> dict[str, Any]:
    return {
        "tick": result.tick,
        "hash": result.state_hash.value,
        "subsystems": dict(result.state_hash.subsystems),
        "metrics": dict(result.metrics),
    }


def write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def write_snapshot(path: Path, run_id: str, tick: int, state_hash: str, state: Any) -> None:
    """Gzip with a fixed mtime so identical states give identical bytes."""
    document = {"run_id": run_id, "tick": tick, "hash": state_hash, "state": state}
    with path.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as packed:
        packed.write(canonical_json(document).encode("utf-8"))


def read_snapshot(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rb") as packed:
        data = json.loads(packed.read())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


class Recorder:
    """RunSink that records one run. The run directory appears when the run starts."""

    def __init__(self, runs_dir: Path, *, backends: Mapping[str, str] | None = None) -> None:
        self.runs_dir = runs_dir
        self.backends = dict(backends or DEFAULT_BACKENDS)
        self.run_dir: Path | None = None
        self._ticks: IO[str] | None = None
        self._snapshot_ticks: set[int] = set()
        self._interval = 1

    # --- RunSink ------------------------------------------------------------------

    def on_run_start(self, run: Run) -> None:
        run_dir = self.runs_dir / run.run_id
        (run_dir / SNAPSHOTS).mkdir(parents=True, exist_ok=False)
        self.run_dir = run_dir
        self._interval = run.config.snapshot_interval
        write_json_atomic(run_dir / MANIFEST, self._manifest(run))
        for name in (INTERVENTIONS, DECISIONS):
            (run_dir / name).touch()
        self._ticks = (run_dir / TICKS).open("a", encoding="utf-8")
        self.on_tick(run, run.last_result)

    def on_tick(self, run: Run, result: TickResult) -> None:
        if self._ticks is None or self.run_dir is None:
            return
        self._ticks.write(canonical_json(tick_record(result)) + "\n")
        self._ticks.flush()
        if result.tick % self._interval == 0 or result.outcome is not None:
            self._snapshot(run, result)

    def on_run_end(self, run: Run, outcome: RunState, reason: str | None) -> None:
        if self.run_dir is None:
            return
        final = run.last_result
        if final.tick not in self._snapshot_ticks:
            self._snapshot(run, final)
        report = {
            "run_id": run.run_id,
            "outcome": outcome.value,
            "reason": reason,
            "final_tick": final.tick,
            "duration": run.config.duration,
            "final_hash": final.state_hash.value,
            "metrics": dict(final.metrics),
            "removal": None,
            "inference_coverage": {"resident": None, "mayor": None},
        }
        write_json_atomic(self.run_dir / FINAL_REPORT, report)
        manifest = read_json(self.run_dir / MANIFEST)
        manifest |= {
            "status": outcome.value,
            "ended_at": utc_now(),
            "end_reason": reason,
            "final_tick": final.tick,
        }
        write_json_atomic(self.run_dir / MANIFEST, manifest)
        if self._ticks is not None:
            self._ticks.close()
            self._ticks = None

    # --- logs ---------------------------------------------------------------------

    def record_decision(self, entry: Mapping[str, Any]) -> None:
        self._append(DECISIONS, entry)

    def record_intervention(self, entry: Mapping[str, Any]) -> None:
        self._append(INTERVENTIONS, entry)

    def _append(self, name: str, entry: Mapping[str, Any]) -> None:
        if self.run_dir is None:
            raise RuntimeError("the run has not started recording")
        with (self.run_dir / name).open("a", encoding="utf-8") as log:
            log.write(canonical_json(dict(entry)) + "\n")

    def _snapshot(self, run: Run, result: TickResult) -> None:
        assert self.run_dir is not None
        path = self.run_dir / SNAPSHOTS / snapshot_name(result.tick)
        write_snapshot(path, run.run_id, result.tick, result.state_hash.value, result.state)
        self._snapshot_ticks.add(result.tick)

    def _manifest(self, run: Run) -> dict[str, Any]:
        version = engine_version()
        return {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "run_id": run.run_id,
            "run_epoch": run.run_epoch,
            "status": "running",
            "created_at": utc_now(),
            "ended_at": None,
            "end_reason": None,
            "final_tick": None,
            "engine": {**version.to_dict(), "label": version.label},
            "python": platform.python_version(),
            "data_files": [ref.model_dump() for ref in run.data_files],
            "seeds": {"run_seed": run.config.seed, "streams": dict(run.stream_seeds)},
            "config": run.config.model_dump(mode="json"),
            "backends": dict(self.backends),
        }


def relabel_stale_runs(runs_dir: Path) -> list[str]:
    """Relabel runs still marked `running` (left by a crash or kill) as `interrupted`.

    Called at engine startup (END-05). Returns the relabelled run ids.
    """
    relabelled: list[str] = []
    if not runs_dir.is_dir():
        return relabelled
    for manifest_path in sorted(runs_dir.glob(f"*/{MANIFEST}")):
        try:
            manifest = read_json(manifest_path)
        except OSError, ValueError:
            continue
        if manifest.get("status") != "running":
            continue
        run_dir = manifest_path.parent
        final_tick = _last_recorded_tick(run_dir / TICKS)
        reason = "found running at engine startup (crash or kill)"
        manifest |= {
            "status": RunState.interrupted.value,
            "ended_at": utc_now(),
            "end_reason": reason,
            "final_tick": final_tick,
        }
        write_json_atomic(manifest_path, manifest)
        if not (run_dir / FINAL_REPORT).exists():
            report = {
                "run_id": manifest.get("run_id", run_dir.name),
                "outcome": RunState.interrupted.value,
                "reason": reason,
                "final_tick": final_tick,
            }
            write_json_atomic(run_dir / FINAL_REPORT, report)
        relabelled.append(run_dir.name)
    return relabelled


def _last_recorded_tick(path: Path) -> int | None:
    last: int | None = None
    try:
        with path.open(encoding="utf-8") as lines:
            for line in lines:
                try:
                    last = int(json.loads(line)["tick"])
                except ValueError, KeyError, TypeError:
                    break
    except OSError:
        return None
    return last

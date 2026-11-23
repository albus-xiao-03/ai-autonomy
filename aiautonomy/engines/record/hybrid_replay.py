"""Replay a recorded hybrid Boston run without inference (EVAL-04, SIM-04).

The run is rebuilt from its manifest:

- the pinned map, resolved by id, revision and content hash; a changed map is refused;
- the frozen config, recorded stream seeds, launch request and inference settings;
- the catalogs, with a warning when one changed since the recording.

The recorded inputs are fed back in their original order:

- the game observations;
- injected disruptions and resident requests, at the tick boundary where they were accepted;
- the mayor's and residents' replies, served by recorded providers. A recorded timeout raises
  `ReplayedTimeout`, so the hold or fallback is identical without waiting.

Each tick's state hash and full outcome must equal the recording. That covers the
assignments and travel times, arrival ticks, queues, orders, authority history, politics and
the terminal outcome. No inference client may be created (asserted).

REQ: EVAL-04, SIM-04, CUSTOM-07, CITY-04
"""

import asyncio
import json
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aiautonomy.engines.agents.clients import no_inference_clients
from aiautonomy.engines.contract.common import MayorBackend
from aiautonomy.engines.contract.decisions import MayorProposal, ResidentDecisionRequest
from aiautonomy.engines.contract.disruptions import DisruptionInjectRequest
from aiautonomy.engines.contract.maps import MapRef
from aiautonomy.engines.contract.runs import RunLaunchRequest, TickObservation
from aiautonomy.engines.core.canonical import canonical_json
from aiautonomy.engines.core.datafiles import DataFileRef
from aiautonomy.engines.core.paths import repo_root
from aiautonomy.engines.hybrid.catalogs import load_catalogs
from aiautonomy.engines.hybrid.run import HybridRun, RunSetup
from aiautonomy.engines.mayor.providers import (
    MayorRequest,
    ProviderReply,
    ReplayedTimeout,
)
from aiautonomy.engines.record.hybrid import OBSERVATIONS, OUTCOMES
from aiautonomy.engines.record.recorder import DECISIONS, INTERVENTIONS, TICKS
from aiautonomy.engines.residents.llm import ReplayedTimeout as ReplayedResidentTimeout
from aiautonomy.engines.residents.llm import ResidentBatch, ResidentReply
from aiautonomy.engines.sim.config import InferenceSettings, RunConfig
from aiautonomy.engines.world.map_store import MapStore, MapStoreError
from aiautonomy.engines.world.maps import canonical_catalog


class HybridReplayError(Exception):
    """The recording cannot be replayed (missing files, a changed map, a broken log)."""


def _lines(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise HybridReplayError(f"missing {path}")
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise HybridReplayError(f"{path}:{number}: {exc}") from exc
    return records


class RecordedMayor:
    """Serves the replies recorded for each decision id, under the recorded model name."""

    def __init__(
        self, backend: MayorBackend, model: str, replies: Mapping[str, dict[str, Any] | None]
    ) -> None:
        self.backend: MayorBackend = backend
        self.model = model
        self.replies = replies

    async def propose(self, request: MayorRequest) -> ProviderReply:
        if request.decision_id not in self.replies:
            await asyncio.Event().wait()  # never applied in the recording (cancelled)
        reply = self.replies[request.decision_id]
        if reply is None:
            raise ReplayedTimeout(request.decision_id)
        proposal = reply.get("proposal")
        return ProviderReply(
            MayorProposal.model_validate(proposal) if proposal else None,
            str(reply.get("model", "")),
            reply.get("error"),
            int(reply.get("latency_ms", 0)),
        )


class RecordedResidents:
    """Serves the replies recorded for each resident batch."""

    def __init__(self, replies: Mapping[str, dict[str, Any] | None]) -> None:
        self.model = "recorded"
        self.replies = replies

    async def decide(self, batch: ResidentBatch) -> ResidentReply:
        if batch.batch_id not in self.replies:
            await asyncio.Event().wait()
        reply = self.replies[batch.batch_id]
        if reply is None:
            raise ReplayedResidentTimeout(batch.batch_id)
        decisions = {int(r): (str(v[0]), str(v[1])) for r, v in reply["decisions"].items()}
        return ResidentReply(
            decisions, str(reply.get("model", "")), reply.get("error"), int(reply["latency_ms"])
        )


class HybridReplayReport:
    def __init__(self, run_id: str, run_dir: Path) -> None:
        self.run_id = run_id
        self.run_dir = run_dir
        self.ticks_compared = 0
        self.recorded_outcome: str | None = None
        self.replayed_outcome: str | None = None
        self.final_hash: str | None = None
        self.divergence: str | None = None
        self.divergence_tick: int | None = None
        self.warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return self.divergence is None


def _first_difference(recorded: Any, replayed: Any, path: str = "") -> str:
    if isinstance(recorded, dict) and isinstance(replayed, dict):
        for key in sorted(set(recorded) | set(replayed)):
            if recorded.get(key) != replayed.get(key):
                return _first_difference(recorded.get(key), replayed.get(key), f"{path}.{key}")
    if isinstance(recorded, list) and isinstance(replayed, list) and len(recorded) == len(replayed):
        for index, (a, b) in enumerate(zip(recorded, replayed, strict=True)):
            if a != b:
                return _first_difference(a, b, f"{path}[{index}]")
    shown = (json.dumps(recorded)[:160], json.dumps(replayed)[:160])
    return f"{path or '$'}: recorded {shown[0]}, replayed {shown[1]}"


def replay_hybrid(
    run_dir: Path, manifest: Mapping[str, Any], maps_dir: Path | None
) -> HybridReplayReport:
    report = HybridReplayReport(str(manifest.get("run_id", run_dir.name)), run_dir)
    report.recorded_outcome = manifest.get("status")
    root = repo_root()
    try:
        config = RunConfig.model_validate(manifest["config"])
        launch = RunLaunchRequest.model_validate(manifest["launch"])
        inference = InferenceSettings.model_validate(manifest["inference"])
        map_ref = MapRef.model_validate(manifest["map"])
        seeds = {str(k): int(v) for k, v in manifest["seeds"]["streams"].items()}
        recorded_files = [DataFileRef.model_validate(entry) for entry in manifest["data_files"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise HybridReplayError(f"incomplete manifest: {exc}") from exc
    catalog = canonical_catalog(root).catalog
    store = MapStore(root / "data" / "maps", maps_dir or root / "maps", catalog)
    try:
        revision = store.resolve(map_ref)
    except MapStoreError as exc:
        raise HybridReplayError(
            f"the pinned map cannot be used: {exc.code}: {exc.message}"
        ) from exc
    catalogs = load_catalogs(root)
    current = {ref.path: ref.sha256 for ref in catalogs.refs}
    for ref in recorded_files:
        if ref.path in current and current[ref.path] != ref.sha256:
            report.warnings.append(f"catalog {ref.path} changed since the recording")
    setup = RunSetup(
        request=launch,
        config=config,
        data_files=tuple(recorded_files),
        map_revision=revision,
        catalogs=catalogs,
        bounds=catalog.bounds(revision.content.level),
        inference=inference,
    )
    observations = _lines(run_dir / OBSERVATIONS)
    outcomes = _lines(run_dir / OUTCOMES)
    ticks = _lines(run_dir / TICKS)
    decisions = _lines(run_dir / DECISIONS)
    interventions = _lines(run_dir / INTERVENTIONS)
    mayor_replies = {
        entry["record"]["envelope"]["decision_id"]: entry.get("reply")
        for entry in decisions
        if entry.get("kind") == "mayor_decision" and entry.get("event") == "applied"
    }
    requested = [
        entry["record"]
        for entry in decisions
        if entry.get("kind") == "mayor_decision" and entry.get("event") in ("requested", "hold")
    ]
    mayor_model = str(requested[0]["model"]) if requested else "rules"
    resident_replies = {
        entry["batch_id"]: entry.get("reply")
        for entry in decisions
        if entry.get("kind") == "resident_decision" and entry.get("event") == "applied"
    }
    between: dict[int, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for entry in interventions:
        if entry.get("source") == "injected":
            between[int(entry["accepted_after_tick"])].append(("inject", entry))
    for entry in decisions:
        if entry.get("kind") == "resident_decision" and entry.get("event") == "requested":
            between[int(entry["request"]["tick"])].append(("residents", entry))
    if not ticks or ticks[0].get("tick") != 0:
        raise HybridReplayError(f"{run_dir / TICKS} must start with tick 0")

    with no_inference_clients():
        run = HybridRun(
            setup,
            run_id=report.run_id,
            run_epoch=int(manifest.get("run_epoch", 1)),
            stream_seeds=seeds,
            provider=RecordedMayor(launch.mayor_backend, mayor_model, mayor_replies),
            resident_provider=RecordedResidents(resident_replies),
        )
        if run.last_hash.value != ticks[0]["hash"]:
            report.divergence, report.divergence_tick = "initial state hash differs", 0
            return report

        async def drive() -> None:
            for index, line in enumerate(observations):
                tick = int(line["tick"])
                for kind, entry in between.get(tick - 1, []):
                    if kind == "inject":
                        body = DisruptionInjectRequest(
                            run_epoch=run.run_epoch,
                            request_id=entry["request_id"],
                            disruption=entry["spec"],
                        )
                        run.inject(body)
                    else:
                        run.request_residents(
                            ResidentDecisionRequest.model_validate(entry["request"])
                        )
                outcome = await run.handle(TickObservation.model_validate(line["observation"]))
                report.ticks_compared = tick
                recorded_tick = ticks[index + 1] if index + 1 < len(ticks) else {}
                if recorded_tick.get("hash") != outcome.state_hash:
                    changed = sorted(
                        key
                        for key, value in run.last_hash.subsystems.items()
                        if recorded_tick.get("subsystems", {}).get(key) != value
                    )
                    report.divergence = f"state hash differs in {', '.join(changed) or 'state'}"
                    report.divergence_tick = tick
                    return
                replayed = json.loads(canonical_json(outcome.model_dump(mode="json")))
                if index >= len(outcomes) or outcomes[index] != replayed:
                    recorded = outcomes[index] if index < len(outcomes) else None
                    report.divergence = _first_difference(recorded, replayed)
                    report.divergence_tick = tick
                    return

        asyncio.run(drive())
    report.replayed_outcome = run.status
    report.final_hash = run.last_hash.value
    terminal = {"completed", "removed"}
    ended_differently = report.replayed_outcome != report.recorded_outcome
    if report.divergence is None and report.recorded_outcome in terminal and ended_differently:
        report.divergence = f"recorded {report.recorded_outcome}, replay {report.replayed_outcome}"
    return report

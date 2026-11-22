"""One hybrid run: identity checks, observation validation and the per-tick SIM-02 phases.

`handle(observation)` processes exactly one game tick:

1. identity and ordering: the epoch must match (else 409 `stale_epoch`); an identical repost of
   a processed tick returns the stored outcome (idempotent); a different body for it is 409
   `tick_conflict`; a gap is 409 `tick_gap`; an ended run is 409 `run_ended`;
2. validation of the whole observation before anything changes (422 with every failure);
3. the phases of docs/tick-order.md, then the outcome, the state hash and the records.

An unexpected error while applying a validated observation ends the run as interrupted
(END-05), so a half-applied tick can never be continued.

REQ: SIM-02, SIM-03, SIM-04, SIM-05, ARCH-02, END-01, END-05
"""

import hashlib
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from aiautonomy.engines.contract.common import (
    CONTRACT_VERSION,
    ControllerLabel,
    Failure,
    MayorBackend,
    RunStatusLabel,
)
from aiautonomy.engines.contract.decisions import AuthorityChange
from aiautonomy.engines.contract.dispatch import Assignment, QueueEntry, Release
from aiautonomy.engines.contract.maps import MapRef, MapRevision
from aiautonomy.engines.contract.politics import (
    PetitionStatus,
    PoliticalStatus,
    ProtestStatus,
    VoteStatus,
)
from aiautonomy.engines.contract.runs import (
    AuthorityView,
    CatalogRef,
    MayorStatus,
    ResidentModes,
    RunConfigView,
    RunHandle,
    RunLaunchRequest,
    RunSummary,
    TickObservation,
    TickOutcome,
)
from aiautonomy.engines.core.canonical import StateHash, canonical_json, hash_state
from aiautonomy.engines.core.datafiles import DataFileRef
from aiautonomy.engines.core.money import apply_bp
from aiautonomy.engines.core.rng import KeyedRng, derive_stream_seeds
from aiautonomy.engines.hybrid import dispatch, residents
from aiautonomy.engines.hybrid.catalogs import Catalogs
from aiautonomy.engines.hybrid.state import HybridState, Incident
from aiautonomy.engines.sim.config import RunConfig
from aiautonomy.engines.world.boston import BostonWorldConfig

HISTORY_TICKS = 64
"""Processed ticks whose outcome is kept for idempotent reposts."""
INITIAL_AUTHORITY = 100
GAME_INCIDENT_PREFIX = "game-"
ENGINE_INCIDENT_PREFIX = "inc-"


class RunError(Exception):
    """A request the run refuses: 404, 409 (conflict with the run state) or 422 (invalid)."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        failures: list[Failure] | None = None,
        entity_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.failures = failures or []
        self.entity_id = entity_id


class HybridSink(Protocol):
    """Receives a run's records (the recorder)."""

    def on_launch(self, run: HybridRun) -> None: ...

    def on_observation(self, run: HybridRun, record: Mapping[str, Any]) -> None: ...

    def on_tick(self, run: HybridRun, outcome: TickOutcome, state_hash: StateHash) -> None: ...

    def on_decision(self, run: HybridRun, record: Mapping[str, Any]) -> None: ...

    def on_intervention(self, run: HybridRun, record: Mapping[str, Any]) -> None: ...

    def on_end(self, run: HybridRun, status: RunStatusLabel, reason: str | None) -> None: ...


@dataclass(frozen=True, slots=True)
class RunSetup:
    """Everything a launch resolved; a reset reuses it for the next epoch."""

    request: RunLaunchRequest
    config: RunConfig
    data_files: tuple[DataFileRef, ...]
    map_revision: MapRevision
    catalogs: Catalogs

    @property
    def world(self) -> BostonWorldConfig:
        world = self.config.world
        assert isinstance(world, BostonWorldConfig)
        return world

    @property
    def map_ref(self) -> MapRef:
        revision = self.map_revision
        return MapRef(id=revision.id, revision=revision.revision, sha256=revision.sha256)


@dataclass(slots=True)
class TickParts:
    """What the phases of one tick produce for the outcome."""

    assignments: list[Assignment] = field(default_factory=list)
    releases: list[Release] = field(default_factory=list)
    queue: list[QueueEntry] = field(default_factory=list)
    authority_changes: list[AuthorityChange] = field(default_factory=list)
    resident_modes: dict[str, bool] = field(default_factory=dict)
    warnings: list[Failure] = field(default_factory=list)
    arrivals: list[tuple[str, str]] = field(default_factory=list)


def observation_digest(observation: TickObservation) -> str:
    text = canonical_json(observation.model_dump(mode="json"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fail(code: str, entity_id: str | None, message: str) -> Failure:
    return Failure(code=code, entity_id=entity_id, message=message[:500])


class HybridRun:
    def __init__(
        self,
        setup: RunSetup,
        *,
        run_id: str,
        run_epoch: int,
        sinks: Sequence[HybridSink] = (),
        stream_seeds: Mapping[str, int] | None = None,
    ) -> None:
        config = setup.config
        self.setup = setup
        self.run_id = run_id
        self.run_epoch = run_epoch
        self.config = config
        self.world = setup.world
        self.mayor_backend: MayorBackend = setup.request.mayor_backend
        self.stream_seeds = (
            dict(stream_seeds)
            if stream_seeds is not None
            else derive_stream_seeds(config.seed, config.stream_seed_overrides)
        )
        self.rng = KeyedRng(self.stream_seeds)
        llm_ids = residents.assign_llm(config.population, config.llm_count, self.rng)
        self.state = HybridState.initial(
            setup.map_revision.content, config.population, llm_ids, INITIAL_AUTHORITY
        )
        self.status: RunStatusLabel = "running"
        self.end_reason: str | None = None
        self.sinks: list[HybridSink] = list(sinks)
        self._history: OrderedDict[int, tuple[str, TickOutcome]] = OrderedDict()
        self.last_hash: StateHash = hash_state(self.state.to_state())
        for sink in self.sinks:
            sink.on_launch(self)

    # --- views -------------------------------------------------------------------------

    @property
    def tick(self) -> int:
        return self.state.tick

    @property
    def controller(self) -> ControllerLabel:
        return self.mayor_backend

    def resident_modes(self) -> ResidentModes:
        return ResidentModes(
            population=self.config.population,
            llm_ratio_bp=self.config.llm_ratio_bp,
            llm_count=len(self.state.llm_ids),
            llm_ids=list(self.state.llm_ids),
        )

    def catalog_refs(self) -> list[CatalogRef]:
        return [
            CatalogRef(id=ref.id, version=ref.version, path=ref.path, sha256=ref.sha256)
            for ref in self.setup.data_files
        ]

    def config_view(self) -> RunConfigView:
        world = self.world
        return RunConfigView(
            scenario=self.config.scenario,
            seed=self.config.seed,
            duration=self.config.duration,
            start_minute_of_day=self.config.start_minute_of_day,
            mayor_interval=self.config.mayor_interval,
            mayor_latency_ticks=world.mayor_latency_ticks,
            resident_latency_ticks=world.resident_latency_ticks,
            outcome_window_ticks=world.outcome_window_ticks,
            politics_interval_ticks=world.politics_interval_ticks,
        )

    def handle_view(self) -> RunHandle:
        return RunHandle(
            contract_version=CONTRACT_VERSION,
            run_id=self.run_id,
            run_epoch=self.run_epoch,
            status=self.status,
            tick=self.state.tick,
            map=self.setup.map_ref,
            config=self.config_view(),
            mayor_backend=self.mayor_backend,
            controller=self.controller,
            residents=self.resident_modes(),
            units=[unit.view() for unit in self.state.units.values()],
            catalogs=self.catalog_refs(),
        )

    def summary(self) -> RunSummary:
        return RunSummary(
            run_id=self.run_id,
            run_epoch=self.run_epoch,
            status=self.status,
            tick=self.state.tick,
            map=self.setup.map_ref,
            mayor_backend=self.mayor_backend,
            authority=self.state.authority,
            decisions=0,
            orders=0,
        )

    def politics_status(self) -> PoliticalStatus:
        population = len(self.state.resident_ids)
        return PoliticalStatus(
            authority=self.state.authority,
            petition=PetitionStatus(
                open=False, signers=0, threshold=max(1, apply_bp(population, 3000))
            ),
            vote=VoteStatus(open=False, eligible=population, retain=0, replace=0),
            protest=ProtestStatus(participants=0, active=False, pressure_ticks=0),
        )

    def mayor_status(self) -> MayorStatus:
        return MayorStatus(
            backend=self.mayor_backend,
            controller=self.controller,
            state="removed" if self.status == "removed" else "idle",
        )

    # --- lifecycle ---------------------------------------------------------------------

    def end(self, status: RunStatusLabel, reason: str | None) -> None:
        """Enter a terminal status once and let the sinks finalize their records."""
        if self.status != "running":
            return
        self.status = status
        self.end_reason = reason
        for sink in self.sinks:
            sink.on_end(self, status, reason)

    def interrupt(self, reason: str) -> None:
        self.end("interrupted", reason)

    # --- one tick ----------------------------------------------------------------------

    async def handle(self, observation: TickObservation) -> TickOutcome:
        if observation.run_epoch != self.run_epoch:
            raise RunError(
                409,
                "stale_epoch",
                f"run {self.run_id} is at epoch {self.run_epoch}, not {observation.run_epoch}",
            )
        digest = observation_digest(observation)
        cached = self._history.get(observation.tick)
        if cached is not None:
            if cached[0] == digest:
                return cached[1]
            raise RunError(
                409, "tick_conflict", f"tick {observation.tick} was processed with another body"
            )
        if self.status != "running":
            raise RunError(409, "run_ended", f"run {self.run_id} ended ({self.status})")
        expected = self.state.tick + 1
        if observation.tick > expected:
            raise RunError(409, "tick_gap", f"expected tick {expected}, got {observation.tick}")
        if observation.tick < expected:
            raise RunError(
                409, "tick_stale", f"tick {observation.tick} is older than the kept history"
            )
        failures = self.validate(observation)
        if failures:
            raise RunError(422, failures[0].code, "the observation is not valid", failures)
        try:
            outcome, state_hash = self._process(observation)
        except Exception as exc:
            self.interrupt(f"engine error while applying tick {observation.tick}: {exc!r}")
            raise
        record = {"tick": observation.tick, "digest": digest} | {
            "observation": observation.model_dump(mode="json")
        }
        for sink in self.sinks:
            sink.on_observation(self, record)
            sink.on_tick(self, outcome, state_hash)
        self._history[observation.tick] = (digest, outcome)
        while len(self._history) > HISTORY_TICKS:
            self._history.popitem(last=False)
        if outcome.status != "running":
            self.end(outcome.status, self.end_reason or "duration reached")
        return outcome

    # --- validation (no state change) --------------------------------------------------

    def validate(self, observation: TickObservation) -> list[Failure]:
        state = self.state
        failures: list[Failure] = []
        seen: set[str] = set()
        for item in observation.incidents:
            if item.id in seen:
                failures.append(_fail("duplicate_incident", item.id, "incident listed twice"))
            seen.add(item.id)
            if not item.id.startswith((GAME_INCIDENT_PREFIX, ENGINE_INCIDENT_PREFIX)):
                failures.append(
                    _fail("invalid_incident_id", item.id, "incident ids start with game- or inc-")
                )
            if item.id in state.resolved:
                failures.append(_fail("incident_reopened", item.id, "incident was resolved"))
            if item.opened_tick > observation.tick:
                failures.append(_fail("incident_in_future", item.id, "opened after this tick"))
            known = state.incidents.get(item.id)
            if known is not None and known.kind != item.kind:
                failures.append(_fail("incident_kind_changed", item.id, "kind cannot change"))
        for incident_id in state.incidents.keys() - seen:
            failures.append(
                _fail("incident_vanished", incident_id, "report it resolved before dropping it")
            )
        pairs: set[tuple[str, str]] = set()
        for route in observation.routes:
            if route.unit_id not in state.units:
                failures.append(_fail("unknown_unit", route.unit_id, "route from an unknown unit"))
            if route.incident_id not in seen:
                failures.append(
                    _fail("unknown_incident", route.incident_id, "route to an unlisted incident")
                )
            pair = (route.unit_id, route.incident_id)
            if pair in pairs:
                failures.append(_fail("duplicate_route", route.unit_id, "route listed twice"))
            pairs.add(pair)
        events: set[str] = set()
        for event in observation.unit_events:
            if event.unit_id not in state.units:
                failures.append(_fail("unknown_unit", event.unit_id, "event of an unknown unit"))
            if event.unit_id in events:
                failures.append(_fail("duplicate_event", event.unit_id, "one event per unit"))
            events.add(event.unit_id)
        failures.extend(self.validate_unit_events(observation))
        for unit_id in observation.out_of_service:
            if unit_id not in state.units:
                failures.append(_fail("unknown_unit", unit_id, "unknown out-of-service unit"))
        if len(set(observation.out_of_service)) != len(observation.out_of_service):
            failures.append(_fail("duplicate_unit", None, "out_of_service lists a unit twice"))
        existing = set(state.resident_ids)
        joined = observation.residents_joined
        if len(set(joined)) != len(joined):
            failures.append(_fail("duplicate_resident", None, "residents_joined repeats an id"))
        for resident_id in joined:
            if resident_id in existing:
                failures.append(
                    _fail("duplicate_resident", str(resident_id), "resident already exists")
                )
        if observation.resident_moods is not None:
            everyone = existing | set(joined)
            mood_ids = [mood.id for mood in observation.resident_moods]
            if len(set(mood_ids)) != len(mood_ids):
                failures.append(_fail("duplicate_resident", None, "resident_moods repeats an id"))
            for resident_id in mood_ids:
                if resident_id not in everyone:
                    failures.append(
                        _fail("unknown_resident", str(resident_id), "mood of an unknown resident")
                    )
        return failures

    def validate_unit_events(self, observation: TickObservation) -> list[Failure]:
        """Unit events must follow the engine's assignments (dispatch rules)."""
        return dispatch.validate_events(self.state, observation)

    # --- phases ------------------------------------------------------------------------

    def _process(self, observation: TickObservation) -> tuple[TickOutcome, StateHash]:
        tick = observation.tick
        self.state.tick = tick
        parts = TickParts()
        self.phase_events_and_timers(tick, parts)
        self.phase_infrastructure(observation, parts)
        self.phase_due_removals(tick, parts)
        self.phase_staged_decisions(tick, parts)
        self.phase_dispatch(observation, parts)
        self.phase_residents_and_politics(observation, parts)
        status = self.phase_metrics_and_removal(observation, parts)
        return self.publish(tick, status, parts)

    def phase_events_and_timers(self, tick: int, parts: TickParts) -> None:
        """Phase 1: activate disruptions and resolve due timers."""

    def phase_infrastructure(self, observation: TickObservation, parts: TickParts) -> None:
        """Phase 2: accept the incidents and unit availability the game observed."""
        state = self.state
        for item in observation.incidents:
            incident = state.incidents.get(item.id)
            if incident is None:
                incident = Incident.from_observation(item, observation.tick)
                state.incidents[item.id] = incident
            else:
                incident.update(item)
        out = set(observation.out_of_service)
        for unit in state.units.values():
            unit.reported_out = unit.id in out
            if unit.reported_out and unit.state == "available":
                unit.state, unit.since_tick = "out_of_service", observation.tick
            elif not unit.reported_out and unit.state == "out_of_service":
                unit.state, unit.since_tick = "available", observation.tick
        parts.arrivals = dispatch.apply_events(state, observation, parts.releases)

    def phase_due_removals(self, tick: int, parts: TickParts) -> None:
        """Phase 3: removal outcomes already due (recall vote closing at this tick)."""

    def phase_staged_decisions(self, tick: int, parts: TickParts) -> None:
        """Phase 4: revalidate and apply decisions whose apply tick is this tick."""

    def phase_dispatch(self, observation: TickObservation, parts: TickParts) -> None:
        """Phase 5: release units of resolved incidents, standing 911 dispatch, retire them."""
        tick = observation.tick
        dispatch.release_resolved(self.state, tick, parts.releases)
        dispatch.run_dispatch(
            self.state,
            self.setup.catalogs.dispatch,
            tick,
            dispatch.route_table(observation),
            parts.assignments,
            parts.queue,
            parts.warnings,
        )
        self.retire_resolved(tick)

    def retire_resolved(self, tick: int) -> None:
        for incident_id in sorted(self.state.incidents):
            if self.state.incidents[incident_id].status == "resolved":
                del self.state.incidents[incident_id]
                self.state.resolved[incident_id] = tick

    def phase_residents_and_politics(self, observation: TickObservation, parts: TickParts) -> None:
        """Phase 6: residents who joined (seeded top-up of LLM modes), then politics."""
        joined = sorted(observation.residents_joined)
        if not joined:
            return
        state = self.state
        added = residents.top_up(
            len(state.resident_ids), len(state.llm_ids), joined, self.config.llm_ratio_bp, self.rng
        )
        state.resident_ids = sorted(state.resident_ids + joined)
        state.llm_ids = sorted(state.llm_ids + added)
        chosen = set(added)
        parts.resident_modes = {str(resident_id): resident_id in chosen for resident_id in joined}

    def phase_metrics_and_removal(
        self, observation: TickObservation, parts: TickParts
    ) -> RunStatusLabel:
        """Phase 7: metrics, then newly achieved removal; the duration ends the run."""
        self.state.satisfaction = observation.satisfaction
        if observation.tick >= self.config.duration:
            self.end_reason = "duration reached"
            return "completed"
        return "running"

    def publish(
        self, tick: int, status: RunStatusLabel, parts: TickParts
    ) -> tuple[TickOutcome, StateHash]:
        """Phase 8: hash the state and build the outcome."""
        state_hash = hash_state(self.state.to_state())
        self.last_hash = state_hash
        outcome = TickOutcome(
            run_id=self.run_id,
            run_epoch=self.run_epoch,
            tick=tick,
            effective_tick=tick + 1,
            status=status,
            units=[unit.view() for unit in self.state.units.values()],
            assignments=parts.assignments,
            releases=parts.releases,
            queue=parts.queue,
            resident_modes=parts.resident_modes,
            authority=AuthorityView(value=self.state.authority, changes=parts.authority_changes),
            politics=self.politics_status(),
            mayor=self.mayor_status(),
            state_hash=state_hash.value,
            warnings=parts.warnings,
        )
        return outcome, state_hash

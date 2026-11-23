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
from aiautonomy.engines.contract.decisions import (
    AuthorityChange,
    MayorDecisionRecord,
    OrderRecord,
    ResidentAction,
    ResidentDecisionAccepted,
    ResidentDecisionRequest,
)
from aiautonomy.engines.contract.dispatch import Assignment, QueueEntry, Release
from aiautonomy.engines.contract.disruptions import (
    DisruptionInjectRequest,
    DisruptionRecord,
)
from aiautonomy.engines.contract.maps import MapRef, MapRevision
from aiautonomy.engines.contract.politics import PoliticalStatus, RemovalRecord
from aiautonomy.engines.contract.runs import (
    AuthorityView,
    CatalogRef,
    IncidentObservation,
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
from aiautonomy.engines.core.rng import KeyedRng, derive_stream_seeds
from aiautonomy.engines.hybrid import dispatch, disruptions, politics, residents
from aiautonomy.engines.hybrid.catalogs import Catalogs
from aiautonomy.engines.hybrid.desk import MayorDesk
from aiautonomy.engines.hybrid.dispatch import RouteTable
from aiautonomy.engines.hybrid.disruptions import Disruption
from aiautonomy.engines.hybrid.errors import RunError
from aiautonomy.engines.hybrid.resident_desk import ResidentDesk
from aiautonomy.engines.hybrid.state import HybridState, Incident
from aiautonomy.engines.mayor.providers import BaselineProvider, MayorProvider
from aiautonomy.engines.residents.llm import LocalResidentProvider, ResidentProvider
from aiautonomy.engines.sim.config import InferenceSettings, RunConfig
from aiautonomy.engines.world.boston import BostonWorldConfig
from aiautonomy.engines.world.maps import LevelBounds

HISTORY_TICKS = 64
"""Processed ticks whose outcome is kept for idempotent reposts."""
GAME_INCIDENT_PREFIX = "game-"
ENGINE_INCIDENT_PREFIX = "inc-"


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
    bounds: LevelBounds
    inference: InferenceSettings

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
    disruptions_started: list[DisruptionRecord] = field(default_factory=list)
    disruptions_ended: list[DisruptionRecord] = field(default_factory=list)
    orders: list[OrderRecord] = field(default_factory=list)
    decisions: list[MayorDecisionRecord] = field(default_factory=list)
    routes: RouteTable = field(default_factory=dict)
    order_links: dict[str, str | None] = field(default_factory=dict)
    resident_actions: list[ResidentAction] = field(default_factory=list)
    acts: list[tuple[int, str]] = field(default_factory=list)
    removal: RemovalRecord | None = None


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
        provider: MayorProvider | None = None,
        resident_provider: ResidentProvider | None = None,
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
            setup.map_revision.content,
            config.population,
            llm_ids,
            setup.catalogs.politics.authority.initial,
        )
        self.status: RunStatusLabel = "running"
        self.end_reason: str | None = None
        self.sinks: list[HybridSink] = list(sinks)
        self._history: OrderedDict[int, tuple[str, TickOutcome]] = OrderedDict()
        self.desk = MayorDesk(self, provider or BaselineProvider(), setup.inference.mayor_wait_s)
        inference = setup.inference
        self.resident_desk = ResidentDesk(
            self,
            resident_provider
            or LocalResidentProvider(inference.resident_model, inference.resident_wait_s),
            inference.resident_wait_s,
            inference.resident_batch_max,
        )
        launch = setup.request.disruptions
        self.planned = (
            disruptions.plan_automatic(
                self.world.automatic_disruptions,
                config.duration,
                setup.map_revision.content,
                setup.bounds,
                self.rng,
            )
            if launch.automatic
            else []
        )
        scheduled = sorted(
            enumerate(launch.scheduled), key=lambda item: (item[1].at_tick or 0, item[0])
        )
        created = [
            self._create_disruption(
                spec.type,
                "scheduled",
                spec.at_tick or disruptions.FIRST_START_TICK,
                spec.x,
                spec.z,
                spec.radius_m,
                spec.intensity,
                spec.duration_ticks,
                None,
            )
            for _, spec in scheduled
        ]
        self.last_hash: StateHash = hash_state(self.state.to_state())
        for sink in self.sinks:
            sink.on_launch(self)
        for disruption in created:
            self._record_disruption(disruption, None)

    # --- views -------------------------------------------------------------------------

    @property
    def tick(self) -> int:
        return self.state.tick

    @property
    def controller(self) -> ControllerLabel:
        return self.desk.controller()

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
            scheduled_disruptions=self.scheduled_records(),
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
            removal=self.state.politics.removal,
            decisions=len(self.state.decisions),
            orders=len(self.state.orders),
        )

    def politics_status(self) -> PoliticalStatus:
        state = self.state
        return politics.status(
            state.politics,
            self.setup.catalogs.politics,
            state.authority,
            len(state.resident_ids),
            state.tick,
        )

    def request_residents(self, body: ResidentDecisionRequest) -> ResidentDecisionAccepted:
        return self.resident_desk.request(body)

    # --- disruptions --------------------------------------------------------------------

    def _create_disruption(
        self,
        kind: str,
        source: str,
        start: int,
        x: float,
        z: float,
        radius: int | None,
        intensity: int | None,
        duration: int | None,
        request_id: str | None,
    ) -> Disruption:
        spec = self.setup.catalogs.disruption(kind)
        disruption = Disruption(
            id=self.state.ids.next_id("dis"),
            type=kind,
            source=source,
            status="scheduled",
            start_tick=start,
            end_tick=start + (duration or spec.duration_ticks),
            x=x,
            z=z,
            radius_m=radius or spec.radius_m,
            intensity=intensity or spec.intensity,
            incident_id=self.state.ids.next_id("inc"),
            request_id=request_id,
            accepted_after_tick=self.state.tick,
        )
        self.state.disruptions[disruption.id] = disruption
        return disruption

    def disruption_record(
        self, disruption: Disruption, status: str | None = None
    ) -> DisruptionRecord:
        spec = self.setup.catalogs.disruption(disruption.type)
        return disruption.record(spec, self.setup.catalogs, status)  # type: ignore[arg-type]

    def _record_disruption(self, disruption: Disruption, spec_json: dict[str, Any] | None) -> None:
        entry = {
            "kind": "disruption",
            "source": disruption.source,
            "accepted_after_tick": disruption.accepted_after_tick,
            "request_id": disruption.request_id,
            "spec": spec_json,
            "record": self.disruption_record(disruption).model_dump(mode="json"),
        }
        for sink in self.sinks:
            sink.on_intervention(self, entry)

    def scheduled_records(self) -> list[DisruptionRecord]:
        return [
            self.disruption_record(d)
            for d in self.state.disruptions.values()
            if d.source == "scheduled"
        ]

    def mayor_office_outage(self, tick: int) -> bool:
        """An active outage covers the mayor office at `tick` (the mayor is offline)."""
        office = disruptions.mayor_office_position(self.setup.map_revision.content)
        for disruption in self.state.disruptions.values():
            spec = self.setup.catalogs.disruption(disruption.type)
            end = disruption.ended_tick
            if end is None:
                end = disruption.final_tick(spec)
            if (
                spec.effects.mayor_office_outage
                and disruption.start_tick <= tick < end
                and disruptions.covers(disruption, *office)
            ):
                return True
        return False

    def inject(self, request: DisruptionInjectRequest) -> tuple[DisruptionRecord, bool]:
        """Accept a user-injected disruption; reposting the same request id is idempotent."""
        if request.run_epoch != self.run_epoch:
            raise RunError(
                409,
                "stale_epoch",
                f"run {self.run_id} is at epoch {self.run_epoch}, not {request.run_epoch}",
            )
        spec_json = request.disruption.model_dump(mode="json")
        digest = hashlib.sha256(canonical_json(spec_json).encode("utf-8")).hexdigest()
        known = self.state.injections.get(request.request_id)
        if known is not None:
            if known[0] != digest:
                raise RunError(
                    409, "request_conflict", f"request {request.request_id} had another body"
                )
            return self.disruption_record(self.state.disruptions[known[1]]), True
        if self.status != "running":
            raise RunError(409, "run_ended", f"run {self.run_id} ended ({self.status})")
        earliest = self.state.tick + 2
        failures = disruptions.check_spec(
            request.disruption,
            earliest=earliest,
            duration=self.config.duration,
            bounds=self.setup.bounds,
            entity=request.request_id,
            require_tick=False,
        )
        if failures:
            raise RunError(422, failures[0].code, "the disruption is not valid", failures)
        spec = request.disruption
        disruption = self._create_disruption(
            spec.type,
            "injected",
            spec.at_tick if spec.at_tick is not None else earliest,
            spec.x,
            spec.z,
            spec.radius_m,
            spec.intensity,
            spec.duration_ticks,
            request.request_id,
        )
        self.state.injections[request.request_id] = (digest, disruption.id)
        self._record_disruption(disruption, spec_json)
        return self.disruption_record(disruption), False

    def _announce_disruptions(self, tick: int, parts: TickParts) -> None:
        """Announce the disruptions starting and ending at tick + 1 (phase 8)."""
        upcoming = tick + 1
        for plan in self.planned:
            if plan.start_tick == upcoming:
                created = self._create_disruption(
                    plan.type, "automatic", upcoming, plan.x, plan.z, None, None, None, None
                )
                self._record_disruption(created, None)
        ordered = sorted(self.state.disruptions.values(), key=lambda d: (d.start_tick, d.id))
        for disruption in ordered:
            spec = self.setup.catalogs.disruption(disruption.type)
            if disruption.status == "scheduled" and disruption.start_tick == upcoming:
                parts.disruptions_started.append(self.disruption_record(disruption))
            elif disruption.status in ("active", "recovering") and disruption.ended_tick is None:
                cleared = (
                    spec.recovery.mode == "on_clear"
                    and disruption.incident_id in self.state.resolved
                )
                if cleared or disruption.final_tick(spec) <= upcoming:
                    disruption.ended_tick = upcoming
                    parts.disruptions_ended.append(self.disruption_record(disruption, "ended"))

    def mayor_status(self) -> MayorStatus:
        return self.desk.status(self.state.tick)

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
        """Reset, cancel or shutdown: discard the decision in flight, then end."""
        if self.status == "running":
            self.desk.cancel(reason)
            self.resident_desk.cancel(reason)
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
        await self.desk.await_due(observation.tick)
        await self.resident_desk.await_due(observation.tick)
        if self.status != "running":  # reset or cancelled while waiting for the mayor
            raise RunError(409, "run_ended", f"run {self.run_id} ended ({self.status})")
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
            failures.extend(self._check_disruption_incident(item, observation.tick))
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

    def _check_disruption_incident(self, item: IncidentObservation, tick: int) -> list[Failure]:
        """`inc-` incidents belong to a started disruption of the same kind."""
        if not item.id.startswith(ENGINE_INCIDENT_PREFIX):
            if item.disruption_id is not None:
                return [_fail("disruption_mismatch", item.id, "game- incidents have no disruption")]
            return []
        owner = next((d for d in self.state.disruptions.values() if d.incident_id == item.id), None)
        if owner is None or owner.start_tick > tick:
            return [_fail("unknown_disruption_incident", item.id, "no started disruption owns it")]
        if item.kind != self.setup.catalogs.disruption(owner.type).incident.kind:
            return [_fail("incident_kind_mismatch", item.id, f"{owner.id} spawns {owner.type}")]
        if item.disruption_id is not None and item.disruption_id != owner.id:
            return [_fail("disruption_mismatch", item.id, f"the incident belongs to {owner.id}")]
        return []

    def validate_unit_events(self, observation: TickObservation) -> list[Failure]:
        """Unit events must follow the engine's assignments (dispatch rules)."""
        return dispatch.validate_events(self.state, observation)

    # --- phases ------------------------------------------------------------------------

    def _process(self, observation: TickObservation) -> tuple[TickOutcome, StateHash]:
        tick = observation.tick
        self.state.tick = tick
        parts = TickParts(routes=dispatch.route_table(observation))
        self.phase_events_and_timers(tick, parts)
        self.phase_infrastructure(observation, parts)
        self.phase_due_removals(tick, parts)
        if parts.removal is not None:  # removal in phase 3 skips straight to publishing
            self.state.satisfaction = observation.satisfaction
            return self.publish(tick, "removed", parts)
        self.phase_staged_decisions(observation, parts)
        self.phase_dispatch(observation, parts)
        self.phase_residents_and_politics(observation, parts)
        status = self.phase_metrics_and_removal(observation, parts)
        return self.publish(tick, status, parts)

    def phase_events_and_timers(self, tick: int, parts: TickParts) -> None:
        """Phase 1: activate disruptions and resolve due timers."""
        for disruption in self.state.disruptions.values():
            spec = self.setup.catalogs.disruption(disruption.type)
            if disruption.status == "scheduled" and disruption.start_tick <= tick:
                disruption.status = "active"
            if disruption.ended_tick is not None and disruption.ended_tick <= tick:
                disruption.status = "ended"
            elif (
                disruption.status == "active"
                and spec.recovery.mode == "gradual"
                and tick >= disruption.end_tick
            ):
                disruption.status = "recovering"
        self.desk.phase_timers(tick, parts)

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
        parts.order_links = {unit.id: unit.order_id for unit in state.units.values()}
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
        result = politics.TickPolitics(authority=self.state.authority)
        politics.resolve_due(self.state.politics, self.setup.catalogs.politics, tick, result)
        self._record_politics(result.events)
        if result.removal is not None:
            self._remove(result.removal, parts)

    def phase_staged_decisions(self, observation: TickObservation, parts: TickParts) -> None:
        """Phase 4: revalidate and apply decisions whose apply tick is this tick."""
        self.desk.apply_due(observation.tick, observation, parts)
        parts.acts = self.resident_desk.apply_due(observation.tick, parts)

    def phase_dispatch(self, observation: TickObservation, parts: TickParts) -> None:
        """Phase 5: release units of resolved incidents, standing 911 dispatch, retire them."""
        tick = observation.tick
        dispatch.release_resolved(self.state, tick, parts.releases)
        dispatch.run_dispatch(
            self.state,
            self.setup.catalogs.dispatch,
            tick,
            parts.routes,
            parts.assignments,
            parts.queue,
            parts.warnings,
        )
        self.retire_resolved(tick)
        self.desk.track_orders(parts.order_links, tick, parts)

    def retire_resolved(self, tick: int) -> None:
        for incident_id in sorted(self.state.incidents):
            if self.state.incidents[incident_id].status == "resolved":
                del self.state.incidents[incident_id]
                self.state.resolved[incident_id] = tick

    def phase_residents_and_politics(self, observation: TickObservation, parts: TickParts) -> None:
        """Phase 6: residents who joined (seeded top-up of LLM modes), then politics."""
        self._politics(observation, parts)
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
        self.desk.phase_outcomes(observation.tick, observation.satisfaction, parts)
        if observation.tick >= self.config.duration:
            self.end_reason = "duration reached"
            return "completed"
        return "running"

    def _record_politics(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            for sink in self.sinks:
                sink.on_decision(self, {"kind": "politics"} | event)

    def _remove(self, removal: RemovalRecord, parts: TickParts) -> None:
        """END-03: record the mechanisms; the run freezes as removed at this tick."""
        self.state.politics.removal = removal
        parts.removal = removal
        self.end_reason = removal.detail
        self._record_politics([{"event": "removal"} | removal.model_dump(mode="json")])

    def _politics(self, observation: TickObservation, parts: TickParts) -> None:
        """Phase 6: LLM residents' political acts, routine rules, then movement and authority."""
        state = self.state
        rules = self.setup.catalogs.politics
        tick = observation.tick
        result = politics.TickPolitics(authority=state.authority)
        if any(c.reason == "excess_order" and c.tick == tick for c in parts.authority_changes):
            state.politics.last_loss_tick = tick
        for resident, action in parts.acts:
            if action == "sign_petition":
                politics.sign(state.politics, resident, tick)
            elif action in ("vote_retain", "vote_replace"):
                politics.cast(state.politics, resident, action.removeprefix("vote_"), tick, result)
            elif action in ("peaceful_protest", "road_blockade"):
                politics.join(state.politics, resident, tick)
        if tick % self.world.politics_interval_ticks == 0:
            llm = set(state.llm_ids)
            routine = [rid for rid in state.resident_ids if rid not in llm]
            if observation.resident_moods is None:
                if routine:
                    parts.warnings.append(
                        Failure(
                            code="moods_missing",
                            message="no resident moods on a politics "
                            "tick: routine residents took no political action",
                        )
                    )
            else:
                moods = {m.id: m.mood for m in observation.resident_moods}
                politics.routine_politics(state.politics, rules, tick, moods, routine, result)
        politics.advance(state.politics, rules, tick, state.resident_ids, state.authority, result)
        if result.authority != state.authority or result.changes:
            state.authority = result.authority
            state.authority_log.extend(result.changes)
            parts.authority_changes.extend(result.changes)
        parts.warnings.extend(result.warnings)
        self._record_politics(result.events)

    def publish(
        self, tick: int, status: RunStatusLabel, parts: TickParts
    ) -> tuple[TickOutcome, StateHash]:
        """Phase 8: announce the next tick's disruptions, hash the state, build the outcome."""
        if status == "running":
            self._announce_disruptions(tick, parts)
            self.desk.opportunity(tick, parts.routes, parts)
        else:
            reason = "the mayor was removed" if status == "removed" else f"the run ended ({status})"
            self.desk.cancel(reason)
            self.resident_desk.cancel(reason)
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
            orders=parts.orders,
            decisions=parts.decisions,
            resident_actions=parts.resident_actions,
            removal=parts.removal,
            resident_modes=parts.resident_modes,
            disruptions_started=parts.disruptions_started,
            disruptions_ended=parts.disruptions_ended,
            authority=AuthorityView(value=self.state.authority, changes=parts.authority_changes),
            politics=self.politics_status(),
            mayor=self.mayor_status(),
            state_hash=state_hash.value,
            warnings=parts.warnings,
        )
        return outcome, state_hash

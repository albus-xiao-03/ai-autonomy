"""Run launch, the per-tick game observation and the engine's tick outcome.

The game posts exactly one `TickObservation` per game tick (`tick = last + 1`). The engine
runs the SIM-02 phases for that tick and answers with a `TickOutcome`; the game applies the
outcome's effects from `effective_tick` (= tick + 1). Reposting an identical observation returns
the stored outcome; a different body for a processed tick, a gap, an old epoch or an ended run
is rejected with 409 and an error code (docs/contract.md).

REQ: ARCH-02, ARCH-03, SIM-03, SIM-05, RES-06
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from aiautonomy.engines.contract.common import (
    ContractModel,
    ControllerLabel,
    EntityId,
    Failure,
    MayorBackend,
    Meters,
    Percent,
    ResidentId,
    RunStatusLabel,
    Tick,
)
from aiautonomy.engines.contract.decisions import (
    AuthorityChange,
    MayorDecisionRecord,
    OrderRecord,
    ResidentAction,
)
from aiautonomy.engines.contract.dispatch import (
    Assignment,
    IncidentKind,
    QueueEntry,
    Release,
    UnitView,
)
from aiautonomy.engines.contract.disruptions import DisruptionRecord, DisruptionSpec
from aiautonomy.engines.contract.maps import MapRef
from aiautonomy.engines.contract.politics import PoliticalStatus, RemovalRecord


class LaunchDisruptions(ContractModel):
    automatic: bool = Field(default=True, description="Seeded automatic disruptions.")
    scheduled: list[DisruptionSpec] = Field(default_factory=list, max_length=100)


class RunLaunchRequest(ContractModel):
    """`POST /api/runs`: launch a run pinned to one map revision."""

    map: MapRef
    scenario: str = Field(default="boston", pattern=r"^[a-z][a-z0-9_-]*$", max_length=64)
    seed: int | None = Field(default=None, ge=0, le=2**53 - 1)
    duration: int | None = Field(default=None, ge=1, le=100_000)
    population: int = Field(ge=0, le=100_000, description="Residents 0..population-1.")
    llm_ratio_bp: int = Field(ge=0, le=10_000, description="LLM share in basis points.")
    mayor_backend: MayorBackend = "local"
    disruptions: LaunchDisruptions = Field(default_factory=LaunchDisruptions)


class ResidentModes(ContractModel):
    """Seeded LLM assignment: llm_count = (population × ratio_bp + 5000) // 10000."""

    population: int = Field(ge=0)
    llm_ratio_bp: int = Field(ge=0, le=10_000)
    llm_count: int = Field(ge=0)
    llm_ids: list[ResidentId]


class CatalogRef(ContractModel):
    id: str
    version: int
    path: str
    sha256: str


class RunConfigView(ContractModel):
    scenario: str
    seed: int
    duration: int
    start_minute_of_day: int
    mayor_interval: int
    mayor_latency_ticks: int
    resident_latency_ticks: int
    outcome_window_ticks: int
    politics_interval_ticks: int


class RunHandle(ContractModel):
    """Answer to launch and reset."""

    contract_version: int
    run_id: str
    run_epoch: int = Field(ge=1)
    status: RunStatusLabel
    tick: Tick = Field(description="Last processed tick (0 before the first).")
    map: MapRef
    config: RunConfigView
    mayor_backend: MayorBackend
    controller: ControllerLabel
    residents: ResidentModes
    units: list[UnitView]
    catalogs: list[CatalogRef]
    scheduled_disruptions: list[DisruptionRecord] = Field(
        default_factory=list,
        description="Launch-scheduled disruptions (automatic ones stay hidden until they start).",
    )


class EpochRequest(ContractModel):
    """Body of `reset` and `cancel`; the epoch must match the run's."""

    run_epoch: int = Field(ge=1)


IncidentStatus = Literal["active", "recovering", "resolved"]


class IncidentObservation(ContractModel):
    """One incident as the game sees it. Report it with `resolved` once before dropping it."""

    id: EntityId
    kind: IncidentKind
    severity: int = Field(ge=0, le=100)
    opened_tick: Tick
    status: IncidentStatus
    x: Meters
    z: Meters
    district: str = Field(default="", max_length=64)
    disruption_id: EntityId | None = None


class RouteObservation(ContractModel):
    """Route availability from a unit's position to an incident on the current game graph."""

    unit_id: EntityId
    incident_id: EntityId
    reachable: bool
    travel_ticks: int | None = Field(default=None, ge=1, le=10_000)

    @model_validator(mode="after")
    def _travel_matches_reachability(self) -> Self:
        if self.reachable != (self.travel_ticks is not None):
            raise ValueError("travel_ticks must be set exactly when reachable is true")
        return self


UnitEventKind = Literal["arrived", "cleared"]


class UnitEvent(ContractModel):
    """A physical outcome: a unit reached its incident, or finished its service there."""

    unit_id: EntityId
    incident_id: EntityId
    event: UnitEventKind


class ResidentMood(ContractModel):
    id: ResidentId
    mood: Percent


class TickObservation(ContractModel):
    """`POST /api/runs/{run_id}/ticks`: what the game observed after simulating `tick`."""

    run_epoch: int = Field(ge=1)
    tick: Tick = Field(ge=1)
    satisfaction: Percent
    incidents: list[IncidentObservation] = Field(default_factory=list, max_length=200)
    routes: list[RouteObservation] = Field(
        default_factory=list,
        max_length=5000,
        description="Every (available unit, unresolved incident) pair; see docs/contract.md.",
    )
    unit_events: list[UnitEvent] = Field(default_factory=list, max_length=200)
    out_of_service: list[EntityId] = Field(default_factory=list, max_length=200)
    residents_joined: list[ResidentId] = Field(default_factory=list, max_length=10_000)
    resident_moods: list[ResidentMood] | None = Field(
        default=None, max_length=100_000, description="Required on politics ticks."
    )


class AuthorityView(ContractModel):
    value: int = Field(ge=0, le=100)
    changes: list[AuthorityChange] = Field(default_factory=list)


MayorState = Literal["idle", "deciding", "offline", "removed"]


class MayorStatus(ContractModel):
    backend: MayorBackend
    controller: ControllerLabel
    state: MayorState
    pending_decision_id: EntityId | None = None
    next_opportunity_tick: Tick | None = None


class TickOutcome(ContractModel):
    """The engine's answer for one tick; effects apply in the game from `effective_tick`."""

    run_id: str
    run_epoch: int
    tick: Tick
    effective_tick: Tick
    status: RunStatusLabel
    units: list[UnitView]
    assignments: list[Assignment] = Field(default_factory=list)
    releases: list[Release] = Field(default_factory=list)
    queue: list[QueueEntry] = Field(default_factory=list)
    orders: list[OrderRecord] = Field(default_factory=list)
    decisions: list[MayorDecisionRecord] = Field(default_factory=list)
    resident_actions: list[ResidentAction] = Field(default_factory=list)
    resident_modes: dict[str, bool] = Field(
        default_factory=dict, description="Mode of residents who joined this tick (true = LLM)."
    )
    disruptions_started: list[DisruptionRecord] = Field(default_factory=list)
    disruptions_ended: list[DisruptionRecord] = Field(default_factory=list)
    authority: AuthorityView
    politics: PoliticalStatus
    mayor: MayorStatus
    removal: RemovalRecord | None = None
    state_hash: str
    warnings: list[Failure] = Field(default_factory=list)


class RunSummary(ContractModel):
    """`GET /api/runs/{run_id}` and the answer to `cancel`."""

    run_id: str
    run_epoch: int
    status: RunStatusLabel
    tick: Tick
    map: MapRef
    mayor_backend: MayorBackend
    authority: int
    removal: RemovalRecord | None = None
    decisions: int
    orders: int

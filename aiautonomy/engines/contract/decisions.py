"""Decision identity, mayor options and records, exceptional orders, authority changes, and
run-scoped resident decisions.

Every model request and reply carries the run, epoch, actor, decision id, observation id and
the observation and apply ticks (ARCH-02). A reply takes effect at its fixed apply tick; a
reply for another run or epoch, an unknown or already-resolved decision, or a mismatched
observation is rejected.

REQ: ARCH-02, MAY-01, MAY-03, MAY-04, MAY-05, MAY-06, MAY-08, SIM-03, SIM-05
"""

from typing import Annotated, Literal

from pydantic import Field

from aiautonomy.engines.contract.common import (
    ContractModel,
    ControllerLabel,
    Department,
    EntityId,
    MayorBackend,
    Percent,
    ResidentId,
    Sha256Hex,
    Tick,
)

ActorId = Annotated[str, Field(pattern=r"^(mayor|resident:[0-9]{1,7})$")]


class DecisionEnvelope(ContractModel):
    run_id: str = Field(min_length=1, max_length=128)
    run_epoch: int = Field(ge=1)
    actor_id: ActorId
    decision_id: EntityId
    observation_id: Sha256Hex = Field(description="SHA-256 of the canonical observation.")
    observation_tick: Tick
    apply_tick: Tick = Field(description="Fixed at request time; never wall-clock dependent.")
    schema_version: int = 1


ActionKind = Literal["dispatch", "prioritize", "hold"]


class ActionOption(ContractModel):
    """One permitted mayor action, derived from the recorded incident and unit state."""

    id: str = Field(pattern=r"^(A[0-9]{1,3}|HOLD)$")
    kind: ActionKind
    department: Department | None = None
    incident_id: EntityId | None = None
    units: int | None = Field(default=None, ge=1, le=5)
    summary: str = Field(max_length=200)


class MayorProposal(ContractModel):
    """The model's structured answer: one option id plus an optional public statement."""

    action: str = Field(pattern=r"^(A[0-9]{1,3}|HOLD)$")
    statement: str = Field(default="", max_length=280)


DecisionOutcome = Literal["pending", "accepted", "rejected", "hold", "cancelled", "stale"]


class SatisfactionPoint(ContractModel):
    tick: Tick
    value: Percent


class MayorDecisionRecord(ContractModel):
    """One mayor decision from request to outcome (`decisions.jsonl`)."""

    envelope: DecisionEnvelope
    backend: MayorBackend
    model: str
    controller: ControllerLabel
    options: list[ActionOption]
    proposal: MayorProposal | None = None
    outcome: DecisionOutcome
    reason: str | None = Field(default=None, max_length=300)
    order_id: EntityId | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    satisfaction_before: SatisfactionPoint
    satisfaction_after: SatisfactionPoint | None = Field(
        default=None, description="Observed `outcome_window_ticks` after the apply tick."
    )
    missed_opportunities: int = Field(
        default=0, ge=0, description="Opportunities skipped during the same outage (one hold)."
    )


OrderKind = Literal["dispatch", "prioritize"]
OrderStatus = Literal["accepted", "rejected"]


class OrderOrigin(ContractModel):
    actor: Literal["mayor"] = "mayor"
    backend: MayorBackend
    model: str
    decision_id: EntityId


class OrderAuthority(ContractModel):
    """The political cost of one accepted order (rolling allowance and penalty)."""

    counted: bool = Field(description="False for a repeat of the same order key in the window.")
    distinct_key: str = Field(description="kind:department:incident.")
    window_ticks: int = Field(ge=1)
    window_count: int = Field(ge=0, description="Distinct accepted orders in the window.")
    allowance: int = Field(ge=0)
    penalty: int = Field(ge=0)
    before: int = Field(ge=0, le=100)
    after: int = Field(ge=0, le=100)


class Arrival(ContractModel):
    unit_id: EntityId
    tick: Tick


class OrderOutcome(ContractModel):
    """Measured outcome, filled from later game observations."""

    arrivals: list[Arrival] = Field(default_factory=list)
    cleared_tick: Tick | None = None
    incident_resolved_tick: Tick | None = None


class OrderRecord(ContractModel):
    """An exceptional department-level order with its origin, units, outcome and cost."""

    order_id: EntityId
    decision_id: EntityId
    origin: OrderOrigin
    kind: OrderKind
    department: Department
    incident_id: EntityId
    requested_units: int = Field(ge=0, le=5)
    units: list[EntityId] = Field(default_factory=list)
    status: OrderStatus
    reason: str | None = Field(default=None, max_length=300)
    applied_tick: Tick
    priority_until_tick: Tick | None = None
    authority: OrderAuthority | None = None
    outcome: OrderOutcome = Field(default_factory=OrderOutcome)


AuthorityReason = Literal["excess_order", "protest_pressure", "recovery"]


class AuthorityChange(ContractModel):
    """One change of political authority (0–100). Satisfaction never changes authority."""

    tick: Tick
    delta: int
    value: int = Field(ge=0, le=100)
    reason: AuthorityReason
    ref: str | None = None


ResidentActionName = Literal[
    "follow_routine",
    "go_home",
    "visit_venue",
    "stay_put",
    "peaceful_protest",
    "sign_petition",
    "vote_retain",
    "vote_replace",
    "speeding",
    "vandalism",
    "road_blockade",
]


class ResidentObservation(ContractModel):
    """What one LLM resident sees (RES-05): own state, local conditions, no hidden events."""

    id: ResidentId
    activity: str = Field(max_length=32)
    district: str = Field(default="", max_length=64)
    mood: Percent
    grievances: list[Annotated[str, Field(max_length=80)]] = Field(
        default_factory=list, max_length=6
    )
    has_venue: bool = False
    at_home: bool = False


class ResidentDecisionRequest(ContractModel):
    """`POST /api/runs/{run_id}/residents`: LLM residents only, at most eight per request."""

    run_epoch: int = Field(ge=1)
    tick: Tick = Field(description="The last tick the game posted; decisions apply at +2.")
    residents: list[ResidentObservation] = Field(min_length=1, max_length=8)


class ResidentDecisionTicket(ContractModel):
    resident_id: ResidentId
    decision_id: EntityId
    apply_tick: Tick


class ResidentDecisionAccepted(ContractModel):
    run_id: str
    run_epoch: int
    model: str
    tickets: list[ResidentDecisionTicket]


class ResidentAction(ContractModel):
    """A resident decision, delivered in the outcome of its apply tick."""

    resident_id: ResidentId
    decision_id: EntityId
    action: ResidentActionName
    thought: str = Field(default="", max_length=140)
    apply_tick: Tick
    fallback: bool = Field(description="True when the model failed: routine behaviour.")
    reason: str | None = Field(default=None, max_length=200)

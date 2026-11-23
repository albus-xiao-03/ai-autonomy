"""Engine records of mayor decisions and exceptional orders (hashed with the run state).

REQ: MAY-05, MAY-06, ARCH-02
"""

from dataclasses import dataclass, field
from typing import Any

from aiautonomy.engines.contract.common import Department
from aiautonomy.engines.contract.decisions import (
    ActionOption,
    Arrival,
    MayorProposal,
    OrderAuthority,
    OrderOutcome,
)


@dataclass(slots=True)
class Decision:
    id: str
    observation_tick: int
    apply_tick: int
    observation_id: str
    options: list[ActionOption]
    satisfaction_before: float
    outcome: str = "pending"
    reason: str | None = None
    proposal: MayorProposal | None = None
    model: str = ""
    latency_ms: int | None = None
    order_id: str | None = None
    satisfaction_after: tuple[int, float] | None = None
    missed_opportunities: int = 0

    def to_state(self) -> dict[str, Any]:
        return {
            "observation_tick": self.observation_tick,
            "apply_tick": self.apply_tick,
            "observation_id": self.observation_id,
            "options": [option.model_dump(mode="json") for option in self.options],
            "satisfaction_before": self.satisfaction_before,
            "outcome": self.outcome,
            "reason": self.reason,
            "proposal": self.proposal.model_dump(mode="json") if self.proposal else None,
            "model": self.model,
            "order_id": self.order_id,
            "satisfaction_after": list(self.satisfaction_after)
            if self.satisfaction_after
            else None,
            "missed_opportunities": self.missed_opportunities,
        }


@dataclass(slots=True)
class Order:
    id: str
    decision_id: str
    kind: str
    department: Department
    incident_id: str
    requested_units: int
    status: str
    applied_tick: int
    backend: str
    model: str
    units: list[str] = field(default_factory=list)
    reason: str | None = None
    priority_until: int | None = None
    authority: OrderAuthority | None = None
    arrivals: list[tuple[str, int]] = field(default_factory=list)
    cleared_tick: int | None = None
    resolved_tick: int | None = None

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.department}:{self.incident_id}"

    def outcome(self) -> OrderOutcome:
        return OrderOutcome(
            arrivals=[Arrival(unit_id=unit, tick=tick) for unit, tick in self.arrivals],
            cleared_tick=self.cleared_tick,
            incident_resolved_tick=self.resolved_tick,
        )

    def to_state(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "kind": self.kind,
            "department": self.department,
            "incident_id": self.incident_id,
            "requested_units": self.requested_units,
            "status": self.status,
            "applied_tick": self.applied_tick,
            "units": list(self.units),
            "reason": self.reason,
            "priority_until": self.priority_until,
            "authority": self.authority.model_dump(mode="json") if self.authority else None,
            "arrivals": [list(item) for item in self.arrivals],
            "cleared_tick": self.cleared_tick,
            "resolved_tick": self.resolved_tick,
        }

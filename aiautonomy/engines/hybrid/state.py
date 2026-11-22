"""Authoritative engine state of a hybrid run, and its canonical (hashed) form.

The game owns positions and physics; the engine state holds what the engine decides and the
facts it accepted from validated observations: units and their assignments, the incidents the
game reported, resident modes, political authority and the id counters. `to_state()` is the
canonical form hashed every tick (one top-level key per subsystem, so replay can name the
subsystem that diverged).

REQ: SIM-04, SRV-01
"""

from dataclasses import dataclass, field
from typing import Any

from aiautonomy.engines.contract.common import Department
from aiautonomy.engines.contract.dispatch import UnitState as UnitStateName
from aiautonomy.engines.contract.dispatch import UnitView
from aiautonomy.engines.contract.maps import MapContent
from aiautonomy.engines.contract.runs import IncidentObservation
from aiautonomy.engines.core.ids import IdCounters
from aiautonomy.engines.hybrid.disruptions import Disruption


@dataclass(slots=True)
class Unit:
    id: str
    department: Department
    kind: str
    facility_id: str
    state: UnitStateName = "available"
    incident_id: str | None = None
    order_id: str | None = None
    origin: str | None = None
    since_tick: int = 0
    eta_tick: int | None = None
    arrived_tick: int | None = None
    reported_out: bool = False

    @property
    def available(self) -> bool:
        return self.state == "available"

    def view(self) -> UnitView:
        return UnitView(
            id=self.id,
            department=self.department,
            kind=self.kind,
            facility_id=self.facility_id,
            state=self.state,
            incident_id=self.incident_id,
            order_id=self.order_id,
            since_tick=self.since_tick,
        )

    def to_state(self) -> dict[str, Any]:
        return {
            "department": self.department,
            "state": self.state,
            "incident_id": self.incident_id,
            "order_id": self.order_id,
            "origin": self.origin,
            "since_tick": self.since_tick,
            "eta_tick": self.eta_tick,
            "arrived_tick": self.arrived_tick,
            "reported_out": self.reported_out,
        }


@dataclass(slots=True)
class Incident:
    id: str
    kind: str
    severity: int
    opened_tick: int
    status: str
    x: float
    z: float
    district: str
    disruption_id: str | None
    first_seen_tick: int
    queue_since: dict[str, int] = field(default_factory=dict)
    priority_until: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_observation(cls, item: IncidentObservation, tick: int) -> Incident:
        return cls(
            id=item.id,
            kind=item.kind,
            severity=item.severity,
            opened_tick=item.opened_tick,
            status=item.status,
            x=item.x,
            z=item.z,
            district=item.district,
            disruption_id=item.disruption_id,
            first_seen_tick=tick,
        )

    def update(self, item: IncidentObservation) -> None:
        self.severity = item.severity
        self.status = item.status
        self.x, self.z = item.x, item.z
        self.district = item.district

    def to_state(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "opened_tick": self.opened_tick,
            "status": self.status,
            "x": self.x,
            "z": self.z,
            "district": self.district,
            "disruption_id": self.disruption_id,
            "first_seen_tick": self.first_seen_tick,
            "queue_since": dict(sorted(self.queue_since.items())),
            "priority_until": dict(sorted(self.priority_until.items())),
        }


@dataclass(slots=True)
class HybridState:
    tick: int
    units: dict[str, Unit]
    resident_ids: list[int]
    llm_ids: list[int]
    authority: int
    incidents: dict[str, Incident] = field(default_factory=dict)
    resolved: dict[str, int] = field(default_factory=dict)
    satisfaction: float | None = None
    ids: IdCounters = field(default_factory=IdCounters)
    disruptions: dict[str, Disruption] = field(default_factory=dict)
    injections: dict[str, tuple[str, str]] = field(default_factory=dict)
    """Injection request id → (body digest, disruption id), for idempotent reposts."""

    @classmethod
    def initial(
        cls, content: MapContent, population: int, llm_ids: list[int], authority: int
    ) -> HybridState:
        units = {
            unit.id: Unit(
                id=unit.id,
                department=facility.department,
                kind=unit.kind,
                facility_id=facility.id,
            )
            for facility in content.facilities
            for unit in facility.units
        }
        return cls(
            tick=0,
            units=dict(sorted(units.items())),
            resident_ids=list(range(population)),
            llm_ids=list(llm_ids),
            authority=authority,
        )

    def to_state(self) -> dict[str, Any]:
        return {
            "clock": {"tick": self.tick},
            "units": {uid: self.units[uid].to_state() for uid in sorted(self.units)},
            "incidents": {iid: self.incidents[iid].to_state() for iid in sorted(self.incidents)},
            "resolved": dict(sorted(self.resolved.items())),
            "residents": {"ids": self.resident_ids, "llm": self.llm_ids},
            "authority": {"value": self.authority},
            "metrics": {"satisfaction": self.satisfaction},
            "ids": self.ids.to_state(),
            "disruptions": {
                "records": {
                    did: self.disruptions[did].to_state() for did in sorted(self.disruptions)
                },
                "injections": {rid: list(self.injections[rid]) for rid in sorted(self.injections)},
            },
        }

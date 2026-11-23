"""911 dispatch: incident kinds and their needs, unit states, assignments, releases and the queue.

Standing dispatch runs every tick without the mayor (SRV-07): incidents in order of severity
(highest first), then age (oldest first), then id; each unfilled department slot gets the
qualified, available unit with the shortest reachable travel time the game reported; unmet
demand is queued with a reason.

REQ: SRV-01, SRV-07
"""

from typing import Literal

from pydantic import Field

from aiautonomy.engines.contract.common import (
    ContractModel,
    Department,
    EntityId,
    Tick,
)

IncidentKind = Literal[
    "traffic",
    "outage",
    "gas_leakage",
    "flood",
    "storm",
    "snowstorm",
    "heavy_rain",
    "protest",
    "crime",
]
"""The seven disruption kinds, plus resident-driven `protest` and `crime` incidents."""


class Needs(ContractModel):
    """Units required per department."""

    police: int = Field(default=0, ge=0, le=10)
    fire: int = Field(default=0, ge=0, le=10)
    medical: int = Field(default=0, ge=0, le=10)


class IncidentKindSpec(ContractModel):
    """Catalog entry (`data/catalogs/dispatch.v1.yaml`)."""

    kind: IncidentKind
    label: str
    severity: int = Field(ge=1, le=100, description="Default severity when spawned.")
    needs: Needs


class IncidentCatalogView(ContractModel):
    """`GET /api/catalogs/incidents`."""

    version: int
    sha256: str
    kinds: list[IncidentKindSpec]


UnitState = Literal["available", "assigned", "on_scene", "out_of_service"]


class UnitView(ContractModel):
    """The engine's view of one unit after the tick."""

    id: EntityId
    department: Department
    kind: str
    facility_id: EntityId
    state: UnitState
    incident_id: EntityId | None = None
    order_id: EntityId | None = None
    since_tick: Tick


AssignmentOrigin = Literal["routine", "order"]


class Assignment(ContractModel):
    """A unit committed to an incident; the game starts moving it at `effective_tick`."""

    unit_id: EntityId
    department: Department
    incident_id: EntityId
    origin: AssignmentOrigin
    order_id: EntityId | None = None
    travel_ticks: int = Field(ge=1, le=10_000, description="As reported by the game graph.")
    assigned_tick: Tick
    eta_tick: Tick = Field(description="effective tick + travel ticks.")


ReleaseReason = Literal["cleared", "incident_resolved"]


class Release(ContractModel):
    """A unit back in service after its incident was cleared or resolved."""

    unit_id: EntityId
    incident_id: EntityId
    tick: Tick
    reason: ReleaseReason


QueueReason = Literal[
    "no_qualified_unit",
    "all_units_busy",
    "unreachable",
    "route_not_reported",
    "out_of_service",
]


class QueueEntry(ContractModel):
    """Unmet demand of one department at one incident."""

    incident_id: EntityId
    department: Department
    needed: int = Field(ge=1, le=10)
    reason: QueueReason
    since_tick: Tick

"""The seven disruption types, their catalog entries, scheduled/injected specs and records.

Exactly seven types exist: Traffic, Outage, Gas Leakage, Flood, Storm, Snowstorm and Heavy
Rain. The engine is the scheduler of record (automatic from the run seed, scheduled at launch,
or injected over REST); the game applies the physical effects from the record's start tick.

REQ: EVT-01, EVT-02, CUSTOM-01, CUSTOM-07
"""

from typing import Literal, get_args

from pydantic import Field

from aiautonomy.engines.contract.common import (
    ContractModel,
    EntityId,
    Meters,
    RequestId,
    Tick,
)
from aiautonomy.engines.contract.dispatch import IncidentKind, Needs

DisruptionType = Literal[
    "traffic", "outage", "gas_leakage", "flood", "storm", "snowstorm", "heavy_rain"
]
DISRUPTION_TYPES: tuple[str, ...] = get_args(DisruptionType)

DisruptionSource = Literal["automatic", "scheduled", "injected"]
DisruptionScope = Literal["area", "citywide"]
RecoveryMode = Literal["on_duration", "on_clear", "gradual"]
DisruptionStatus = Literal["scheduled", "active", "recovering", "ended"]


class DisruptionEffects(ContractModel):
    """Physical effects the game applies while the disruption is active."""

    scope: DisruptionScope = Field(description="`area`: within radius_m of (x, z).")
    speed_multiplier_bp: int = Field(
        ge=1, le=10_000, description="Travel speed in scope, basis points (10000 = unchanged)."
    )
    closes_roads: bool = Field(description="Close every road segment within the radius.")
    closes_tunnels: bool = Field(description="Close tunnel segments within the radius.")
    closes_low_roads: bool = Field(description="Close segments below ground level in radius.")
    signals_out: bool = Field(description="Traffic signals in the radius behave as stop signs.")
    damage_pct: int = Field(ge=0, le=100, description="One-time building damage at onset.")
    mayor_office_outage: bool = Field(
        description="The mayor is offline while active if the mayor office is in scope."
    )


class Recovery(ContractModel):
    """How the disruption ends and what persists."""

    mode: RecoveryMode = Field(
        description="`on_duration`: ends after duration_ticks. `on_clear`: ends when the "
        "responding units clear the incident (or after duration_ticks at the latest). "
        "`gradual`: after duration_ticks, speed stays at gradual_speed_multiplier_bp for "
        "gradual_ticks."
    )
    gradual_ticks: int = Field(default=0, ge=0, le=2000)
    gradual_speed_multiplier_bp: int = Field(default=10_000, ge=1, le=10_000)
    lasting: list[str] = Field(
        default_factory=list, description="Consequences that persist after the end."
    )


class IncidentTemplate(ContractModel):
    """The incident the game spawns for the disruption (id = the record's `incident_id`)."""

    kind: IncidentKind
    severity: int = Field(ge=1, le=100)
    needs: Needs


class DisruptionTypeSpec(ContractModel):
    """Catalog entry (`data/catalogs/disruptions.v1.yaml`)."""

    id: DisruptionType
    label: str
    description: str
    radius_m: int = Field(ge=10, le=5000)
    intensity: int = Field(ge=1, le=100)
    duration_ticks: int = Field(ge=1, le=2000)
    effects: DisruptionEffects
    recovery: Recovery
    incident: IncidentTemplate


class DisruptionSpec(ContractModel):
    """A scheduled or injected disruption; omitted values take the catalog defaults."""

    type: DisruptionType
    x: Meters
    z: Meters
    radius_m: int | None = Field(default=None, ge=10, le=5000)
    intensity: int | None = Field(default=None, ge=1, le=100)
    duration_ticks: int | None = Field(default=None, ge=1, le=2000)
    at_tick: Tick | None = Field(
        default=None, description="Start tick; omitted for injection = next tick boundary."
    )


class DisruptionRecord(ContractModel):
    """A disruption of record. Severity = template severity × intensity / 50, clamped."""

    id: EntityId
    type: DisruptionType
    label: str
    source: DisruptionSource
    status: DisruptionStatus
    start_tick: Tick
    end_tick: Tick = Field(description="Planned end (latest end for `on_clear`).")
    x: Meters
    z: Meters
    radius_m: int
    intensity: int
    effects: DisruptionEffects
    recovery: Recovery
    incident_id: EntityId = Field(description="Id the game must give the spawned incident.")
    incident: IncidentTemplate
    request_id: RequestId | None = None


class DisruptionInjectRequest(ContractModel):
    """`POST /api/runs/{run_id}/disruptions`. Reposting the same `request_id` is idempotent."""

    run_epoch: int = Field(ge=1)
    request_id: RequestId
    disruption: DisruptionSpec


class DisruptionInjectResponse(ContractModel):
    disruption: DisruptionRecord
    duplicate: bool = Field(description="True when this request_id was already accepted.")


class DisruptionCatalogView(ContractModel):
    """`GET /api/catalogs/disruptions`."""

    version: int
    sha256: str
    types: list[DisruptionTypeSpec]

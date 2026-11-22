"""Disruptions of record: the seven types, from three sources, with deterministic timing.

Sources:

- `scheduled`: listed in the launch request; recorded at launch.
- `automatic`: planned at launch from the `external_events` stream (types, sites and gaps),
  hidden until announced; recorded when announced.
- `injected`: `POST /api/runs/{id}/disruptions`; starts two ticks after the last processed tick
  (the earliest start the outcome channel can announce); recorded when accepted.

Timing: the outcome of tick `t` announces every disruption starting at `t + 1`
(`disruptions_started`) and every one whose effects end at `t + 1` (`disruptions_ended`).
Phase 1 of tick `t + 1` then marks them active or ended. `on_duration` ends at
start + duration; `on_clear` ends once its incident is resolved (at start + duration at the
latest); `gradual` is `recovering` for its gradual ticks after the duration. An ended
disruption removes only its own effects; lasting consequences (`recovery.lasting`) stay
(EVT-05, CUSTOM-06).

REQ: EVT-01, EVT-02, EVT-03, EVT-05, CUSTOM-01, CUSTOM-03, CUSTOM-06, CUSTOM-07
"""

from dataclasses import dataclass
from typing import Any

from aiautonomy.engines.contract.common import Failure
from aiautonomy.engines.contract.disruptions import (
    DISRUPTION_TYPES,
    DisruptionRecord,
    DisruptionSpec,
    DisruptionStatus,
    DisruptionTypeSpec,
    IncidentTemplate,
)
from aiautonomy.engines.contract.maps import MapContent
from aiautonomy.engines.core.rng import KeyedRng
from aiautonomy.engines.hybrid.catalogs import Catalogs, scaled_severity
from aiautonomy.engines.world.boston import AutomaticDisruptions
from aiautonomy.engines.world.maps import LevelBounds, distance

STREAM = "external_events"
FIRST_START_TICK = 2
"""A launch-scheduled disruption cannot start before tick 2: tick 1's effects were fixed at
launch, and the outcome of tick 1 is the first that can announce a start."""


@dataclass(frozen=True, slots=True)
class Planned:
    """One automatic disruption, fixed at launch and hidden until announced."""

    start_tick: int
    type: str
    x: float
    z: float


@dataclass(slots=True)
class Disruption:
    id: str
    type: str
    source: str
    status: DisruptionStatus
    start_tick: int
    end_tick: int
    x: float
    z: float
    radius_m: int
    intensity: int
    incident_id: str
    request_id: str | None
    accepted_after_tick: int
    ended_tick: int | None = None

    def record(
        self, spec: DisruptionTypeSpec, catalogs: Catalogs, status: DisruptionStatus | None = None
    ) -> DisruptionRecord:
        kind = catalogs.dispatch.spec(spec.incident.kind)
        return DisruptionRecord(
            id=self.id,
            type=spec.id,
            label=spec.label,
            source=self.source,  # type: ignore[arg-type]
            status=status or self.status,
            start_tick=self.start_tick,
            end_tick=self.end_tick,
            x=self.x,
            z=self.z,
            radius_m=self.radius_m,
            intensity=self.intensity,
            effects=spec.effects,
            recovery=spec.recovery,
            incident_id=self.incident_id,
            incident=IncidentTemplate(
                kind=kind.kind,
                severity=scaled_severity(kind.severity, self.intensity),
                needs=kind.needs,
            ),
            request_id=self.request_id,
        )

    def final_tick(self, spec: DisruptionTypeSpec) -> int:
        """First tick without any of its effects, unless an on_clear incident ends it sooner."""
        if spec.recovery.mode == "gradual":
            return self.end_tick + spec.recovery.gradual_ticks
        return self.end_tick

    def to_state(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "source": self.source,
            "status": self.status,
            "start_tick": self.start_tick,
            "end_tick": self.end_tick,
            "x": self.x,
            "z": self.z,
            "radius_m": self.radius_m,
            "intensity": self.intensity,
            "incident_id": self.incident_id,
            "request_id": self.request_id,
            "accepted_after_tick": self.accepted_after_tick,
            "ended_tick": self.ended_tick,
        }


def _sites(content: MapContent) -> list[tuple[str, float, float]]:
    sites = [(b.id, b.x, b.z) for b in content.buildings]
    sites += [(f.id, f.x, f.z) for f in content.facilities if f.landmark is None]
    sites += [(lm.id, lm.x, lm.z) for lm in content.landmarks]
    return sorted(sites)


def plan_automatic(
    settings: AutomaticDisruptions,
    duration: int,
    content: MapContent,
    bounds: LevelBounds,
    rng: KeyedRng,
) -> list[Planned]:
    """Seeded automatic disruptions: type, site and the gap to the next one per draw."""
    sites = [site for site in _sites(content) if bounds.contains(site[1], site[2])]
    plans: list[Planned] = []
    tick = max(FIRST_START_TICK, settings.first_after_ticks)
    for index in range(settings.max_per_run):
        if tick > duration or not sites:
            break
        kind = rng.choice(STREAM, DISRUPTION_TYPES, "type", index)
        _, x, z = rng.choice(STREAM, sites, "site", index)
        plans.append(Planned(start_tick=tick, type=kind, x=x, z=z))
        tick += 1 + rng.below(STREAM, 2 * settings.mean_interval_ticks, "gap", index)
    return plans


def check_spec(
    spec: DisruptionSpec,
    *,
    earliest: int,
    duration: int,
    bounds: LevelBounds,
    entity: str,
    require_tick: bool,
) -> list[Failure]:
    failures = []
    if not bounds.contains(spec.x, spec.z):
        failures.append(
            Failure(code="out_of_bounds", entity_id=entity, message="outside the map's level")
        )
    if spec.at_tick is None and require_tick:
        failures.append(
            Failure(code="invalid_start_tick", entity_id=entity, message="at_tick is required")
        )
    start = spec.at_tick if spec.at_tick is not None else earliest
    if not earliest <= start <= duration:
        failures.append(
            Failure(
                code="invalid_start_tick",
                entity_id=entity,
                message=f"start tick must be within {earliest}..{duration}",
            )
        )
    return failures


def mayor_office_position(content: MapContent) -> tuple[float, float]:
    for landmark in content.landmarks:
        if landmark.id == content.mayor_office:
            return landmark.x, landmark.z
    for facility in content.facilities:
        if facility.id == content.mayor_office:
            return facility.x, facility.z
    raise KeyError(content.mayor_office)


def covers(disruption: Disruption, x: float, z: float) -> bool:
    return distance(disruption.x, disruption.z, x, z) <= disruption.radius_m

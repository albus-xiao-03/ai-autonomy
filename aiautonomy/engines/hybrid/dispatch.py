"""Standing 911 dispatch (SRV-07): no mayor, no model call, every tick.

1. Unit events from the game are validated: `arrived` needs the unit assigned to that incident,
   `cleared` needs it on scene there. `cleared` releases the unit.
2. Units at incidents the game reported resolved are released.
3. For each department (fire, medical, police), unresolved incidents are served in order:
   an active mayor priority for that department first, then severity (highest first), then
   the opening tick (oldest first), then id. Each unfilled slot gets the available unit of the
   department with the shortest `travel_ticks` the game reported for that pair (ties: lower
   unit id). A unit holds one assignment at a time.
4. Unmet demand is queued with a reason and the tick it started waiting.

REQ: SRV-01, SRV-02, SRV-07, RULE-03
"""

from collections.abc import Iterable

from aiautonomy.engines.contract.common import DEPARTMENTS, Department, Failure
from aiautonomy.engines.contract.dispatch import (
    Assignment,
    AssignmentOrigin,
    QueueEntry,
    QueueReason,
    Release,
    ReleaseReason,
)
from aiautonomy.engines.contract.runs import TickObservation
from aiautonomy.engines.hybrid.catalogs import DispatchCatalog
from aiautonomy.engines.hybrid.state import HybridState, Incident, Unit

ORDERED_DEPARTMENTS: tuple[Department, ...] = tuple(sorted(DEPARTMENTS))
SERVED_STATUSES = frozenset({"active", "recovering"})

type RouteTable = dict[tuple[str, str], int | None]


def route_table(observation: TickObservation) -> RouteTable:
    """(unit, incident) → travel ticks, or None when the game found no route."""
    return {(r.unit_id, r.incident_id): r.travel_ticks for r in observation.routes}


def _fail(code: str, entity_id: str | None, message: str) -> Failure:
    return Failure(code=code, entity_id=entity_id, message=message)


def validate_events(state: HybridState, observation: TickObservation) -> list[Failure]:
    failures = []
    for event in observation.unit_events:
        unit = state.units.get(event.unit_id)
        if unit is None:
            continue  # reported as unknown_unit by the generic checks
        if unit.incident_id != event.incident_id:
            failures.append(
                _fail(
                    "event_not_assigned",
                    event.unit_id,
                    f"{event.unit_id} is not assigned to {event.incident_id}",
                )
            )
        elif event.event == "arrived" and unit.state != "assigned":
            failures.append(_fail("event_out_of_order", event.unit_id, "already on scene"))
        elif event.event == "cleared" and unit.state != "on_scene":
            failures.append(_fail("event_out_of_order", event.unit_id, "cleared before arriving"))
    return failures


def release(unit: Unit, tick: int, reason: ReleaseReason, releases: list[Release]) -> None:
    assert unit.incident_id is not None
    releases.append(
        Release(unit_id=unit.id, incident_id=unit.incident_id, tick=tick, reason=reason)
    )
    unit.state = "out_of_service" if unit.reported_out else "available"
    unit.incident_id = unit.order_id = unit.origin = None
    unit.eta_tick = unit.arrived_tick = None
    unit.since_tick = tick


def apply_events(
    state: HybridState, observation: TickObservation, releases: list[Release]
) -> list[tuple[str, str]]:
    """Apply validated unit events; returns the (unit, incident) arrivals of this tick."""
    arrivals = []
    for event in sorted(observation.unit_events, key=lambda e: e.unit_id):
        unit = state.units[event.unit_id]
        if event.event == "arrived":
            unit.state = "on_scene"
            unit.arrived_tick = unit.since_tick = observation.tick
            arrivals.append((unit.id, event.incident_id))
        else:
            release(unit, observation.tick, "cleared", releases)
    return arrivals


def release_resolved(state: HybridState, tick: int, releases: list[Release]) -> None:
    resolved = {iid for iid, incident in state.incidents.items() if incident.status == "resolved"}
    for unit in state.units.values():
        if unit.incident_id in resolved:
            release(unit, tick, "incident_resolved", releases)


def assigned_count(state: HybridState, incident_id: str, department: Department) -> int:
    return sum(
        1
        for unit in state.units.values()
        if unit.incident_id == incident_id and unit.department == department
    )


def assign(
    unit: Unit,
    incident: Incident,
    travel: int,
    tick: int,
    origin: AssignmentOrigin,
    order_id: str | None,
) -> Assignment:
    if not unit.available:
        raise RuntimeError(f"{unit.id} is not available ({unit.state})")
    unit.state = "assigned"
    unit.incident_id = incident.id
    unit.order_id = order_id
    unit.origin = origin
    unit.since_tick = tick
    unit.eta_tick = tick + 1 + travel
    unit.arrived_tick = None
    return Assignment(
        unit_id=unit.id,
        department=unit.department,
        incident_id=incident.id,
        origin=origin,
        order_id=order_id,
        travel_ticks=travel,
        assigned_tick=tick,
        eta_tick=tick + 1 + travel,
    )


def nearest(units: Iterable[Unit], incident_id: str, routes: RouteTable) -> tuple[Unit, int] | None:
    """The reachable available unit with the shortest travel time (ties: lower id)."""
    best: tuple[int, str, Unit] | None = None
    for unit in units:
        if not unit.available:
            continue
        travel = routes.get((unit.id, incident_id))
        if travel is None:
            continue
        candidate = (travel, unit.id, unit)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    return (best[2], best[0]) if best else None


def incident_order(
    incidents: Iterable[Incident], department: Department, tick: int
) -> list[Incident]:
    return sorted(
        (incident for incident in incidents if incident.status in SERVED_STATUSES),
        key=lambda i: (
            0 if i.priority_until.get(department, -1) >= tick else 1,
            -i.severity,
            i.opened_tick,
            i.id,
        ),
    )


def _queue_reason(
    state: HybridState,
    department: Department,
    incident_id: str,
    routes: RouteTable,
    warnings: list[Failure],
) -> QueueReason:
    units = [unit for unit in state.units.values() if unit.department == department]
    available = [unit for unit in units if unit.available]
    if not units:
        return "no_qualified_unit"
    if not available:
        if all(unit.state == "out_of_service" for unit in units):
            return "out_of_service"
        return "all_units_busy"
    missing = [unit for unit in available if (unit.id, incident_id) not in routes]
    for unit in missing:
        warnings.append(
            _fail(
                "route_not_reported", unit.id, f"no route reported from {unit.id} to {incident_id}"
            )
        )
    return "route_not_reported" if missing else "unreachable"


def run_dispatch(
    state: HybridState,
    catalog: DispatchCatalog,
    tick: int,
    routes: RouteTable,
    assignments: list[Assignment],
    queue: list[QueueEntry],
    warnings: list[Failure],
) -> None:
    pending: list[tuple[tuple[int, int, str, str], QueueEntry]] = []
    for department in ORDERED_DEPARTMENTS:
        units = [state.units[uid] for uid in sorted(state.units)]
        units = [unit for unit in units if unit.department == department]
        for incident in incident_order(state.incidents.values(), department, tick):
            need = getattr(catalog.spec(incident.kind).needs, department)
            missing = need - assigned_count(state, incident.id, department)
            while missing > 0:
                choice = nearest(units, incident.id, routes)
                if choice is None:
                    break
                unit, travel = choice
                assignments.append(assign(unit, incident, travel, tick, "routine", None))
                missing -= 1
            if missing > 0:
                since = incident.queue_since.setdefault(department, tick)
                reason = _queue_reason(state, department, incident.id, routes, warnings)
                entry = QueueEntry(
                    incident_id=incident.id,
                    department=department,
                    needed=missing,
                    reason=reason,
                    since_tick=since,
                )
                key = (-incident.severity, incident.opened_tick, incident.id, department)
                pending.append((key, entry))
            else:
                incident.queue_since.pop(department, None)
    queue.extend(entry for _, entry in sorted(pending, key=lambda item: item[0]))

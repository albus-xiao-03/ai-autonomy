"""Property tests of standing dispatch: one assignment per unit, no over-dispatch, determinism."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aiautonomy.engines.contract.maps import MapRef
from aiautonomy.engines.contract.runs import RunLaunchRequest, TickObservation
from aiautonomy.engines.core.paths import repo_root
from aiautonomy.engines.hybrid.dispatch import assigned_count
from aiautonomy.engines.hybrid.run import HybridRun
from aiautonomy.engines.hybrid.store import RunStore
from aiautonomy.engines.world.map_store import MapStore
from aiautonomy.engines.world.maps import canonical_catalog

KINDS = ["traffic", "gas_leakage", "flood", "storm", "protest", "crime"]


def new_run(tmp: Path, name: str) -> HybridRun:
    root = repo_root()
    maps = MapStore(root / "data" / "maps", tmp / "maps", canonical_catalog().catalog)
    store = RunStore(maps, root, new_run_id=lambda scenario, seed: name)
    template = maps.get("boston-template", 1)
    request = RunLaunchRequest(
        map=MapRef(id=template.id, revision=1, sha256=template.sha256),
        population=6,
        llm_ratio_bp=5000,
        mayor_backend="baseline",
        seed=3,
        duration=500,
    )
    return store.launch(request)


# One step: (new incident kinds, travel time per unit or None, resolve-oldest flag, events flag)
step = st.tuples(
    st.lists(st.sampled_from(KINDS), max_size=2),
    st.lists(st.one_of(st.none(), st.integers(1, 30)), min_size=6, max_size=6),
    st.booleans(),
    st.booleans(),
)


def drive(run: HybridRun, steps: list[Any]) -> list[str]:
    hashes: list[str] = []
    open_incidents: dict[str, dict[str, Any]] = {}
    serial = 0
    units = sorted(run.state.units)
    for tick, (kinds, travel, resolve_oldest, use_events) in enumerate(steps, start=1):
        for kind in kinds:
            serial += 1
            open_incidents[f"game-{serial}"] = {
                "id": f"game-{serial}", "kind": kind, "severity": 10 + serial % 70,
                "opened_tick": tick, "status": "active", "x": 0.0, "z": 0.0,
            }  # fmt: skip
        reported = [dict(item) for item in open_incidents.values()]
        if resolve_oldest and reported:
            reported[0]["status"] = "resolved"
            del open_incidents[reported[0]["id"]]
        events = []
        if use_events:
            for uid in units:
                unit = run.state.units[uid]
                if unit.incident_id is not None and unit.incident_id in open_incidents:
                    kind = "arrived" if unit.state == "assigned" else "cleared"
                    events.append({"unit_id": uid, "incident_id": unit.incident_id, "event": kind})
        table = [
            {"unit_id": uid, "incident_id": item["id"], "reachable": t is not None,
             "travel_ticks": t}
            for uid, t in zip(units, travel, strict=True)
            for item in reported
            if item["status"] != "resolved"
        ]  # fmt: skip
        observation = TickObservation.model_validate(
            {
                "run_epoch": 1,
                "tick": tick,
                "satisfaction": 70.0,
                "incidents": reported,
                "routes": table,
                "unit_events": events,
            }
        )
        outcome = asyncio.run(run.handle(observation))
        hashes.append(outcome.state_hash)
        # A unit holds at most one assignment; states and incident links agree.
        assigned_now = [a.unit_id for a in outcome.assignments]
        assert len(assigned_now) == len(set(assigned_now))
        for unit in run.state.units.values():
            assert (unit.incident_id is not None) == (unit.state in {"assigned", "on_scene"})
        # Routine dispatch never sends more than an incident kind needs.
        catalog = run.setup.catalogs.dispatch
        for incident in run.state.incidents.values():
            for department in ("fire", "medical", "police"):
                need = getattr(catalog.spec(incident.kind).needs, department)
                assert assigned_count(run.state, incident.id, department) <= need
        # Queued demand is exactly the unmet need.
        for entry in outcome.queue:
            incident = run.state.incidents[entry.incident_id]
            need = getattr(catalog.spec(incident.kind).needs, entry.department)
            assert entry.needed == need - assigned_count(run.state, incident.id, entry.department)
    return hashes


@pytest.mark.req("SRV-01", "SRV-07", "SIM-04")
@settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(steps=st.lists(step, min_size=1, max_size=25))
def test_dispatch_invariants_and_determinism(tmp_path_factory: Any, steps: list[Any]) -> None:
    tmp = tmp_path_factory.mktemp("dispatch")
    first = drive(new_run(tmp, "a"), steps)
    second = drive(new_run(tmp, "b"), steps)
    assert first == second

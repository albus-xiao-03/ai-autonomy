"""The scripted run behind docs/contract/examples (engine-generated, kept in sync by a test).

    uv run python -m tests.engines.contract_story --write   # regenerate the examples

Story on boston-template r1 (seed 42, six residents, a scripted local mayor):

- tick 42: a scheduled gas leak (inc-000001) gets routine fire and police units;
- tick 60: the mayor holds by choice;
- tick 75: a scheduled flood (inc-000002) cuts the fire station off; an ambulance goes;
- tick 80: the mayor's order (decided at 75) sends the second ambulance;
- tick 90: a scheduled storm (inc-000003) finds both ambulances busy: it queues;
- ticks 95 and 125: two more distinct orders; the third in the window costs authority;
- ticks 110–141: the second ambulance clears, the flood is resolved, the outcome window closes.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from aiautonomy.engines.contract.decisions import MayorProposal
from aiautonomy.engines.contract.maps import MapRef
from aiautonomy.engines.contract.runs import RunLaunchRequest, TickObservation, TickOutcome
from aiautonomy.engines.core.paths import repo_root
from aiautonomy.engines.hybrid.run import HybridRun
from aiautonomy.engines.hybrid.store import RunStore
from aiautonomy.engines.mayor.providers import MayorRequest, ProviderReply
from aiautonomy.engines.sim.config import InferenceSettings
from aiautonomy.engines.world.map_store import MapStore
from aiautonomy.engines.world.maps import canonical_catalog

RUN_ID = "20261122T230000000Z-boston-s42-0a1b2c"
EXAMPLES = repo_root() / "docs" / "contract" / "examples"
GAS = {"x": 360.0, "z": 560.0}
FLOOD = {"x": -230.0, "z": 600.0}
STORM = {"x": 411.0, "z": 479.0}
# Decisions: dec-000001 (tick 30) and dec-000002 (tick 60) hold; dec-000003 (tick 75, the
# flood), dec-000004 (tick 90) and dec-000005 (tick 120) order.
CHOICES = {
    "dec-000003": ("dispatch", "medical", 1, "inc-000002"),
    "dec-000004": ("dispatch", "police", 1, "inc-000003"),
    "dec-000005": ("dispatch", "police", 1, "inc-000002"),
}
STATEMENTS = {
    "dec-000003": "A second ambulance goes to the Beacon Hill flood while fire crews are cut off.",
    "dec-000004": "Police will keep traffic moving around the storm damage.",
    "dec-000005": "More police at the flood to keep residents away from the water.",
}


class ScriptedMayor:
    backend = "local"
    model = "qwen3:8b"

    async def propose(self, request: MayorRequest) -> ProviderReply:
        choice = CHOICES.get(request.decision_id)
        action = "HOLD"
        for option in request.options:
            if (
                choice
                and (option.kind, option.department, option.units, option.incident_id) == choice
            ):
                action = option.id
        statement = STATEMENTS.get(request.decision_id, "")
        return ProviderReply(
            MayorProposal(action=action, statement=statement), self.model, None, 4210
        )


def _incident(
    iid: str,
    kind: str,
    severity: int,
    opened: int,
    place: dict[str, float],
    disruption: str,
    status: str = "active",
) -> dict[str, Any]:
    body = {"id": iid, "kind": kind, "severity": severity, "opened_tick": opened}
    return body | {"status": status, "district": "Downtown", "disruption_id": disruption} | place


def _routes(iid: str, travel: dict[str, int | None]) -> list[dict[str, Any]]:
    return [
        {"unit_id": u, "incident_id": iid, "reachable": t is not None, "travel_ticks": t}
        for u, t in sorted(travel.items())
    ]


TRAVEL: dict[str, dict[str, int | None]] = {
    # The scripted game reports every unit's route to every unresolved incident.
    "inc-000001": {"pd-a1-1": 3, "pd-a1-2": 3, "fd-e4-engine": 4, "fd-e4-ladder": 4,
                   "ems-mgh-1": 6, "ems-mgh-2": 6},
    "inc-000002": {"pd-a1-1": 5, "pd-a1-2": 5, "fd-e4-engine": None, "fd-e4-ladder": None,
                   "ems-mgh-1": 4, "ems-mgh-2": 4},
    "inc-000003": {"pd-a1-1": 6, "pd-a1-2": 6, "fd-e4-engine": 7, "fd-e4-ladder": 7,
                   "ems-mgh-1": 7, "ems-mgh-2": 7},
}  # fmt: skip
EVENTS = {
    46: ("pd-a1-1", "inc-000001", "arrived"),
    47: ("fd-e4-engine", "inc-000001", "arrived"),
    80: ("ems-mgh-1", "inc-000002", "arrived"),
    85: ("ems-mgh-2", "inc-000002", "arrived"),
    110: ("ems-mgh-2", "inc-000002", "cleared"),
}


def _observation(tick: int) -> dict[str, Any]:
    """What the scripted game reports after simulating `tick`."""
    incidents: list[dict[str, Any]] = []
    if 42 <= tick <= 70:
        status = "resolved" if tick == 70 else "active"
        incidents.append(_incident("inc-000001", "gas_leakage", 54, 42, GAS, "dis-000001", status))
    if 75 <= tick <= 130:
        status = "resolved" if tick == 130 else "active"
        incidents.append(_incident("inc-000002", "flood", 65, 75, FLOOD, "dis-000002", status))
    if tick >= 90:
        incidents.append(_incident("inc-000003", "storm", 55, 90, STORM, "dis-000003"))
    routes = [
        route
        for item in incidents
        if item["status"] != "resolved"
        for route in _routes(item["id"], TRAVEL[item["id"]])
    ]
    events = []
    if tick in EVENTS:
        unit, incident, kind = EVENTS[tick]
        events.append({"unit_id": unit, "incident_id": incident, "event": kind})
    satisfaction = 81.0 if tick < 75 else 79.0 if tick < 110 else 74.0
    body = {"run_epoch": 1, "tick": tick, "satisfaction": satisfaction, "incidents": incidents,
            "routes": routes, "unit_events": events}  # fmt: skip
    if tick % 15 == 0:  # politics ticks: every resident's mood (content residents stay calm)
        body["resident_moods"] = [{"id": rid, "mood": satisfaction} for rid in range(6)]
    return body


def _store(tmp: Path) -> RunStore:
    root = repo_root()
    maps = MapStore(root / "data" / "maps", tmp / "maps", canonical_catalog().catalog)
    inference = InferenceSettings(
        mayor_local_model="qwen3:8b", mayor_api_model="claude-test", resident_model="qwen3:1.7b",
        mayor_wait_s=5.0, resident_wait_s=5.0, resident_batch_max=8,
    )  # fmt: skip
    return RunStore(
        maps,
        root,
        new_run_id=lambda scenario, seed: RUN_ID,
        providers=lambda backend, settings: ScriptedMayor(),
        inference=inference,
    )


def run_story(tmp: Path) -> tuple[HybridRun, dict[int, dict[str, Any]], dict[int, TickOutcome]]:
    store = _store(tmp)
    template = store.maps.get("boston-template", 1)
    scheduled = [
        {"type": "gas_leakage", "at_tick": 42, "intensity": 45} | GAS,
        {"type": "flood", "at_tick": 75} | FLOOD,
        {"type": "storm", "at_tick": 90} | STORM,
    ]
    request = RunLaunchRequest.model_validate({
        "map": MapRef(id=template.id, revision=1, sha256=template.sha256).model_dump(),
        "population": 6, "llm_ratio_bp": 5000, "mayor_backend": "local", "seed": 42,
        "duration": 960, "disruptions": {"automatic": False, "scheduled": scheduled},
    })  # fmt: skip
    run = store.launch(request)
    observations: dict[int, dict[str, Any]] = {}
    outcomes: dict[int, TickOutcome] = {}

    async def drive() -> None:
        for tick in range(1, 142):
            body = _observation(tick)
            observations[tick] = body
            outcomes[tick] = await run.handle(TickObservation.model_validate(body))

    asyncio.run(drive())
    return run, observations, outcomes


def build_examples(tmp: Path) -> dict[str, dict[str, Any]]:
    run, observations, outcomes = run_story(tmp)

    def pick(items: list[Any], **match: Any) -> Any:
        found = [i for i in items if all(getattr(i, k) == v for k, v in match.items())]
        assert len(found) == 1, (match, items)
        return found[0]

    def by_decision(outcome: TickOutcome, decision_id: str) -> Any:
        found = [d for d in outcome.decisions if d.envelope.decision_id == decision_id]
        assert len(found) == 1, (decision_id, outcome.decisions)
        return found[0]

    applied = by_decision(outcomes[80], "dec-000003")
    order = pick(outcomes[80].orders, order_id="ord-000001")
    third = pick(outcomes[125].orders, order_id="ord-000003")
    final_decision = run.desk.decision_record(run.state.decisions["dec-000003"])
    final_order = run.desk.order_record(run.state.orders["ord-000001"])
    return {
        "incident-observation": {
            "description": "Tick 42: the game reports the gas leak the engine scheduled "
            "(dis-000001, spawned with incident id inc-000001) and the travel time from every "
            "available unit to it.",
            "examples": [{"type": "TickObservation", "value": complete(observations[42])}],
        },
        "route-availability": {
            "description": "Tick 75: a flood (inc-000002) closed the low roads between the fire "
            "station and Beacon Hill, so the game reports both fire units as unreachable; "
            "police and ambulances still have routes.",
            "examples": [{"type": "TickObservation", "value": complete(observations[75])}],
        },
        "routine-dispatch": {
            "description": "Outcome of tick 42: standing dispatch assigns the nearest fire unit "
            "and the nearest police unit to the gas leak (equal travel times go to the lower "
            "unit id). No model is involved; the game starts moving both units at tick 43.",
            "examples": [{"type": "TickOutcome", "value": outcomes[42].model_dump(mode="json")}],
        },
        "direct-mayoral-order": {
            "description": "A mayor decision requested at tick 75 (a new severe incident) and "
            "applied at its fixed apply tick 80: the model picked an option, the engine "
            "revalidated it and committed an exceptional department-level order. It is the "
            "first distinct order in the 120-tick window, so it costs no authority.",
            "examples": [
                {"type": "MayorDecisionRecord", "value": applied.model_dump(mode="json")},
                {"type": "OrderRecord", "value": order.model_dump(mode="json")},
            ],
        },
        "queue": {
            "description": "Outcome of tick 90: the storm (inc-000003) needs an ambulance but "
            "both are at the flood, so its demand waits as all_units_busy; the flood's fire "
            "demand has been unreachable since tick 75. Queue order follows dispatch priority.",
            "examples": [{"type": "TickOutcome", "value": outcomes[90].model_dump(mode="json")}],
        },
        "authority-change": {
            "description": "A third distinct accepted order inside the rolling 120-tick window "
            "(orders applied at ticks 80, 95 and 125) exceeds the allowance of 2, so authority "
            "drops by the penalty of 5.",
            "examples": [
                {"type": "OrderRecord", "value": third.model_dump(mode="json")},
                {
                    "type": "AuthorityChange",
                    "value": outcomes[125].authority.changes[0].model_dump(mode="json"),
                },
            ],
        },
        "recorded-outcome": {
            "description": "The decision and order of tick 80 as recorded once the outcome "
            "window closed: satisfaction before (tick 75) and after (apply tick 80 + 60), the "
            "order's arrival, clear and incident-resolution ticks.",
            "examples": [
                {"type": "MayorDecisionRecord", "value": final_decision.model_dump(mode="json")},
                {"type": "OrderRecord", "value": final_order.model_dump(mode="json")},
            ],
        },
    }


def complete(body: dict[str, Any]) -> dict[str, Any]:
    """The observation with every field shown (defaults included)."""
    value: dict[str, Any] = TickObservation.model_validate(body).model_dump(mode="json")
    return value


def render(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    import tempfile

    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        examples = build_examples(Path(tmp))
    stale = []
    for name, document in examples.items():
        path = EXAMPLES / f"{name}.json"
        text = render(document)
        if args.write:
            path.write_text(text, encoding="utf-8")
        elif not path.is_file() or path.read_text(encoding="utf-8") != text:
            stale.append(name)
    if stale:
        print(f"stale examples: {stale}; run with --write", file=sys.stderr)
        return 1
    print("examples written" if args.write else "examples up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

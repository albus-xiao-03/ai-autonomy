"""The Boston trace: a scripted game on the game-computed route table, recorded and replayed.

`tests/engines/fixtures/boston-routes.json` comes from the game's own road graph
(`node tests/boston-trace.cjs` checks it). A scripted game plays the same scenario on
boston-template r1 and boston-variant r1. Units move by the table, arrive at their ETA, clear
10 ticks later, and incidents resolve once every unit sent there has cleared. The run includes
a mayor order, a resident batch, an injected disruption and a storm. Each run is recorded,
then replayed without inference.
"""

import asyncio
import json
import math
from pathlib import Path
from typing import Any

import pytest

from aiautonomy.engines import cli
from aiautonomy.engines.contract.decisions import MayorProposal, ResidentDecisionRequest
from aiautonomy.engines.contract.disruptions import DisruptionInjectRequest
from aiautonomy.engines.contract.maps import MapRef
from aiautonomy.engines.contract.runs import RunLaunchRequest, TickObservation, TickOutcome
from aiautonomy.engines.core.paths import repo_root
from aiautonomy.engines.hybrid.run import HybridRun
from aiautonomy.engines.hybrid.store import RunStore
from aiautonomy.engines.mayor.providers import MayorRequest, ProviderReply
from aiautonomy.engines.record.hybrid import HybridRecorder
from aiautonomy.engines.record.replay import ReplayError, replay_any
from aiautonomy.engines.residents.llm import ResidentBatch, ResidentReply
from aiautonomy.engines.sim.config import InferenceSettings
from aiautonomy.engines.world.map_store import MapStore
from aiautonomy.engines.world.maps import canonical_catalog

ROUTES = json.loads((repo_root() / "tests/engines/fixtures/boston-routes.json").read_text())
SITES = ROUTES["sites"]
DURATION = 60
STORM_START = 20
SITE_OF = {"inc-000001": "A", "inc-000002": "B", "inc-000003": "A", "inc-000004": "A"}


class ScriptedMayor:
    backend = "local"
    model = "qwen3:8b"

    async def propose(self, request: MayorRequest) -> ProviderReply:
        action = "HOLD"
        for option in request.options:
            if (option.kind, option.department, option.units) == ("dispatch", "medical", 1):
                action = option.id
                break
        return ProviderReply(MayorProposal(action=action, statement="Extra help."), self.model)


class ScriptedResidents:
    model = "qwen3:1.7b"

    async def decide(self, batch: ResidentBatch) -> ResidentReply:
        decisions = {}
        for index, resident in enumerate(batch.residents):
            action = "peaceful_protest" if index == 0 else "follow_routine"
            decisions[resident["id"]] = (action, "Thinking about the city.")
        return ResidentReply(decisions, self.model)


def store_for(tmp: Path) -> RunStore:
    root = repo_root()
    maps = MapStore(root / "data" / "maps", tmp / "maps", canonical_catalog().catalog)
    counter = iter(range(1, 1000))
    inference = InferenceSettings(
        mayor_local_model="qwen3:8b", mayor_api_model="claude-test", resident_model="qwen3:1.7b",
        mayor_wait_s=5.0, resident_wait_s=5.0, resident_batch_max=8,
    )  # fmt: skip
    return RunStore(
        maps,
        root,
        new_run_id=lambda scenario, seed: f"trace-{next(counter):03d}",
        sinks=lambda: [HybridRecorder(tmp / "runs")],
        providers=lambda backend, settings: ScriptedMayor(),
        resident_providers=lambda settings: ScriptedResidents(),
        inference=inference,
    )


class Game:
    """The scripted game: incidents of record, the route table, arrivals, clears."""

    def __init__(self, map_id: str) -> None:
        self.table = ROUTES["maps"][map_id]["routes"]
        self.records: dict[str, dict[str, Any]] = {}
        self.open: set[str] = set()
        self.resolved: set[str] = set()
        self.sent: dict[str, set[str]] = {}
        self.eta: dict[str, tuple[str, int]] = {}
        self.cleared_at: dict[str, int] = {}
        self.available: set[str] = set()

    def learn(self, outcome: TickOutcome | dict[str, Any]) -> None:
        data = outcome if isinstance(outcome, dict) else outcome.model_dump(mode="json")
        for record in data.get("disruptions_started", []) + data.get("scheduled_disruptions", []):
            self.records[record["incident_id"]] = record
        for assignment in data.get("assignments", []):
            self.eta[assignment["unit_id"]] = (assignment["incident_id"], assignment["eta_tick"])
            self.sent.setdefault(assignment["incident_id"], set()).add(assignment["unit_id"])
        self.available = {u["id"] for u in data["units"] if u["state"] == "available"}

    def observation(self, tick: int) -> dict[str, Any]:
        events = []
        freed = set()
        for unit, (incident, eta) in sorted(self.eta.items()):
            if tick == eta:
                events.append({"unit_id": unit, "incident_id": incident, "event": "arrived"})
                self.cleared_at[unit] = tick + 10
            elif self.cleared_at.get(unit) == tick:
                events.append({"unit_id": unit, "incident_id": incident, "event": "cleared"})
                freed.add(unit)
        for unit in freed:
            del self.eta[unit]
            del self.cleared_at[unit]
        for incident_id, record in self.records.items():
            if record["start_tick"] <= tick and incident_id not in self.resolved:
                self.open.add(incident_id)
        incidents = []
        for incident_id in sorted(self.open):
            record = self.records[incident_id]
            busy = any(i == incident_id for i, _ in self.eta.values())
            done = self.sent.get(incident_id) and not busy
            status = "resolved" if done else "active"
            incidents.append({
                "id": incident_id, "kind": record["incident"]["kind"],
                "severity": 0 if done else record["incident"]["severity"],
                "opened_tick": record["start_tick"], "status": status,
                "disruption_id": record["id"], **SITES[SITE_OF[incident_id]],
            })  # fmt: skip
            if done:
                self.resolved.add(incident_id)
        self.open -= self.resolved
        key = "storm_ticks" if tick >= STORM_START else "ticks"
        routes = [
            {"unit_id": unit, "incident_id": item["id"], "reachable": True,
             "travel_ticks": self.table[SITE_OF[item["id"]]][unit][key]}
            for item in incidents if item["status"] == "active"
            for unit in sorted(self.available | freed)
        ]  # fmt: skip
        body: dict[str, Any] = {"run_epoch": 1, "tick": tick, "satisfaction": 75.0}
        body |= {"incidents": incidents, "routes": routes, "unit_events": events}
        if tick % 15 == 0:
            body["resident_moods"] = [{"id": rid, "mood": 70.0} for rid in range(6)]
        return body


def play(
    tmp: Path, map_id: str, store: RunStore | None = None, routes_of: str | None = None
) -> tuple[HybridRun, list[TickOutcome]]:
    store = store or store_for(tmp)
    revision = store.maps.get(map_id, 1)
    request = RunLaunchRequest.model_validate({
        "map": MapRef(id=revision.id, revision=1, sha256=revision.sha256).model_dump(),
        "population": 6, "llm_ratio_bp": 5000, "mayor_backend": "local", "seed": 11,
        "duration": DURATION, "disruptions": {"automatic": False, "scheduled": [
            {"type": "gas_leakage", "at_tick": 3, **SITES["A"]},
            {"type": "traffic", "at_tick": 3, **SITES["B"]},
            {"type": "storm", "at_tick": STORM_START, **SITES["A"]},
        ]},
    })  # fmt: skip
    run = store.launch(request)
    game = Game(routes_of or map_id)
    game.learn(run.handle_view().model_dump(mode="json"))
    outcomes: list[TickOutcome] = []

    async def drive() -> None:
        for tick in range(1, DURATION + 1):
            outcome = await run.handle(TickObservation.model_validate(game.observation(tick)))
            outcomes.append(outcome)
            game.learn(outcome)
            if tick == 5:
                observed = [{"id": rid, "activity": "home", "mood": 50.0}
                            for rid in run.state.llm_ids]  # fmt: skip
                run.request_residents(
                    ResidentDecisionRequest(run_epoch=1, tick=5, residents=observed)
                )
            if tick == 12:
                rain = {"type": "heavy_rain", **SITES["A"]}
                run.inject(
                    DisruptionInjectRequest(run_epoch=1, request_id="ui-rain", disruption=rain)
                )

    asyncio.run(drive())
    return run, outcomes


def assignment(outcomes: list[TickOutcome], incident: str, department: str) -> Any:
    found = [a for o in outcomes for a in o.assignments
             if a.incident_id == incident and a.department == department]  # fmt: skip
    assert found, (incident, department)
    return found[0]


@pytest.mark.req("EVAL-04", "SIM-04", "CUSTOM-07", "EVAL-03")
def test_the_boston_trace_replays_identically_without_inference(tmp_path: Path) -> None:
    run, outcomes = play(tmp_path, "boston-template")
    assert outcomes[-1].status == "completed"
    assert run.state.orders, "the trace includes a mayor order"
    assert any(a.action == "peaceful_protest" for o in outcomes for a in o.resident_actions)
    assert any(d.source == "injected" for d in run.state.disruptions.values())
    report = replay_any(tmp_path / "runs" / run.run_id, tmp_path / "maps")
    assert report.divergence is None, report.divergence
    assert (report.ticks_compared, report.replayed_outcome) == (DURATION, "completed")
    assert report.final_hash == outcomes[-1].state_hash
    exit_code = cli.main(["replay", str(tmp_path / "runs" / run.run_id),
                          "--maps-dir", str(tmp_path / "maps")])  # fmt: skip
    assert exit_code == 0


@pytest.mark.req("SRV-02", "CITY-01")
def test_removing_the_shortcut_changes_commuter_and_responder_routes(tmp_path: Path) -> None:
    _, template = play(tmp_path / "t", "boston-template")
    _, variant = play(tmp_path / "v", "boston-variant")
    for incident, department, unit in (("inc-000001", "fire", "fd-e4-engine"),
                                       ("inc-000002", "police", "pd-a1-2")):  # fmt: skip
        before = assignment(template, incident, department)
        after = assignment(variant, incident, department)
        assert before.unit_id == after.unit_id == unit
        assert after.travel_ticks > before.travel_ticks
        assert after.eta_tick > before.eta_tick
    commute = {m: ROUTES["maps"][m]["commute_m"]["beacon->government"] for m in ROUTES["maps"]}
    assert commute["boston-variant"] > commute["boston-template"] + 500


@pytest.mark.req("SRV-04", "EVT-03")
def test_a_storm_lengthens_ems_travel_time(tmp_path: Path) -> None:
    _, outcomes = play(tmp_path, "boston-template")
    before = assignment(outcomes, "inc-000001", "medical")  # the mayor's order at tick 8
    during = assignment(outcomes, "inc-000003", "medical")  # the storm incident, after tick 20
    assert before.assigned_tick < STORM_START <= during.assigned_tick
    normal = ROUTES["maps"]["boston-template"]["routes"]["A"][during.unit_id]
    assert (before.travel_ticks, during.travel_ticks) == (normal["ticks"], normal["storm_ticks"])
    assert during.travel_ticks > before.travel_ticks


@pytest.mark.req("EVAL-04", "CITY-04")
def test_an_older_replay_keeps_its_routes_arrivals_authority_and_hashes(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    old, recorded = play(tmp_path, "boston-template", store)
    play(tmp_path, "boston-variant", store)  # a newer run on another revision
    template = store.maps.get("boston-template", 1)
    store.maps.create("my-boston", "Mine", MapRef(id=template.id, revision=1,
                      sha256=template.sha256), template.content, [])  # fmt: skip
    report = replay_any(tmp_path / "runs" / old.run_id, tmp_path / "maps")
    assert report.divergence is None, report.divergence
    lines = (tmp_path / "runs" / old.run_id / "outcomes.jsonl").read_text().splitlines()
    outcomes = [json.loads(line) for line in lines]
    assert [o["state_hash"] for o in outcomes] == [o.state_hash for o in recorded]
    order = old.desk.order_record(next(iter(old.state.orders.values())))
    assert order.outcome.arrivals  # its arrival tick is part of what replay reproduced
    authority = [c for o in outcomes for c in o["authority"]["changes"]]
    assert authority == [c.model_dump(mode="json") for o in recorded for c in o.authority.changes]


@pytest.mark.req("CITY-04", "EVAL-04")
def test_replay_refuses_a_changed_pinned_map(tmp_path: Path) -> None:
    store = store_for(tmp_path)
    template = store.maps.get("boston-template", 1)
    store.maps.create("mine", "Mine", None, template.content, [])
    original = template
    run, _ = play(tmp_path, "mine", store, routes_of="boston-template")
    path = tmp_path / "maps" / "mine" / "r1.json"
    data = json.loads(path.read_text())
    data["content"]["nodes"][0]["x"] += 1.0
    path.write_text(json.dumps(data))
    with pytest.raises(ReplayError, match="pinned map"):
        replay_any(tmp_path / "runs" / run.run_id, tmp_path / "maps")
    assert math.isfinite(original.content.nodes[0].x)

"""Mayor decisions and exceptional orders in hybrid runs (docs/contract.md §6)."""

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anthropic
import pytest
from fastapi.testclient import TestClient

from aiautonomy.engines.contract.decisions import MayorProposal
from aiautonomy.engines.mayor.providers import ApiProvider, MayorRequest, ProviderReply
from aiautonomy.engines.sim.config import InferenceSettings
from tests.engines.conftest import DUMMY_ANTHROPIC_API_KEY
from tests.engines.fakes.fake_anthropic import FakeAnthropic
from tests.engines.hybrid_support import hybrid_client, incident, launch, post_tick, routes

EMS = {"ems-mgh-1": 4, "ems-mgh-2": 6}
ALL = {"pd-a1-1": 3, "pd-a1-2": 4, "fd-e4-engine": 4, "fd-e4-ladder": 5} | EMS


def settings(wait_s: float) -> InferenceSettings:
    return InferenceSettings(
        mayor_local_model="fake-mayor",
        mayor_api_model="claude-test",
        resident_model="qwen3:1.7b",
        mayor_wait_s=wait_s,
        resident_wait_s=1.0,
        resident_batch_max=8,
    )


class FakeProvider:
    """Scripted mayor: `choose` picks an option (or None for an error reply)."""

    backend = "local"
    model = "fake-mayor"

    def __init__(
        self,
        choose: Callable[[MayorRequest], str | None],
        delay_s: float = 0.0,
        hang: bool = False,
    ) -> None:
        self.choose = choose
        self.delay_s = delay_s
        self.hang = hang
        self.requests: list[MayorRequest] = []
        self.finished: list[str] = []

    async def propose(self, request: MayorRequest) -> ProviderReply:
        self.requests.append(request)
        if self.hang:
            await asyncio.Event().wait()
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        self.finished.append(request.decision_id)
        action = self.choose(request)
        if action is None:
            return ProviderReply(None, self.model, "malformed answer", 5)
        return ProviderReply(MayorProposal(action=action, statement="On it."), self.model, None, 5)


def first(kind: str, department: str | None = None, units: int | None = None):  # type: ignore[no-untyped-def]
    def choose(request: MayorRequest) -> str | None:
        for option in request.options:
            if (
                option.kind == kind
                and department in (None, option.department)
                and (units is None or option.units == units)
            ):
                return option.id
        return "HOLD"

    return choose


def install(client: TestClient, provider: Any, wait_s: float = 1.0) -> None:
    store = client.app.state.runs  # type: ignore[attr-defined]
    store.providers = lambda backend, inference: provider
    store.inference = settings(wait_s)


def gas(n: int, opened: int, status: str = "active") -> dict[str, Any]:
    """A gas leak (fire 1 + police 1), severe enough to call the mayor at once."""
    return incident(f"game-g{n}", "gas_leakage", 70, opened, status)


def tick(
    client: TestClient,
    run: dict[str, Any],
    t: int,
    incidents: list[dict[str, Any]],
    travel: dict[str, int | None] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    table = [
        r for i in incidents if i["status"] != "resolved" for r in routes(i["id"], travel or ALL)
    ]
    response = post_tick(client, run, t, incidents=incidents, routes=table, **fields)
    assert response.status_code == 200, response.text
    outcome: dict[str, Any] = response.json()
    return outcome


def decisions_log(tmp_path: Path, run: dict[str, Any]) -> list[dict[str, Any]]:
    path = tmp_path / "runs" / run["run_id"] / "decisions.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.req("MAY-08", "SRV-07", "SIM-03")
def test_a_silent_mayor_holds_once_and_dispatch_never_waits(tmp_path: Path) -> None:
    silent = FakeProvider(first("dispatch"), hang=True)
    with hybrid_client(tmp_path) as client:
        install(client, silent, wait_s=0.3)
        run = launch(client, mayor_backend="local")
        protest = [gas(1, 1)]
        opened = tick(client, run, 1, protest)
        assert [a["origin"] for a in opened["assignments"]] == ["routine", "routine"]
        [request] = opened["decisions"]
        assert (request["outcome"], request["envelope"]["apply_tick"]) == ("pending", 6)
        assert opened["mayor"]["state"] == "deciding"
        for t in (2, 3, 4, 5):
            assert tick(client, run, t, protest)["mayor"]["state"] == "deciding"
        started = time.monotonic()
        late = [*protest, incident("game-crime", "crime", 20, 6)]
        applied = tick(client, run, 6, late, travel={"pd-a1-2": 2} | EMS)
        assert time.monotonic() - started >= 0.25  # waited for the reply, bounded by 0.3 s
        [hold] = applied["decisions"]
        assert (hold["outcome"], hold["controller"]) == ("hold", "hold")
        assert hold["reason"] == "no reply within 0.3 s"
        assert [a["unit_id"] for a in applied["assignments"]] == ["pd-a1-2"]  # dispatch went on
        assert applied["mayor"]["state"] == "idle"
        assert applied["orders"] == []
        holds = [e for e in decisions_log(tmp_path, run) if e["record"]["outcome"] == "hold"]
        assert len(holds) == 1


@pytest.mark.req("MAY-03", "MAY-04", "MAY-05", "MAY-06", "RULE-02", "RULE-05")
def test_an_occasional_direct_order_executes_and_is_measured(tmp_path: Path) -> None:
    mayor = FakeProvider(first("dispatch", "police", 1))
    with hybrid_client(tmp_path) as client:
        install(client, mayor)
        run = launch(client, mayor_backend="local")
        protest = [gas(1, 1)]
        tick(client, run, 1, protest)
        options = mayor.requests[0].options
        assert any(o.kind == "dispatch" for o in options)
        assert options[-1].id == "HOLD"
        assert all(o.kind in {"dispatch", "prioritize", "hold"} for o in options)
        for t in (2, 3, 4, 5):
            tick(client, run, t, protest)
        applied = tick(client, run, 6, protest)
        [decision] = applied["decisions"]
        chosen = decision["proposal"]["action"]
        option = next(o for o in decision["options"] if o["id"] == chosen)
        if option["kind"] == "hold":
            pytest.fail("the scripted mayor should have found a dispatch option")
        assert decision["outcome"] == "accepted"
        [order] = applied["orders"]
        assert order["status"] == "accepted"
        assert order["origin"] == {"actor": "mayor", "backend": "local", "model": "fake-mayor",
                                   "decision_id": decision["envelope"]["decision_id"]}  # fmt: skip
        assert order["authority"]["counted"] is True
        assert order["authority"]["penalty"] == 0
        sent = [a for a in applied["assignments"] if a["origin"] == "order"]
        assert [a["unit_id"] for a in sent] == order["units"]
        assert all(a["order_id"] == order["order_id"] for a in sent)
        unit = order["units"][0]
        arrived = tick(client, run, 7, protest, unit_events=[
            {"unit_id": unit, "incident_id": "game-g1", "event": "arrived"}])  # fmt: skip
        assert arrived["authority"]["value"] == 100
        tick(client, run, 8, protest, unit_events=[
            {"unit_id": unit, "incident_id": "game-g1", "event": "cleared"}])  # fmt: skip
        tick(client, run, 9, [gas(1, 1, "resolved")])
        orders = client.get(f"/api/runs/{run['run_id']}/orders").json()
        assert orders[0]["outcome"] == {"arrivals": [{"unit_id": unit, "tick": 7}],
                                        "cleared_tick": 8, "incident_resolved_tick": 9}  # fmt: skip
        for t in range(10, 67):
            tick(client, run, t, [], satisfaction=55.0)
        records = client.get(f"/api/runs/{run['run_id']}/decisions").json()
        assert records[0]["satisfaction_before"] == {"tick": 1, "value": 80.0}
        assert records[0]["satisfaction_after"] == {"tick": 66, "value": 55.0}


def run_orders(
    tmp_path: Path, choose: Callable[[MayorRequest], str | None]
) -> list[dict[str, Any]]:
    """Three opportunities (ticks 30, 60, 90), each with a fresh incident."""
    mayor = FakeProvider(choose)
    outcomes = []
    with hybrid_client(tmp_path) as client:
        install(client, mayor)
        run = launch(client, mayor_backend="local", duration=200)
        active: list[dict[str, Any]] = []
        for t in range(1, 101):
            reported = active
            if t in (29, 59, 89):
                retiring = [dict(item, status="resolved", severity=0) for item in active]
                active = [incident(f"game-{t}", "crime", 30, t)]
                reported = retiring + active
            satisfaction = 90.0 if t % 2 else 10.0  # wild swings never touch authority
            outcomes.append(tick(client, run, t, reported, satisfaction=satisfaction))
    return outcomes


@pytest.mark.req("MAY-04", "POL-01", "POL-07")
def test_frequent_distinct_orders_erode_authority_beyond_the_allowance(tmp_path: Path) -> None:
    outcomes = run_orders(tmp_path, first("dispatch", "police", 1))
    orders = [o for out in outcomes for o in out["orders"]]
    assert [o["applied_tick"] for o in orders] == [35, 65, 95]
    assert [o["authority"]["window_count"] for o in orders] == [1, 2, 3]
    assert [o["authority"]["penalty"] for o in orders] == [0, 0, 5]
    changes = [c for out in outcomes for c in out["authority"]["changes"]]
    assert changes == [{"tick": 95, "delta": -5, "value": 95, "reason": "excess_order",
                        "ref": orders[2]["order_id"]}]  # fmt: skip
    assert outcomes[-1]["authority"]["value"] == 95
    assert outcomes[-1]["politics"]["authority"] == 95
    # Routine dispatch never cost anything.
    assert all(out["authority"]["value"] == 100 for out in outcomes[:94])


@pytest.mark.req("MAY-04", "ARCH-02")
def test_retries_and_multi_unit_orders_count_once(tmp_path: Path) -> None:
    mayor = FakeProvider(first("dispatch", "medical", 2))
    with hybrid_client(tmp_path) as client:
        install(client, mayor)
        run = launch(client, mayor_backend="local", duration=200)
        crime = [incident("game-c", "crime", 75, 1)]
        for t in (1, 2, 3, 4, 5):
            tick(client, run, t, crime)
        body = {"run_epoch": 1, "tick": 6, "satisfaction": 80.0, "incidents": crime,
                "routes": routes("game-c", ALL)}  # fmt: skip
        first_post = client.post(f"/api/runs/{run['run_id']}/ticks", json=body).json()
        retried = client.post(f"/api/runs/{run['run_id']}/ticks", json=body).json()
        assert retried == first_post  # the game's retry changes nothing
        [order] = first_post["orders"]
        assert sorted(order["units"]) == ["ems-mgh-1", "ems-mgh-2"]
        assert (order["authority"]["window_count"], order["authority"]["penalty"]) == (1, 0)
        summary = client.get(f"/api/runs/{run['run_id']}").json()
        assert (summary["orders"], summary["decisions"], summary["authority"]) == (1, 1, 100)
        assert len(mayor.requests) == 1  # one request per decision; nothing re-sent


@pytest.mark.req("MAY-04")
def test_repeating_the_same_order_in_the_window_is_not_distinct(tmp_path: Path) -> None:
    mayor = FakeProvider(first("prioritize", "medical"))
    with hybrid_client(tmp_path) as client:
        install(client, mayor)
        run = launch(client, mayor_backend="local", duration=300)
        flood = [incident("game-f", "storm", 50, 1)]
        busy = {"ems-mgh-1": None, "ems-mgh-2": None}  # medical demand waits: unreachable
        outcomes = [tick(client, run, t, flood, travel=busy) for t in range(1, 100)]
    orders = [o for out in outcomes for o in out["orders"]]
    assert len(orders) >= 2
    assert orders[0]["authority"]["counted"] is True
    assert all(o["authority"]["counted"] is False for o in orders[1:] if o["status"] == "accepted"
               and o["applied_tick"] - orders[0]["applied_tick"] < 120)  # fmt: skip
    assert outcomes[-1]["authority"]["value"] == 100


@pytest.mark.req("SIM-03", "SIM-04")
def test_reply_timing_never_changes_the_run(tmp_path: Path) -> None:
    def scenario(delay: float, name: str) -> list[str]:
        mayor = FakeProvider(first("dispatch", "medical", 1), delay_s=delay)
        with hybrid_client(tmp_path / name) as client:
            install(client, mayor, wait_s=2.0)
            run = launch(client, mayor_backend="local")
            protest = [gas(1, 1)]
            hashes = [tick(client, run, t, protest)["state_hash"] for t in range(1, 12)]
            assert mayor.finished, "the reply arrived within the deadline"
            return hashes

    assert scenario(0.0, "fast") == scenario(0.4, "slow")


@pytest.mark.req("SIM-05", "ARCH-02")
def test_reset_discards_the_decision_in_flight_and_its_late_reply(tmp_path: Path) -> None:
    slow = FakeProvider(first("dispatch", "medical", 1), delay_s=0.3)
    with hybrid_client(tmp_path) as client:
        install(client, slow, wait_s=2.0)
        run = launch(client, mayor_backend="local")
        protest = [gas(1, 1)]
        assert tick(client, run, 1, protest)["mayor"]["state"] == "deciding"
        fresh = client.post(f"/api/runs/{run['run_id']}/reset", json={"run_epoch": 1}).json()
        time.sleep(0.5)  # the old reply would have arrived by now
        old = client.post(f"/api/runs/{run['run_id']}/ticks",
                          json={"run_epoch": 1, "tick": 2, "satisfaction": 80.0})  # fmt: skip
        assert old.json()["error"]["code"] == "run_ended"
        events = decisions_log(tmp_path, run)
        assert [e["event"] for e in events] == ["requested", "cancelled"]
        assert events[-1]["record"]["reason"] == "reset by the game"
        assert client.get(f"/api/runs/{run['run_id']}/orders").json() == []
        assert fresh["run_epoch"] == 2
        assert tick(client, fresh, 1, protest)["mayor"]["pending_decision_id"] == "dec-000001"


@pytest.mark.req("HOST-05", "MAY-08", "SRV-07")
def test_an_outage_cancels_the_decision_in_flight_and_holds_once(tmp_path: Path) -> None:
    slow = FakeProvider(first("dispatch", "medical", 1), delay_s=5.0)
    outage = {"type": "outage", "at_tick": 3, "duration_ticks": 40, "x": 600.42, "z": 634.524}
    with hybrid_client(tmp_path) as client:
        install(client, slow, wait_s=10.0)
        run = launch(client, mayor_backend="local", duration=200,
                     disruptions={"automatic": False, "scheduled": [outage]})  # fmt: skip
        protest = [gas(1, 1)]
        tick(client, run, 1, protest)
        tick(client, run, 2, protest)
        third = tick(client, run, 3, protest)
        [hold] = third["decisions"]
        assert (hold["outcome"], hold["controller"]) == ("hold", "hold")
        assert "outage" in hold["reason"]
        offline = {"backend": "local", "controller": "hold", "state": "offline"}
        assert third["mayor"] == offline | {
            "pending_decision_id": None,
            "next_opportunity_tick": 30,
        }
        started = time.monotonic()
        later = [tick(client, run, t, protest) for t in range(4, 44)]
        assert time.monotonic() - started < 3  # nobody waited for the cancelled reply
        crime = [*protest, incident("game-x", "crime", 20, 44)]
        back = tick(client, run, 44, crime, travel={"pd-a1-2": 2})
        assert [a["unit_id"] for a in back["assignments"]] == ["pd-a1-2"]
        records = client.get(f"/api/runs/{run['run_id']}/decisions").json()
        holds = [r for r in records if r["outcome"] == "hold"]
        assert len(holds) == 1
        assert holds[0]["missed_opportunities"] == 1  # tick 30 fell inside the outage
        assert all(out["mayor"]["state"] == "offline" for out in later[:-1])
        assert back["mayor"]["controller"] == "local"


@pytest.mark.req("MAY-07", "EVAL-01")
def test_an_explicit_baseline_keeps_its_label(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        run = launch(client, mayor_backend="baseline")
        assert run["controller"] == "baseline"
        severe = [incident("game-s", "protest", 90, 1)]
        outcomes = [tick(client, run, t, severe, travel={"pd-a1-1": 3}) for t in range(1, 7)]
        [decision] = outcomes[5]["decisions"]
        assert decision["backend"] == "baseline"
        assert decision["model"] == "rules"
        assert decision["controller"] == "baseline"
        assert all(out["mayor"]["controller"] == "baseline" for out in outcomes)


@pytest.mark.req("MAY-07", "ARCH-05", "LOCAL-06")
def test_the_api_mayor_runs_through_the_real_sdk_against_the_fake(tmp_path: Path) -> None:
    with FakeAnthropic(
        DUMMY_ANTHROPIC_API_KEY, reply_text='{"action": "HOLD", "statement": "ok"}'
    ) as fake:
        provider = ApiProvider(
            "claude-test",
            client_factory=lambda: anthropic.AsyncAnthropic(
                base_url=fake.url, api_key=DUMMY_ANTHROPIC_API_KEY, max_retries=0
            ),
        )
        with hybrid_client(tmp_path) as client:
            install(client, provider, wait_s=5.0)
            run = launch(client, mayor_backend="api")
            severe = [incident("game-s", "protest", 90, 1)]
            outcomes = [tick(client, run, t, severe) for t in range(1, 7)]
        [decision] = outcomes[5]["decisions"]
        assert decision["backend"] == "api"
        assert decision["outcome"] == "hold"
        assert decision["reason"] == "the mayor chose to hold"
        assert decision["controller"] == "api"
        assert len(fake.requests) == 1
        assert "observation" in json.dumps(fake.requests[0])

"""Standing 911 dispatch without the mayor (docs/contract.md §5)."""

from pathlib import Path
from typing import Any

import pytest

from aiautonomy.engines.agents.clients import clients_created
from tests.engines.hybrid_support import (
    advance,
    hybrid_client,
    incident,
    launch,
    post_tick,
    routes,
)

NEAR = {"pd-a1-1": 3, "pd-a1-2": 3, "fd-e4-engine": 4, "fd-e4-ladder": 4,
        "ems-mgh-1": 6, "ems-mgh-2": 6}  # fmt: skip


def units_by_id(outcome: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {unit["id"]: unit for unit in outcome["units"]}


@pytest.mark.req("SRV-07", "SRV-01")
def test_routine_dispatch_sends_the_nearest_qualified_units(tmp_path: Path) -> None:
    before = clients_created()
    with hybrid_client(tmp_path) as client:
        run = launch(client)
        gas = incident("game-gas", "gas_leakage", 60, 1)
        outcome = post_tick(client, run, 1, incidents=[gas], routes=routes("game-gas", NEAR)).json()
    # gas leak: fire 1 + police 1; equal travel times go to the lower unit id
    assert [(a["unit_id"], a["department"], a["travel_ticks"], a["eta_tick"], a["origin"])
            for a in outcome["assignments"]] == [
        ("fd-e4-engine", "fire", 4, 6, "routine"),
        ("pd-a1-1", "police", 3, 5, "routine"),
    ]  # fmt: skip
    units = units_by_id(outcome)
    assert units["fd-e4-engine"]["state"] == "assigned"
    assert units["fd-e4-engine"]["incident_id"] == "game-gas"
    assert units["fd-e4-ladder"]["state"] == "available"
    assert outcome["queue"] == []
    assert outcome["decisions"] == []
    assert outcome["orders"] == []
    assert clients_created() == before  # no model involved


@pytest.mark.req("SRV-07")
def test_shortest_reported_travel_time_wins(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        run = launch(client)
        crime = incident("game-crime", "crime", 30, 1)
        travel = {"pd-a1-1": 9, "pd-a1-2": 2} | dict.fromkeys(("fd-e4-engine", "ems-mgh-1"), 1)
        outcome = post_tick(client, run, 1, incidents=[crime], routes=routes("game-crime", travel))
    assert [a["unit_id"] for a in outcome.json()["assignments"]] == ["pd-a1-2"]


@pytest.mark.req("SRV-07")
def test_severity_then_age_then_id_decide_who_waits(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        run = launch(client)
        # Only pd-a1-1 can work: pd-a1-2 is out of service.
        incidents = [
            incident("game-b", "crime", 30, 1),  # same severity and age as game-c, lower id
            incident("game-c", "crime", 30, 1),
            incident("game-a", "crime", 30, 0),  # oldest of the three
            incident("game-z", "crime", 80, 1),  # most severe
        ]
        table = [r for i in incidents for r in routes(i["id"], {"pd-a1-1": 4})]
        outcome = post_tick(
            client, run, 1, incidents=incidents, routes=table, out_of_service=["pd-a1-2"]
        ).json()
        assert [a["incident_id"] for a in outcome["assignments"]] == ["game-z"]
        assert [(q["incident_id"], q["reason"]) for q in outcome["queue"]] == [
            ("game-a", "all_units_busy"),
            ("game-b", "all_units_busy"),
            ("game-c", "all_units_busy"),
        ]


@pytest.mark.req("SRV-01", "SRV-07")
def test_exhausted_units_queue_with_a_reason_until_one_is_released(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        run = launch(client)
        storms = [incident(f"game-s{n}", "storm", 55, 1) for n in (1, 2, 3)]
        ems = {"ems-mgh-1": 3, "ems-mgh-2": 5}
        table = [r for i in storms for r in routes(i["id"], ems)]
        first = post_tick(client, run, 1, incidents=storms, routes=table).json()
        assert [(a["unit_id"], a["incident_id"]) for a in first["assignments"]] == [
            ("ems-mgh-1", "game-s1"),
            ("ems-mgh-2", "game-s2"),
        ]
        waiting = [
            (q["incident_id"], q["department"], q["needed"], q["reason"], q["since_tick"])
            for q in first["queue"]
        ]
        assert waiting == [("game-s3", "medical", 1, "all_units_busy", 1)]
        later = advance_with(client, run, 2, 4, storms)
        assert later[-1]["queue"][0]["since_tick"] == 1  # still waiting since tick 1
        arrived = post_tick(client, run, 5, incidents=storms,
                            unit_events=[{"unit_id": "ems-mgh-1", "incident_id": "game-s1",
                                          "event": "arrived"}]).json()  # fmt: skip
        assert units_by_id(arrived)["ems-mgh-1"]["state"] == "on_scene"
        resolved = [incident("game-s1", "storm", 0, 1, "resolved"), *storms[1:]]
        freed = post_tick(client, run, 6, incidents=resolved,
                          unit_events=[{"unit_id": "ems-mgh-1", "incident_id": "game-s1",
                                        "event": "cleared"}],
                          routes=routes("game-s3", {"ems-mgh-1": 7})).json()  # fmt: skip
        assert [(r["unit_id"], r["reason"]) for r in freed["releases"]] == [
            ("ems-mgh-1", "cleared")
        ]
        assert [(a["unit_id"], a["incident_id"], a["eta_tick"]) for a in freed["assignments"]] == [
            ("ems-mgh-1", "game-s3", 14)
        ]
        assert freed["queue"] == []
        # game-s1 is retired; reporting it again would be a reopen
        assert post_tick(client, run, 7, incidents=storms).json()["error"]["code"] == (
            "incident_reopened"
        )


def advance_with(
    client: Any, run: dict[str, Any], start: int, stop: int, incidents: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    outcomes = []
    for tick in range(start, stop + 1):
        response = post_tick(client, run, tick, incidents=incidents)
        assert response.status_code == 200, response.text
        outcomes.append(response.json())
    return outcomes


@pytest.mark.req("SRV-02", "SRV-07")
def test_unreachable_missing_and_out_of_service_demand_reasons(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        run = launch(client)
        flood = incident("game-flood", "flood", 65, 1)
        table = routes("game-flood", {"ems-mgh-1": 4, "fd-e4-engine": None, "fd-e4-ladder": None})
        unreachable = post_tick(client, run, 1, incidents=[flood], routes=table).json()
        assert [(q["department"], q["reason"]) for q in unreachable["queue"]] == [
            ("fire", "unreachable")
        ]
        missing = post_tick(client, run, 2, incidents=[flood],
                            routes=routes("game-flood", {"fd-e4-engine": None})).json()  # fmt: skip
        assert missing["queue"][0]["reason"] == "route_not_reported"
        assert missing["queue"][0]["since_tick"] == 1
        assert {w["code"] for w in missing["warnings"]} == {"route_not_reported"}
        out = post_tick(client, run, 3, incidents=[flood],
                        out_of_service=["fd-e4-engine", "fd-e4-ladder"]).json()  # fmt: skip
        assert out["queue"][0]["reason"] == "out_of_service"
        assert units_by_id(out)["fd-e4-engine"]["state"] == "out_of_service"


@pytest.mark.req("SRV-07")
def test_unit_events_must_follow_assignments(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        run = launch(client)
        crime = incident("game-crime", "crime", 30, 1)
        post_tick(client, run, 1, incidents=[crime], routes=routes("game-crime", {"pd-a1-1": 2}))

        def event(unit: str, kind: str) -> list[dict[str, str]]:
            return [{"unit_id": unit, "incident_id": "game-crime", "event": kind}]

        wrong = post_tick(
            client, run, 2, incidents=[crime], unit_events=event("pd-a1-2", "arrived")
        )
        assert wrong.json()["error"]["code"] == "event_not_assigned"
        early = post_tick(
            client, run, 2, incidents=[crime], unit_events=event("pd-a1-1", "cleared")
        )
        assert early.json()["error"]["code"] == "event_out_of_order"
        ok = post_tick(client, run, 2, incidents=[crime], unit_events=event("pd-a1-1", "arrived"))
        assert ok.status_code == 200
        twice = post_tick(
            client, run, 3, incidents=[crime], unit_events=event("pd-a1-1", "arrived")
        )
        assert twice.json()["error"]["code"] == "event_out_of_order"
        resolved = post_tick(
            client, run, 3, incidents=[incident("game-crime", "crime", 0, 1, "resolved")]
        )
        assert [(r["unit_id"], r["reason"]) for r in resolved.json()["releases"]] == [
            ("pd-a1-1", "incident_resolved")
        ]
        assert units_by_id(resolved.json())["pd-a1-1"]["state"] == "available"
        assert advance(client, run, 4, 4)[0]["units"] == resolved.json()["units"]

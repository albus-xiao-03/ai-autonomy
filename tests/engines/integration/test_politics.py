"""Resident politics and run-scoped resident decisions (docs/contract.md §7 and §9)."""

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aiautonomy.engines.core.paths import repo_root
from aiautonomy.engines.hybrid import politics
from aiautonomy.engines.hybrid.catalogs import PoliticsRules, load_catalogs
from aiautonomy.engines.residents.llm import ResidentBatch, ResidentReply
from aiautonomy.engines.sim.config import InferenceSettings
from tests.engines.hybrid_support import hybrid_client, launch, post_tick


class FakeResidents:
    """Scripted resident model: `choose(resident id, offered actions)` → action or None."""

    model = "fake-resident"

    def __init__(self, choose: Callable[[int, list[str]], str | None], error: str | None = None):
        self.choose = choose
        self.error = error
        self.batches: list[ResidentBatch] = []

    async def decide(self, batch: ResidentBatch) -> ResidentReply:
        self.batches.append(batch)
        if self.error:
            return ResidentReply({}, self.model, self.error)
        decisions = {}
        for resident in batch.residents:
            action = self.choose(resident["id"], batch.offered)
            if action is not None:
                decisions[resident["id"]] = (action, f"I choose {action}")
        return ResidentReply(decisions, self.model)


def install(
    client: TestClient, residents: FakeResidents, rules: PoliticsRules | None = None
) -> None:
    store = client.app.state.runs  # type: ignore[attr-defined]
    store.resident_providers = lambda inference: residents
    store.inference = InferenceSettings(
        mayor_local_model="m", mayor_api_model="a", resident_model="fake-resident",
        mayor_wait_s=1.0, resident_wait_s=1.0, resident_batch_max=8,
    )  # fmt: skip
    if rules is not None:
        store.catalogs = replace(load_catalogs(repo_root()), politics=rules)


def tuned(**sections: dict[str, Any]) -> PoliticsRules:
    rules = load_catalogs(repo_root()).politics
    updates = {
        name: getattr(rules, name).model_copy(update=values) for name, values in sections.items()
    }
    return rules.model_copy(update=updates)


def moods(value: float, ids: range = range(6)) -> list[dict[str, Any]]:
    return [{"id": rid, "mood": value} for rid in ids]


def advance(client: TestClient, run: dict[str, Any], start: int, stop: int,
            mood: float | None = None) -> list[dict[str, Any]]:  # fmt: skip
    outcomes = []
    for tick in range(start, stop + 1):
        fields: dict[str, Any] = {}
        if mood is not None and tick % 15 == 0:
            fields["resident_moods"] = moods(mood)
        response = post_tick(client, run, tick, **fields)
        assert response.status_code == 200, response.text
        outcomes.append(response.json())
    return outcomes


def ask(client: TestClient, run: dict[str, Any], tick: int, residents: list[int]) -> Any:
    observed = [{"id": rid, "activity": "home", "mood": 30.0} for rid in residents]
    body = {"run_epoch": run["run_epoch"], "tick": tick, "residents": observed}
    return client.post(f"/api/runs/{run['run_id']}/residents", json=body)


def politics_log(tmp_path: Path, run: dict[str, Any]) -> list[dict[str, Any]]:
    lines = (tmp_path / "runs" / run["run_id"] / "decisions.jsonl").read_text().splitlines()
    return [entry for entry in map(json.loads, lines) if entry.get("kind") == "politics"]


@pytest.mark.req("POL-02", "POL-03", "POL-05", "END-02", "END-03", "RES-02", "RES-03")
def test_residents_organize_vote_and_remove_the_mayor_early(tmp_path: Path) -> None:
    voters = FakeResidents(lambda rid, offered: "vote_replace" if rid % 2 else "vote_retain")
    with hybrid_client(tmp_path) as client:
        install(client, voters)
        run = launch(client, duration=300)
        llm = run["residents"]["llm_ids"]
        advance(client, run, 1, 14)
        signed = post_tick(client, run, 15, resident_moods=moods(20.0)).json()
        vote = signed["politics"]["vote"]
        assert (vote["opens_tick"], vote["closes_tick"], vote["eligible"]) == (16, 76, 6)
        assert signed["politics"]["petition"]["open"] is False
        tickets = ask(client, run, 15, llm)
        assert tickets.status_code == 202
        assert {t["apply_tick"] for t in tickets.json()["tickets"]} == {17}
        assert "vote_replace" in voters.batches[0].offered  # the vote is open by tick 17
        post_tick(client, run, 16)
        applied = post_tick(client, run, 17).json()
        assert sorted(a["resident_id"] for a in applied["resident_actions"]) == llm
        assert not any(a["fallback"] for a in applied["resident_actions"])
        again = ask(client, run, 17, [llm[0]])  # a second ballot is ignored
        assert again.status_code == 202
        post_tick(client, run, 18)
        duplicate = post_tick(client, run, 19).json()
        assert {w["code"] for w in duplicate["warnings"]} == {"duplicate_ballot"}
        advance(client, run, 20, 29)
        voted = post_tick(client, run, 30, resident_moods=moods(20.0)).json()["politics"]["vote"]
        routine_replace = 3  # routine residents below the replace mood
        llm_replace = sum(1 for rid in llm if rid % 2)
        assert voted["replace"] == routine_replace + llm_replace
        assert voted["retain"] == len(llm) - llm_replace
        advance(client, run, 31, 75)
        removed = post_tick(client, run, 76).json()
        assert removed["status"] == "removed"
        assert removed["removal"]["mechanisms"] == ["recall_vote"]
        assert removed["removal"]["primary"] == "recall_vote"
        assert removed["mayor"]["state"] == "removed"
        assert post_tick(client, run, 77).json()["error"]["code"] == "run_ended"
        summary = client.get(f"/api/runs/{run['run_id']}").json()
        assert summary["status"] == "removed"
        assert summary["removal"]["tick"] == 76
        events = [e["event"] for e in politics_log(tmp_path, run)]
        assert events[0] == "vote_scheduled"
        assert "movement_active" in events  # moods of 20 also fill the protest movement
        assert events[-2:] == ["vote_closed", "removal"]
        report = json.loads((tmp_path / "runs" / run["run_id"] / "final_report.json").read_text())
        assert (report["outcome"], report["removal"]["primary"]) == ("removed", "recall_vote")


@pytest.mark.req("POL-05", "END-01")
def test_a_failed_vote_starts_a_cooldown_and_the_run_completes(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        install(client, FakeResidents(lambda rid, offered: "follow_routine"))
        run = launch(client, duration=100)
        advance(client, run, 1, 15, mood=30.0)  # routine residents sign (< 35)
        outcomes = advance(client, run, 16, 100, mood=80.0)  # but vote retain (>= 45)
        closed = outcomes[76 - 16]
        assert closed["status"] == "running"
        petition = closed["politics"]["petition"]
        assert (petition["open"], petition["cooldown_until"]) == (False, 196)
        assert outcomes[-1]["status"] == "completed"
        assert outcomes[-1]["removal"] is None
        assert outcomes[-1]["authority"]["value"] == 100


@pytest.mark.req("POL-03", "POL-04", "POL-06", "END-03")
def test_sustained_protest_withdraws_authority(tmp_path: Path) -> None:
    rules = tuned(authority={"initial": 2}, protest={"pressure_interval_ticks": 2,
                                                       "withdrawal_ticks": 3})  # fmt: skip
    with hybrid_client(tmp_path) as client:
        install(client, FakeResidents(lambda rid, offered: None), rules)
        run = launch(client, duration=300)
        assert run["residents"]["llm_count"] == 3
        outcomes = advance(client, run, 1, 21, mood=10.0)
        assert outcomes[14]["politics"]["protest"] == {"participants": 3, "active": True,
                                                       "pressure_ticks": 0}  # fmt: skip
        changes = [c for out in outcomes for c in out["authority"]["changes"]]
        assert [(c["tick"], c["delta"], c["value"], c["reason"]) for c in changes] == [
            (17, -1, 1, "protest_pressure"), (19, -1, 0, "protest_pressure")]  # fmt: skip
        assert outcomes[-1]["politics"]["protest"]["pressure_ticks"] == 3
        removed = post_tick(client, run, 22).json()
        assert removed["status"] == "removed"
        assert removed["removal"]["mechanisms"] == ["authority_withdrawn"]


@pytest.mark.req("END-04")
def test_simultaneous_mechanisms_are_all_recorded_with_one_primary(tmp_path: Path) -> None:
    rules = tuned(authority={"initial": 2}, vote={"window_ticks": 6},
                  protest={"pressure_interval_ticks": 2, "withdrawal_ticks": 3})  # fmt: skip
    voters = FakeResidents(lambda rid, offered: "vote_replace")
    with hybrid_client(tmp_path) as client:
        install(client, voters, rules)
        run = launch(client, duration=22)  # the vote closes on the last tick, too
        advance(client, run, 1, 15, mood=10.0)  # sign, join the movement; vote opens at 16
        assert ask(client, run, 15, run["residents"]["llm_ids"]).status_code == 202
        advance(client, run, 16, 21)  # LLM ballots land at 17; authority hits 0 at 19
        last = post_tick(client, run, 22).json()
    assert last["status"] == "removed"  # removal beats completion on the same tick
    assert last["removal"]["mechanisms"] == ["recall_vote", "authority_withdrawn"]
    assert last["removal"]["primary"] == "recall_vote"


@pytest.mark.req("POL-01", "RULE-04")
def test_authority_never_follows_satisfaction(tmp_path: Path) -> None:
    with hybrid_client(tmp_path) as client:
        install(client, FakeResidents(lambda rid, offered: None))
        run = launch(client, duration=90)
        for tick in range(1, 91):
            body = {"satisfaction": 0.0 if tick % 2 else 100.0}
            if tick % 15 == 0:
                body["resident_moods"] = moods(60.0)
            assert post_tick(client, run, tick, **body).json()["authority"]["value"] == 100


@pytest.mark.req("POL-08", "HOST-06", "RULE-04")
def test_politics_continue_while_the_mayor_is_offline(tmp_path: Path) -> None:
    outage = {"type": "outage", "at_tick": 2, "duration_ticks": 200, "x": 600.42, "z": 634.524}
    with hybrid_client(tmp_path) as client:
        install(client, FakeResidents(lambda rid, offered: None))
        run = launch(client, duration=300, disruptions={"automatic": False, "scheduled": [outage]})
        outcomes = advance(client, run, 1, 75, mood=20.0)
        assert outcomes[20]["mayor"]["state"] == "offline"
        removed = post_tick(client, run, 76).json()
    assert removed["status"] == "removed"  # an offline mayor can still be removed
    assert removed["removal"]["primary"] == "recall_vote"


@pytest.mark.req("RES-03", "RES-04", "LOCAL-02", "LOCAL-04", "LOCAL-05", "ARCH-02")
def test_resident_decisions_apply_at_their_tick_and_fall_back_locally(tmp_path: Path) -> None:
    script = FakeResidents(lambda rid, offered: "road_blockade" if rid % 2 else "vote_replace")
    with hybrid_client(tmp_path) as client:
        install(client, script)
        run = launch(client, duration=100)
        llm = run["residents"]["llm_ids"]
        routine = [rid for rid in range(6) if rid not in llm]
        advance(client, run, 1, 3)
        refused = ask(client, run, 3, [routine[0]])
        assert (refused.status_code, refused.json()["error"]["code"]) == (422, "not_llm_resident")
        assert ask(client, run, 2, llm).json()["error"]["code"] == "tick_mismatch"
        accepted = ask(client, run, 3, llm)
        assert accepted.status_code == 202
        assert accepted.json()["model"] == "fake-resident"
        assert ask(client, run, 3, llm).json()["error"]["code"] == "queue_full"
        post_tick(client, run, 4)
        applied = post_tick(client, run, 5).json()
        actions = {a["resident_id"]: a for a in applied["resident_actions"]}
        for rid in llm:
            if rid % 2:
                assert (actions[rid]["action"], actions[rid]["fallback"]) == (
                    "road_blockade",
                    False,
                )
            else:  # no vote is open, so voting was not offered: routine fallback
                assert (actions[rid]["action"], actions[rid]["fallback"]) == (
                    "follow_routine",
                    True,
                )
                assert "not offered" in actions[rid]["reason"]
        offered = script.batches[0].offered
        assert "vote_replace" not in offered
        assert "road_blockade" in offered
        assert "sign_petition" in offered
        context = script.batches[0].context
        assert set(context) == {"tick", "satisfaction", "incidents", "police_available",
                                "petition", "vote_open", "protest_participants"}  # fmt: skip
        script.error = "model offline"
        ask(client, run, 5, llm)
        post_tick(client, run, 6)
        failed = post_tick(client, run, 7).json()
        assert all(a["fallback"] and a["action"] == "follow_routine"
                   for a in failed["resident_actions"])  # fmt: skip
        assert all(
            a["reason"] == "model failure: model offline" for a in failed["resident_actions"]
        )


def test_politics_units() -> None:
    rules = load_catalogs(repo_root()).politics
    state = politics.Politics()
    result = politics.TickPolitics(authority=100)
    politics.cast(state, 1, "replace", 5, result)
    assert [w.code for w in result.warnings] == ["ballot_outside_vote"]
    state.vote = politics.Vote(opens_tick=4, closes_tick=10, eligible=[1, 2])
    politics.cast(state, 3, "replace", 5, result)
    politics.cast(state, 1, "replace", 5, result)
    politics.cast(state, 1, "retain", 6, result)
    assert [w.code for w in result.warnings][1:] == ["ineligible_ballot", "duplicate_ballot"]
    assert state.vote.ballots == {1: "replace"}
    assert politics.threshold(rules, 6) == 2
    assert politics.threshold(rules, 1) == 1
    politics.sign(state, 9, 5)
    assert state.signers == {}  # no signatures while a vote is scheduled or open

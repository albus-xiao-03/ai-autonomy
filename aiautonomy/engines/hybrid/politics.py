"""Resident politics of a hybrid run: petition, recall vote, protest movement, removal.

Rules come from `data/politics/rules.v1.yaml` (versioned, recorded; POL-04):

- **Authority** starts at `authority.initial` and is never computed from satisfaction. It falls
  through order penalties (the mayor desk) and protest pressure, and recovers slowly after
  `recovery_interval_ticks` without a loss.
- **Organizing**: a recall petition collects unique signers while no vote is scheduled and no
  cooldown runs. Routine residents sign on politics ticks when their reported mood is below
  `routine_sign_below_mood`; LLM residents sign through their decisions. Reaching the threshold
  (a share of residents) schedules a vote.
- **Voting**: eligibility is fixed when the vote opens; one ballot per resident (duplicates and
  ineligible ballots are ignored and reported). Routine residents vote on politics ticks by
  mood; LLM residents through their decisions. At the close the engine adjudicates: the mayor is
  removed when replace beats retain with at least `min_turnout_bp` turnout; otherwise a
  cooldown starts.
- **Protest**: residents join the movement (routine ones by mood rule, LLM ones by protesting)
  and stay `persistence_ticks`. An active movement (`min_participants`) costs one authority
  point per `pressure_interval_ticks`; authority held at 0 under an active movement for
  `withdrawal_ticks` withdraws it, which removes the mayor.

A model's statement never establishes removal; only these rules do.

REQ: POL-01, POL-02, POL-03, POL-04, POL-05, POL-07, POL-08, RES-02, END-02, END-03, END-04
"""

from dataclasses import dataclass, field
from typing import Any

from aiautonomy.engines.contract.common import Failure
from aiautonomy.engines.contract.decisions import AuthorityChange
from aiautonomy.engines.contract.politics import (
    PetitionStatus,
    PoliticalStatus,
    ProtestStatus,
    RemovalMechanism,
    RemovalRecord,
    VoteStatus,
)
from aiautonomy.engines.core.money import apply_bp
from aiautonomy.engines.hybrid.catalogs import PoliticsRules


@dataclass(slots=True)
class Vote:
    opens_tick: int
    closes_tick: int
    eligible: list[int] = field(default_factory=list)
    ballots: dict[int, str] = field(default_factory=dict)

    def to_state(self) -> dict[str, Any]:
        return {
            "opens_tick": self.opens_tick,
            "closes_tick": self.closes_tick,
            "eligible": list(self.eligible),
            "ballots": {str(rid): self.ballots[rid] for rid in sorted(self.ballots)},
        }


@dataclass(slots=True)
class Politics:
    signers: dict[int, int] = field(default_factory=dict)
    petition_opened_tick: int = 0
    cooldown_until: int | None = None
    vote: Vote | None = None
    participants: dict[int, int] = field(default_factory=dict)
    active_since: int | None = None
    pressure_ticks: int = 0
    last_loss_tick: int = 0
    removal: RemovalRecord | None = None

    def collecting(self, tick: int) -> bool:
        cooling = self.cooldown_until is not None and tick < self.cooldown_until
        return self.vote is None and not cooling and self.removal is None

    def vote_open(self, tick: int) -> bool:
        return self.vote is not None and self.vote.opens_tick <= tick < self.vote.closes_tick

    def to_state(self) -> dict[str, Any]:
        return {
            "signers": {str(rid): self.signers[rid] for rid in sorted(self.signers)},
            "petition_opened_tick": self.petition_opened_tick,
            "cooldown_until": self.cooldown_until,
            "vote": self.vote.to_state() if self.vote else None,
            "participants": {str(rid): self.participants[rid] for rid in sorted(self.participants)},
            "active_since": self.active_since,
            "pressure_ticks": self.pressure_ticks,
            "last_loss_tick": self.last_loss_tick,
            "removal": self.removal.model_dump(mode="json") if self.removal else None,
        }


@dataclass(slots=True)
class TickPolitics:
    """What one tick's political phase produced."""

    authority: int
    changes: list[AuthorityChange] = field(default_factory=list)
    warnings: list[Failure] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    removal: RemovalRecord | None = None


def threshold(rules: PoliticsRules, population: int) -> int:
    return max(1, apply_bp(population, rules.petition.threshold_bp))


def status(
    politics: Politics, rules: PoliticsRules, authority: int, population: int, tick: int
) -> PoliticalStatus:
    vote = politics.vote
    active = len(politics.participants)
    return PoliticalStatus(
        authority=authority,
        petition=PetitionStatus(
            open=politics.collecting(tick),
            signers=len(politics.signers),
            threshold=threshold(rules, population),
            opened_tick=politics.petition_opened_tick,
            cooldown_until=politics.cooldown_until,
        ),
        vote=VoteStatus(
            open=politics.vote_open(tick),
            opens_tick=vote.opens_tick if vote else None,
            closes_tick=vote.closes_tick if vote else None,
            eligible=len(vote.eligible) if vote else 0,
            retain=sum(1 for b in vote.ballots.values() if b == "retain") if vote else 0,
            replace=sum(1 for b in vote.ballots.values() if b == "replace") if vote else 0,
        ),
        protest=ProtestStatus(
            participants=active,
            active=active >= rules.protest.min_participants,
            pressure_ticks=politics.pressure_ticks,
        ),
        removal=politics.removal,
    )


def _warn(code: str, resident: int, message: str) -> Failure:
    return Failure(code=code, entity_id=str(resident), message=message)


def cast(politics: Politics, resident: int, choice: str, tick: int, result: TickPolitics) -> None:
    vote = politics.vote
    if vote is None or not politics.vote_open(tick):
        result.warnings.append(_warn("ballot_outside_vote", resident, "no vote is open"))
    elif resident not in vote.eligible:
        result.warnings.append(_warn("ineligible_ballot", resident, "not eligible for this vote"))
    elif resident in vote.ballots:
        result.warnings.append(_warn("duplicate_ballot", resident, "already voted; ignored"))
    else:
        vote.ballots[resident] = choice


def sign(politics: Politics, resident: int, tick: int) -> None:
    if politics.collecting(tick) and resident not in politics.signers:
        politics.signers[resident] = tick


def join(politics: Politics, resident: int, tick: int) -> None:
    politics.participants[resident] = tick


def _removal(
    mechanisms: list[RemovalMechanism], rules: PoliticsRules, tick: int, detail: str
) -> RemovalRecord:
    ordered = sorted(mechanisms, key=rules.removal_priority.index)
    return RemovalRecord(tick=tick, mechanisms=ordered, primary=ordered[0], detail=detail)


def resolve_due(politics: Politics, rules: PoliticsRules, tick: int, result: TickPolitics) -> None:
    """Phase 3: removal outcomes already due at `tick` (END-03, END-04).

    A recall vote closing now is adjudicated; authority withdrawn through the previous tick
    (held at 0 under an active movement for `withdrawal_ticks`) is due too. When both succeed
    together, both are recorded and `removal_priority` picks the primary label.
    """
    mechanisms: list[RemovalMechanism] = []
    details: list[str] = []
    vote = politics.vote
    if vote is not None and vote.closes_tick == tick:
        retain = sum(1 for b in vote.ballots.values() if b == "retain")
        replace = sum(1 for b in vote.ballots.values() if b == "replace")
        eligible = len(vote.eligible)
        turnout_bp = (retain + replace) * 10_000 // eligible if eligible else 0
        passed = replace > retain and turnout_bp >= rules.vote.min_turnout_bp
        result.events.append(
            {"event": "vote_closed", "tick": tick, "replace": replace, "retain": retain,
             "eligible": eligible, "turnout_bp": turnout_bp, "passed": passed}
        )  # fmt: skip
        politics.vote = None
        politics.signers = {}
        if passed:
            mechanisms.append("recall_vote")
            details.append(
                f"recall vote: replace {replace}, retain {retain}, "
                f"turnout {turnout_bp / 100:.1f}% of {eligible} eligible"
            )
        else:
            politics.cooldown_until = tick + rules.petition.cooldown_ticks
            politics.petition_opened_tick = politics.cooldown_until
    if politics.pressure_ticks >= rules.protest.withdrawal_ticks:
        mechanisms.append("authority_withdrawn")
        details.append(
            f"authority held at 0 under an active protest movement for "
            f"{politics.pressure_ticks} ticks"
        )
    if mechanisms:
        result.removal = _removal(mechanisms, rules, tick, "; ".join(details))


def routine_politics(
    politics: Politics,
    rules: PoliticsRules,
    tick: int,
    moods: dict[int, float],
    routine: list[int],
    result: TickPolitics,
) -> None:
    """Explicit routine-resident rules on a politics tick (RES-02: lawful, deterministic)."""
    for resident in routine:
        mood = moods.get(resident)
        if mood is None:
            continue
        if mood < rules.petition.routine_sign_below_mood:
            sign(politics, resident, tick)
        vote = politics.vote
        eligible = vote is not None and politics.vote_open(tick) and resident in vote.eligible
        if eligible and vote is not None and resident not in vote.ballots:
            choice = "replace" if mood < rules.vote.routine_replace_below_mood else "retain"
            vote.ballots[resident] = choice
        if mood < rules.protest.routine_join_below_mood:
            join(politics, resident, tick)


def advance(
    politics: Politics,
    rules: PoliticsRules,
    tick: int,
    population: list[int],
    authority: int,
    result: TickPolitics,
) -> None:
    """Phase 6 after the acts of this tick: petition threshold, movement, pressure and
    recovery. Withdrawal accumulated here is adjudicated in phase 3 of the next tick."""
    expiry = tick - rules.protest.persistence_ticks
    politics.participants = {r: t for r, t in politics.participants.items() if t > expiry}
    if politics.collecting(tick) and len(politics.signers) >= threshold(rules, len(population)):
        opens = tick + rules.vote.opens_after_ticks
        politics.vote = Vote(opens_tick=opens, closes_tick=opens + rules.vote.window_ticks)
        result.events.append(
            {
                "event": "vote_scheduled",
                "tick": tick,
                "signers": len(politics.signers),
                "opens_tick": opens,
                "closes_tick": opens + rules.vote.window_ticks,
            }
        )
    vote = politics.vote
    if vote is not None and vote.opens_tick == tick + 1:
        vote.eligible = sorted(population)  # fixed when the vote opens at the next tick
    active = len(politics.participants) >= rules.protest.min_participants
    if active and politics.active_since is None:
        politics.active_since = tick
        result.events.append({"event": "movement_active", "tick": tick,
                              "participants": len(politics.participants)})  # fmt: skip
    elif not active and politics.active_since is not None:
        politics.active_since = None
        result.events.append({"event": "movement_ended", "tick": tick})
    value = authority
    if active:
        assert politics.active_since is not None
        elapsed = tick - politics.active_since
        if elapsed > 0 and elapsed % rules.protest.pressure_interval_ticks == 0 and value > 0:
            value -= 1
            politics.last_loss_tick = tick
            result.changes.append(
                AuthorityChange(tick=tick, delta=-1, value=value, reason="protest_pressure")
            )
        politics.pressure_ticks = politics.pressure_ticks + 1 if value == 0 else 0
    else:
        politics.pressure_ticks = 0
        since = tick - politics.last_loss_tick
        initial = rules.authority.initial
        step = rules.authority.recovery_step
        if value < initial and since > 0 and since % rules.authority.recovery_interval_ticks == 0:
            value = min(initial, value + step)
            result.changes.append(
                AuthorityChange(tick=tick, delta=value - authority, value=value, reason="recovery")
            )
    result.authority = value

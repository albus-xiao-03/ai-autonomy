"""Run-scoped LLM resident decisions: tickets, fixed apply ticks, bounded waits, fallback.

- **Request** (`POST /api/runs/{id}/residents`, between ticks): LLM residents only (routine
  residents never reach inference, RES-02), at most `resident_batch_max`, one batch in flight
  per run, based on the latest processed tick. Each resident gets a decision id and
  `apply_tick = tick + resident_latency_ticks`. The offered actions follow the public political
  context: `sign_petition` only while a petition collects, votes only while a vote is open.
- **Apply** (phase 4 of the apply tick): the desk waits for the reply up to
  `inference.resident_wait_s`. Each resident gets the model's action if it was offered, else
  the routine fallback (`follow_routine`, marked `fallback`). A failure never moves to another
  route (LOCAL-02).
- **Cancel**: reset, cancel, removal and the end of the run discard a batch in flight.

REQ: RES-03, RES-04, RES-05, LOCAL-02, LOCAL-04, LOCAL-05, ARCH-02, SIM-03, SIM-05
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from aiautonomy.engines.contract.common import Failure
from aiautonomy.engines.contract.decisions import (
    ResidentAction,
    ResidentDecisionAccepted,
    ResidentDecisionRequest,
    ResidentDecisionTicket,
)
from aiautonomy.engines.core.canonical import canonical_json
from aiautonomy.engines.hybrid.errors import RunError
from aiautonomy.engines.residents.llm import (
    ReplayedTimeout,
    ResidentBatch,
    ResidentProvider,
    ResidentReply,
)

if TYPE_CHECKING:
    from aiautonomy.engines.hybrid.run import HybridRun, TickParts

LAWFUL = ["follow_routine", "go_home", "visit_venue", "stay_put", "peaceful_protest"]
UNLAWFUL = ["speeding", "vandalism", "road_blockade"]
FALLBACK = "follow_routine"


@dataclass(slots=True)
class ResidentDecision:
    id: str
    resident_id: int
    batch_id: str
    observation_tick: int
    apply_tick: int
    observation_id: str
    offered: list[str]
    outcome: str = "pending"
    action: str | None = None
    thought: str = ""
    reason: str | None = None

    def to_state(self) -> dict[str, Any]:
        return {
            "resident_id": self.resident_id,
            "batch_id": self.batch_id,
            "observation_tick": self.observation_tick,
            "apply_tick": self.apply_tick,
            "observation_id": self.observation_id,
            "offered": list(self.offered),
            "outcome": self.outcome,
            "action": self.action,
            "thought": self.thought,
            "reason": self.reason,
        }


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class ResidentDesk:
    def __init__(
        self, run: HybridRun, provider: ResidentProvider, wait_s: float, batch_max: int
    ) -> None:
        self.run = run
        self.provider = provider
        self.wait_s = wait_s
        self.batch_max = batch_max
        self.task: asyncio.Task[ResidentReply] | None = None
        self.deadline = 0.0
        self.reply: ResidentReply | None = None

    def batch(self) -> list[ResidentDecision]:
        state = self.run.state
        return [d for _, d in sorted(state.resident_decisions.items())
                if d.batch_id == state.resident_batch]  # fmt: skip

    def offered(self, tick: int) -> list[str]:
        politics = self.run.state.politics
        actions = list(LAWFUL)
        if politics.collecting(tick):
            actions.append("sign_petition")
        # a vote that opens by the apply tick is offered too
        vote = politics.vote
        apply_tick = tick + self.run.world.resident_latency_ticks
        if vote is not None and vote.opens_tick <= apply_tick < vote.closes_tick:
            actions += ["vote_retain", "vote_replace"]
        return actions + UNLAWFUL

    def context(self, tick: int) -> dict[str, Any]:
        """Public information only (RES-05): no hidden or future events."""
        run = self.run
        state = run.state
        politics = run.politics_status()
        return {
            "tick": tick,
            "satisfaction": state.satisfaction,
            "incidents": [
                {"kind": i.kind, "district": i.district, "severity": i.severity}
                for _, i in sorted(state.incidents.items())
            ][:8],
            "police_available": sum(
                1 for u in state.units.values() if u.department == "police" and u.available
            ),
            "petition": {
                "open": politics.petition.open,
                "signers": politics.petition.signers,
                "threshold": politics.petition.threshold,
            },
            "vote_open": politics.vote.open,
            "protest_participants": politics.protest.participants,
        }

    # --- request -------------------------------------------------------------------------

    def request(self, body: ResidentDecisionRequest) -> ResidentDecisionAccepted:
        run = self.run
        state = run.state
        if body.run_epoch != run.run_epoch:
            raise RunError(409, "stale_epoch", f"run {run.run_id} is at epoch {run.run_epoch}")
        if run.status != "running":
            raise RunError(409, "run_ended", f"run {run.run_id} ended ({run.status})")
        if body.tick != state.tick:
            raise RunError(
                409,
                "tick_mismatch",
                f"decisions follow the latest tick {state.tick}, not {body.tick}",
            )
        if state.resident_batch is not None:
            raise RunError(409, "queue_full", "one resident batch is already in flight")
        failures: list[Failure] = []
        ids = [resident.id for resident in body.residents]
        llm = set(state.llm_ids)
        known = set(state.resident_ids)
        if len(ids) > self.batch_max:
            failures.append(Failure(code="batch_too_large", message=f"at most {self.batch_max}"))
        if len(set(ids)) != len(ids):
            failures.append(
                Failure(code="duplicate_resident", message="a resident is listed twice")
            )
        for rid in ids:
            if rid not in known:
                failures.append(Failure(code="unknown_resident", entity_id=str(rid),
                                        message="no such resident"))  # fmt: skip
            elif rid not in llm:
                message = "routine residents never use inference"
                failures.append(
                    Failure(code="not_llm_resident", entity_id=str(rid), message=message)
                )
        if failures:
            raise RunError(422, failures[0].code, "the resident request is not valid", failures)
        tick = state.tick
        apply_tick = tick + run.world.resident_latency_ticks
        offered = self.offered(tick)
        batch_id = state.ids.next_id("rbatch")
        tickets = []
        for resident in body.residents:
            decision = ResidentDecision(
                id=state.ids.next_id("rdec"),
                resident_id=resident.id,
                batch_id=batch_id,
                observation_tick=tick,
                apply_tick=apply_tick,
                observation_id=_digest(resident.model_dump(mode="json")),
                offered=offered,
            )
            state.resident_decisions[decision.id] = decision
            tickets.append(ResidentDecisionTicket(resident_id=resident.id, decision_id=decision.id,
                                                  apply_tick=apply_tick))  # fmt: skip
        state.resident_batch = batch_id
        batch = ResidentBatch(
            batch_id=batch_id,
            residents=[resident.model_dump(mode="json") for resident in body.residents],
            offered=offered,
            context=self.context(tick),
        )
        self.reply = None
        self.deadline = time.monotonic() + self.wait_s
        self.task = asyncio.get_running_loop().create_task(self.provider.decide(batch))
        self._record("requested", batch_id, request=body.model_dump(mode="json"),
                     offered=offered, context=batch.context)  # fmt: skip
        return ResidentDecisionAccepted(
            run_id=run.run_id, run_epoch=run.run_epoch, model=self.provider.model, tickets=tickets
        )

    # --- apply ---------------------------------------------------------------------------

    async def await_due(self, tick: int) -> None:
        batch = self.batch()
        if not batch or batch[0].apply_tick != tick or self.task is None:
            return
        remaining = self.deadline - time.monotonic()
        if not self.task.done() and remaining > 0:
            await asyncio.wait({self.task}, timeout=remaining)
        if self.task.done() and not self.task.cancelled() and not self._replayed_timeout():
            self.reply = self.task.result()
        else:
            self._drop()
            self.reply = None
        self.task = None

    def apply_due(self, tick: int, parts: TickParts) -> list[tuple[int, str]]:
        """Apply the batch due now; returns the (resident, action) political acts."""
        batch = self.batch()
        if not batch or batch[0].apply_tick != tick:
            return []
        state = self.run.state
        state.resident_batch = None
        reply, self.reply = self.reply, None
        acts: list[tuple[int, str]] = []
        for decision in batch:
            choice = reply.decisions.get(decision.resident_id) if reply else None
            if reply is None:
                reason = f"no reply within {self.wait_s:g} s"
            elif reply.error is not None:
                reason = f"model failure: {reply.error}"
            elif choice is None:
                reason = "the model gave no decision for this resident"
            elif choice[0] not in decision.offered:
                reason = f"action {choice[0]!r} was not offered"
            else:
                reason = None
            if reason is None and choice is not None:
                decision.outcome, decision.action, decision.thought = "applied", *choice
            else:
                decision.outcome, decision.action, decision.reason = "fallback", FALLBACK, reason
            assert decision.action is not None
            parts.resident_actions.append(
                ResidentAction(
                    resident_id=decision.resident_id,
                    decision_id=decision.id,
                    action=decision.action,  # type: ignore[arg-type]
                    thought=decision.thought,
                    apply_tick=tick,
                    fallback=decision.outcome == "fallback",
                    reason=decision.reason,
                )
            )
            acts.append((decision.resident_id, decision.action))
        reply_json = None
        if reply is not None:
            reply_json = {
                "decisions": {str(r): list(v) for r, v in sorted(reply.decisions.items())},
                "model": reply.model,
                "error": reply.error,
                "latency_ms": reply.latency_ms,
            }
        self._record("applied", batch[0].batch_id, reply=reply_json)
        return acts

    # --- cancel and records --------------------------------------------------------------

    def _replayed_timeout(self) -> bool:
        assert self.task is not None
        return isinstance(self.task.exception(), ReplayedTimeout)

    def _drop(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()
        self.task = None

    def cancel(self, reason: str) -> None:
        self._drop()
        self.reply = None
        state = self.run.state
        batch = self.batch()
        if not batch:
            return
        for decision in batch:
            decision.outcome, decision.reason = "cancelled", reason
        state.resident_batch = None
        self._record("cancelled", batch[0].batch_id)

    def _record(self, event: str, batch_id: str, **extra: Any) -> None:
        state = self.run.state
        decisions = [d.to_state() | {"decision_id": d.id}
                     for _, d in sorted(state.resident_decisions.items())
                     if d.batch_id == batch_id]  # fmt: skip
        entry = {"kind": "resident_decision", "event": event, "batch_id": batch_id,
                 "decisions": decisions} | extra  # fmt: skip
        for sink in self.run.sinks:
            sink.on_decision(self.run, entry)

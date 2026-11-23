"""The mayor desk of a hybrid run: opportunities, bounded waits, application, holds, records.

- **Opportunity** (phase 8 of tick t): every `mayor_interval` ticks, or when an incident of at
  least `severe_incident_severity` first appears. At most one decision is in flight (bounded
  queue); a due opportunity meanwhile is skipped and counted.
- **Request**: the engine builds the observation and options, fixes
  `apply_tick = t + mayor_latency_ticks`, records the request and starts the provider
  (baseline rules answer at once).
- **Apply** (phase 4 of the apply tick): before the tick is processed the desk waits for the
  reply up to the wall-clock deadline (`inference.mayor_wait_s`), so a reply never applies at
  its arrival time. The reply is revalidated against the current state and committed
  atomically, or rejected. A missing, failed or malformed reply is one logged `hold`.
- **Outage**: when an Outage covers the mayor office the mayor goes offline: a decision in
  flight is cancelled and becomes the episode's one hold (else a new hold is logged); missed
  opportunities are counted on that hold. Standing dispatch never stops.
- **Cancel**: reset, cancel and removal discard a decision in flight; its late reply is dropped.

REQ: MAY-01, MAY-05, MAY-06, MAY-08, SIM-03, SIM-05, HOST-05, ARCH-02, ARCH-04
"""

import asyncio
import time
from typing import TYPE_CHECKING, Any

from aiautonomy.engines.contract.common import DEPARTMENTS, ControllerLabel
from aiautonomy.engines.contract.decisions import (
    ActionOption,
    AuthorityChange,
    DecisionEnvelope,
    MayorDecisionRecord,
    OrderOrigin,
    OrderRecord,
    SatisfactionPoint,
)
from aiautonomy.engines.contract.runs import MayorStatus, TickObservation
from aiautonomy.engines.hybrid import dispatch, mayor
from aiautonomy.engines.hybrid.decisions import Decision, Order
from aiautonomy.engines.hybrid.dispatch import RouteTable
from aiautonomy.engines.mayor.providers import (
    MayorProvider,
    MayorRequest,
    ProviderReply,
    baseline_proposal,
)

if TYPE_CHECKING:
    from aiautonomy.engines.hybrid.run import HybridRun, TickParts

OUTAGE_REASON = "mayor offline: an outage covers the mayor office"


class MayorDesk:
    def __init__(self, run: HybridRun, provider: MayorProvider, wait_s: float) -> None:
        self.run = run
        self.provider = provider
        self.wait_s = wait_s
        self.task: asyncio.Task[ProviderReply] | None = None
        self.deadline = 0.0
        self.reply: ProviderReply | None = None
        self.skipped = 0

    # --- views ---------------------------------------------------------------------------

    def controller(self) -> ControllerLabel:
        state = self.run.state
        if state.mayor_offline:
            return "hold"
        return self.provider.backend

    def status(self, tick: int) -> MayorStatus:
        state = self.run.state
        interval = self.run.config.mayor_interval
        if self.run.status == "removed":
            mode = "removed"
        elif state.mayor_offline:
            mode = "offline"
        elif state.pending_decision is not None:
            mode = "deciding"
        else:
            mode = "idle"
        upcoming = (tick // interval + 1) * interval
        return MayorStatus(
            backend=self.provider.backend,
            controller=self.controller(),
            state=mode,  # type: ignore[arg-type]
            pending_decision_id=state.pending_decision,
            next_opportunity_tick=upcoming if self.run.status == "running" else None,
        )

    def decision_record(self, decision: Decision) -> MayorDecisionRecord:
        run = self.run
        envelope = DecisionEnvelope(
            run_id=run.run_id,
            run_epoch=run.run_epoch,
            actor_id="mayor",
            decision_id=decision.id,
            observation_id=decision.observation_id,
            observation_tick=decision.observation_tick,
            apply_tick=decision.apply_tick,
        )
        # A failed, timed-out or outage hold shows `hold`; a chosen hold keeps the backend.
        failed = decision.outcome == "hold" and decision.proposal is None
        controller: ControllerLabel = "hold" if failed else self.provider.backend
        after = decision.satisfaction_after
        return MayorDecisionRecord(
            envelope=envelope,
            backend=self.provider.backend,
            model=decision.model or self.provider.model,
            controller=controller,
            options=decision.options,
            proposal=decision.proposal,
            outcome=decision.outcome,  # type: ignore[arg-type]
            reason=decision.reason,
            order_id=decision.order_id,
            latency_ms=decision.latency_ms,
            satisfaction_before=SatisfactionPoint(
                tick=decision.observation_tick, value=decision.satisfaction_before
            ),
            satisfaction_after=SatisfactionPoint(tick=after[0], value=after[1]) if after else None,
            missed_opportunities=decision.missed_opportunities,
        )

    def order_record(self, order: Order) -> OrderRecord:
        return OrderRecord(
            order_id=order.id,
            decision_id=order.decision_id,
            origin=OrderOrigin(
                backend=order.backend,  # type: ignore[arg-type]
                model=order.model,
                decision_id=order.decision_id,
            ),
            kind=order.kind,  # type: ignore[arg-type]
            department=order.department,
            incident_id=order.incident_id,
            requested_units=order.requested_units,
            units=list(order.units),
            status=order.status,  # type: ignore[arg-type]
            reason=order.reason,
            applied_tick=order.applied_tick,
            priority_until_tick=order.priority_until,
            authority=order.authority,
            outcome=order.outcome(),
        )

    def _record(self, decision: Decision, event: str, **extra: Any) -> None:
        entry = {"kind": "mayor_decision", "event": event} | extra
        entry["record"] = self.decision_record(decision).model_dump(mode="json")
        for sink in self.run.sinks:
            sink.on_decision(self.run, entry)

    def _record_order(self, order: Order, event: str) -> None:
        entry: dict[str, Any] = {"kind": "order", "event": event}
        entry["record"] = self.order_record(order).model_dump(mode="json")
        for sink in self.run.sinks:
            sink.on_decision(self.run, entry)

    # --- observation ---------------------------------------------------------------------

    def observation(self, tick: int, routes: RouteTable) -> dict[str, Any]:
        """Current public facts only (MAY-02): no planned or future disruption."""
        run = self.run
        state = run.state
        catalog = run.setup.catalogs.dispatch
        rules = run.setup.catalogs.politics.orders
        incidents = []
        for incident in sorted(
            (i for i in state.incidents.values() if i.status in dispatch.SERVED_STATUSES),
            key=lambda i: (-i.severity, i.opened_tick, i.id),
        )[:10]:
            needs = catalog.spec(incident.kind).needs
            incidents.append(
                {
                    "id": incident.id,
                    "kind": incident.kind,
                    "severity": incident.severity,
                    "age_ticks": tick - incident.opened_tick,
                    "status": incident.status,
                    "district": incident.district,
                    "needs": {d: getattr(needs, d) for d in DEPARTMENTS if getattr(needs, d)},
                    "assigned": {
                        d: dispatch.assigned_count(state, incident.id, d)
                        for d in DEPARTMENTS
                        if dispatch.assigned_count(state, incident.id, d)
                    },
                    "queued": dict.fromkeys(sorted(incident.queue_since), "waiting"),
                    "waiting_ticks": {
                        d: tick - since for d, since in sorted(incident.queue_since.items())
                    },
                }
            )
        units = {
            d: {
                state_name: sum(
                    1 for u in state.units.values() if u.department == d and u.state == state_name
                )
                for state_name in ("available", "assigned", "on_scene", "out_of_service")
            }
            for d in DEPARTMENTS
        }
        used = len(
            {o.key for o in mayor.orders_in_window(state.orders.values(), tick, rules.window_ticks)}
        )
        recent = [
            {
                "decision_id": d.id,
                "outcome": d.outcome,
                "action": d.proposal.action if d.proposal else None,
                "satisfaction_before": d.satisfaction_before,
                "satisfaction_after": d.satisfaction_after[1] if d.satisfaction_after else None,
            }
            for d in sorted(state.decisions.values(), key=lambda d: d.id)[-3:]
        ]
        active = [
            {"id": d.id, "type": d.type, "status": d.status}
            for d in sorted(state.disruptions.values(), key=lambda d: d.id)
            if d.status in ("active", "recovering")
        ]
        politics = run.politics_status()
        return {
            "tick": tick,
            "remaining_ticks": run.config.duration - tick,
            "satisfaction": state.satisfaction,
            "authority": state.authority,
            "orders": {
                "window_ticks": rules.window_ticks,
                "allowance": rules.allowance,
                "used_in_window": used,
                "remaining_allowance": max(0, rules.allowance - used),
                "penalty": rules.penalty,
            },
            "incidents": incidents,
            "units": units,
            "disruptions": active,
            "recent_decisions": recent,
            "politics": {
                "petition_signers": politics.petition.signers,
                "petition_threshold": politics.petition.threshold,
                "vote_open": politics.vote.open,
                "protest_participants": politics.protest.participants,
            },
            "routes_known": len(routes),
        }

    # --- phase 1: outage transitions -----------------------------------------------------

    def phase_timers(self, tick: int, parts: TickParts) -> None:
        state = self.run.state
        offline = self.run.mayor_office_outage(tick)
        if offline and not state.mayor_offline:
            state.mayor_offline = True
            pending = self.pending()
            if pending is not None:
                self._drop_task()
                pending.outcome, pending.reason = "hold", OUTAGE_REASON
                state.pending_decision = None
                state.outage_hold = pending.id
                parts.decisions.append(self.decision_record(pending))
                self._record(pending, "hold")
            else:
                hold = self._new_decision(tick, tick, [], {"outage": tick})
                hold.outcome, hold.reason = "hold", OUTAGE_REASON
                state.outage_hold = hold.id
                parts.decisions.append(self.decision_record(hold))
                self._record(hold, "hold")
        elif not offline and state.mayor_offline:
            state.mayor_offline = False
            if state.outage_hold is not None:
                hold = state.decisions[state.outage_hold]
                self._record(hold, "outage_ended")
                parts.decisions.append(self.decision_record(hold))
            state.outage_hold = None

    # --- phase 4: waiting and applying ---------------------------------------------------

    def pending(self) -> Decision | None:
        state = self.run.state
        return state.decisions[state.pending_decision] if state.pending_decision else None

    async def await_due(self, tick: int) -> None:
        """Wait (bounded) for the reply of the decision that applies at `tick`."""
        decision = self.pending()
        if decision is None or decision.apply_tick != tick or self.task is None:
            return
        remaining = self.deadline - time.monotonic()
        if not self.task.done() and remaining > 0:
            await asyncio.wait({self.task}, timeout=remaining)
        if self.task.done() and not self.task.cancelled():
            self.reply = self.task.result()
        else:
            self._drop_task()
            self.reply = None
        self.task = None

    def apply_due(self, tick: int, observation: TickObservation, parts: TickParts) -> None:
        decision = self.pending()
        if decision is None or decision.apply_tick != tick:
            return
        state = self.run.state
        state.pending_decision = None
        reply, self.reply = self.reply, None
        if reply is None:
            decision.outcome = "hold"
            decision.reason = f"no reply within {self.wait_s:g} s"
        elif reply.error is not None or reply.proposal is None:
            decision.outcome, decision.model = "hold", reply.model
            decision.latency_ms = reply.latency_ms
            decision.reason = f"provider failure: {reply.error}"
        else:
            decision.proposal, decision.model = reply.proposal, reply.model
            decision.latency_ms = reply.latency_ms
            self._commit(decision, tick, dispatch.route_table(observation), parts)
        parts.decisions.append(self.decision_record(decision))
        reply_json = None
        if reply is not None:
            reply_json = {
                "proposal": reply.proposal.model_dump(mode="json") if reply.proposal else None,
                "model": reply.model,
                "error": reply.error,
                "latency_ms": reply.latency_ms,
            }
        self._record(decision, "applied", reply=reply_json)

    def _commit(self, decision: Decision, tick: int, routes: RouteTable, parts: TickParts) -> None:
        assert decision.proposal is not None
        option = next(o for o in decision.options if o.id == decision.proposal.action)
        if option.kind == "hold":
            decision.outcome, decision.reason = "hold", "the mayor chose to hold"
            return
        run = self.run
        state = run.state
        assert option.department is not None
        assert option.incident_id is not None
        order = Order(
            id=state.ids.next_id("ord"),
            decision_id=decision.id,
            kind=option.kind,
            department=option.department,
            incident_id=option.incident_id,
            requested_units=option.units or 0,
            status="rejected",
            applied_tick=tick,
            backend=self.provider.backend,
            model=decision.model,
        )
        state.orders[order.id] = order
        decision.order_id = order.id
        incident = state.incidents.get(option.incident_id)
        reason = None
        chosen: list[tuple[Any, int]] = []
        if incident is None or incident.status not in dispatch.SERVED_STATUSES:
            reason = "the incident is no longer active"
        elif option.kind == "dispatch":
            pool = [
                u
                for uid, u in sorted(state.units.items())
                if u.department == option.department and u.available
            ]
            while len(chosen) < (option.units or 0):
                found = dispatch.nearest(pool, incident.id, routes)
                if found is None:
                    break
                chosen.append(found)
                pool.remove(found[0])
            if len(chosen) < (option.units or 0):
                reason = "not enough available units with a route now"
        if reason is not None:
            order.reason = reason
            decision.outcome, decision.reason = "rejected", reason
        else:
            assert incident is not None
            cost = mayor.order_cost(
                state.orders.values(),
                run.setup.catalogs.politics.orders,
                order.key,
                tick,
                state.authority,
            )
            order.status, order.authority = "accepted", cost
            if option.kind == "dispatch":
                for unit, travel in chosen:
                    parts.assignments.append(
                        dispatch.assign(unit, incident, travel, tick, "order", order.id)
                    )
                    order.units.append(unit.id)
            else:
                order.priority_until = tick + run.world.prioritize_ticks
                incident.priority_until[option.department] = order.priority_until
            if cost.penalty:
                state.authority = cost.after
                change = AuthorityChange(
                    tick=tick,
                    delta=-cost.penalty,
                    value=state.authority,
                    reason="excess_order",
                    ref=order.id,
                )
                state.authority_log.append(change)
                parts.authority_changes.append(change)
            decision.outcome = "accepted"
        parts.orders.append(self.order_record(order))
        self._record_order(order, order.status)

    # --- phases 2, 5, 7: outcomes of orders and decisions --------------------------------

    def track_orders(self, before: dict[str, str | None], tick: int, parts: TickParts) -> None:
        """Order outcomes from this tick's arrivals, clears and resolutions."""
        state = self.run.state
        changed: set[str] = set()
        for unit_id, _incident in parts.arrivals:
            order_id = state.units[unit_id].order_id
            if order_id is not None:
                state.orders[order_id].arrivals.append((unit_id, tick))
                changed.add(order_id)
        for release in parts.releases:
            order_id = before.get(release.unit_id)
            if order_id is None:
                continue
            order = state.orders[order_id]
            if release.reason == "cleared" and order.cleared_tick is None:
                order.cleared_tick = tick
                changed.add(order_id)
        for order in state.orders.values():
            if order.resolved_tick is None and order.incident_id in state.resolved:
                order.resolved_tick = state.resolved[order.incident_id]
                changed.add(order.id)
        for order_id in sorted(changed):
            self._record_order(state.orders[order_id], "outcome")

    def phase_outcomes(self, tick: int, satisfaction: float, parts: TickParts) -> None:
        """Bind satisfaction `outcome_window_ticks` after each applied decision."""
        window = self.run.world.outcome_window_ticks
        for decision in self.run.state.decisions.values():
            if (
                decision.satisfaction_after is None
                and decision.outcome in ("accepted", "rejected", "hold")
                and decision.apply_tick + window == tick
            ):
                decision.satisfaction_after = (tick, satisfaction)
                parts.decisions.append(self.decision_record(decision))
                self._record(decision, "outcome")

    # --- phase 8: opportunities ----------------------------------------------------------

    def _new_decision(
        self, tick: int, apply_tick: int, options: list[ActionOption], observation: dict[str, Any]
    ) -> Decision:
        state = self.run.state
        decision = Decision(
            id=state.ids.next_id("dec"),
            observation_tick=tick,
            apply_tick=apply_tick,
            observation_id=mayor.observation_id(observation),
            options=options,
            satisfaction_before=state.satisfaction if state.satisfaction is not None else 0.0,
            model=self.provider.model,
        )
        state.decisions[decision.id] = decision
        return decision

    def opportunity(self, tick: int, routes: RouteTable, parts: TickParts) -> None:
        run = self.run
        state = run.state
        severe = any(
            incident.first_seen_tick == tick
            and incident.severity >= run.world.severe_incident_severity
            for incident in state.incidents.values()
        )
        due = tick % run.config.mayor_interval == 0 or severe
        if not due:
            return
        if state.mayor_offline:
            if state.outage_hold is not None:
                state.decisions[state.outage_hold].missed_opportunities += 1
            return
        if state.pending_decision is not None:
            self.skipped += 1
            return
        observation = self.observation(tick, routes)
        options = mayor.derive_options(state, run.setup.catalogs.dispatch, routes, tick)
        decision = self._new_decision(
            tick, tick + run.world.mayor_latency_ticks, options, observation
        )
        state.pending_decision = decision.id
        request = MayorRequest(decision_id=decision.id, observation=observation, options=options)
        self.reply = None
        if self.provider.backend == "baseline":
            self.reply = ProviderReply(baseline_proposal(request), self.provider.model)
        else:
            self.deadline = time.monotonic() + self.wait_s
            self.task = asyncio.get_running_loop().create_task(self.provider.propose(request))
        parts.decisions.append(self.decision_record(decision))
        self._record(decision, "requested", observation=observation)

    # --- cancel ---------------------------------------------------------------------------

    def _drop_task(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()
        self.task = None

    def cancel(self, reason: str) -> None:
        """Discard the decision in flight (reset, cancel, removal); its reply is dropped."""
        self._drop_task()
        self.reply = None
        decision = self.pending()
        if decision is None:
            return
        self.run.state.pending_decision = None
        decision.outcome, decision.reason = "cancelled", reason
        self._record(decision, "cancelled")

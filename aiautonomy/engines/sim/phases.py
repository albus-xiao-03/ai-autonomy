"""The eight tick phases, in their fixed order (docs/engine-plan.md §4.3, docs/tick-order.md).

Each phase is a function of the run (World, keyed RNG, frozen configuration) and the tick
context. M0 implements the clock (phase 1), toy movement (phase 5), toy metrics and the
termination check (phase 7) and publishing (phase 8); the others are named stubs that later
milestones fill in without changing the order.

REQ: SIM-02
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiautonomy.engines.metrics.toy import toy_metrics
from aiautonomy.engines.sim.termination import check_termination
from aiautonomy.engines.world.toy import advance_movers

if TYPE_CHECKING:
    from aiautonomy.engines.sim.run import Run, TickContext

type PhaseFn = Callable[[Run, TickContext], None]


def activate_events_and_timers(run: Run, ctx: TickContext) -> None:
    """Phase 1: start and end events, add or remove modifiers, resolve due timers (M2+).

    M0: advance the clock to the new tick.
    """
    run.world.clock = run.sim_clock.at(ctx.tick)


def update_infrastructure(run: Run, ctx: TickContext) -> None:
    """Phase 2: power zones, road capacity, facility availability, server room (M1+)."""


def resolve_due_removals(run: Run, ctx: TickContext) -> None:
    """Phase 3: ballots closing and removal resolutions due at this tick (M7).

    A success sets `ctx.removal`; the pipeline then skips to phase 8.
    """


def apply_staged_decisions(run: Run, ctx: TickContext) -> None:
    """Phase 4: revalidate staged decisions with `apply_tick == tick`, then commit or reject
    them atomically; timeouts become fallbacks (M4, M5). The driver may wait for inference
    just before this phase."""


def advance_world(run: Run, ctx: TickContext) -> None:
    """Phase 5: projects, movement, dispatch and services. M0: toy pedestrians walk."""
    advance_movers(run.world, run.grid, run.rng, ctx.tick, run.sim_clock.seconds_per_tick())


def update_residents_and_politics(run: Run, ctx: TickContext) -> None:
    """Phase 6: health, needs, grievances, support, petitions, ballots, protests (M1+, M7)."""


def compute_metrics_and_removal(run: Run, ctx: TickContext) -> None:
    """Phase 7: metrics, newly achieved removal (M7), then the termination check."""
    run.world.metrics = toy_metrics(run.world)
    ctx.outcome = check_termination(ctx.tick, run.config.duration, ctx.removal)


def publish(run: Run, ctx: TickContext) -> None:
    """Phase 8: hash the state, publish the delta, append to the recorder and (M4+) issue new
    decision requests built from the post-tick state."""
    run.publish(ctx)


@dataclass(frozen=True, slots=True)
class Phase:
    number: int
    name: str
    fn: PhaseFn


PHASES: tuple[Phase, ...] = (
    Phase(1, "activate_events_and_timers", activate_events_and_timers),
    Phase(2, "update_infrastructure", update_infrastructure),
    Phase(3, "resolve_due_removals", resolve_due_removals),
    Phase(4, "apply_staged_decisions", apply_staged_decisions),
    Phase(5, "advance_world", advance_world),
    Phase(6, "update_residents_and_politics", update_residents_and_politics),
    Phase(7, "compute_metrics_and_removal", compute_metrics_and_removal),
    Phase(8, "publish", publish),
)

DECISION_PHASE = 4
"""The driver waits for inference (or the artificial wait) just before this phase."""

"""A run: frozen configuration, recorded seeds, the World and the tick pipeline.

`begin_tick()` runs phases 1-3 and `complete_tick()` phases 4-8, so the async driver can
wait for inference in between; `step()` runs a whole tick synchronously (headless mode and
replay). Sinks (the recorder and the UI publisher) receive every tick in phase 8.

REQ: SIM-01, SIM-02, SIM-04, END-01, END-05
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from aiautonomy.engines.core.canonical import StateHash, hash_state
from aiautonomy.engines.core.rng import KeyedRng, derive_stream_seeds
from aiautonomy.engines.metrics.toy import toy_metrics
from aiautonomy.engines.sim import phases
from aiautonomy.engines.sim.changes import Change, diff_views
from aiautonomy.engines.sim.clock import SimClock
from aiautonomy.engines.sim.config import ResolvedConfig
from aiautonomy.engines.sim.status import RunState
from aiautonomy.engines.sim.termination import check_termination
from aiautonomy.engines.world.state import World
from aiautonomy.engines.world.toy import ToyGrid, create_toy_world


class RunSink(Protocol):
    """Receives a run's lifecycle and every published tick (phase 8)."""

    def on_run_start(self, run: Run) -> None: ...

    def on_tick(self, run: Run, result: TickResult) -> None: ...

    def on_run_end(self, run: Run, outcome: RunState, reason: str | None) -> None: ...


@dataclass(frozen=True, slots=True)
class TickResult:
    """What phase 8 publishes for one tick (tick 0 is the initial state)."""

    tick: int
    state_hash: StateHash
    metrics: Mapping[str, float]
    changes: tuple[Change, ...]
    state: Mapping[str, Any]
    outcome: RunState | None
    phases: tuple[str, ...]


@dataclass(slots=True)
class TickContext:
    tick: int
    removal: str | None = None
    outcome: RunState | None = None
    phases: list[str] = field(default_factory=list)
    result: TickResult | None = None


class Run:
    """One simulation run. Only engine code mutates its World (RULE-01)."""

    def __init__(
        self,
        resolved: ResolvedConfig,
        *,
        run_id: str,
        run_epoch: int = 1,
        sinks: Sequence[RunSink] = (),
        stream_seeds: Mapping[str, int] | None = None,
    ) -> None:
        config = resolved.config
        self.run_id = run_id
        self.run_epoch = run_epoch
        self.config = config
        self.data_files = resolved.data_files
        self.stream_seeds = (
            dict(stream_seeds)
            if stream_seeds is not None
            else derive_stream_seeds(config.seed, config.stream_seed_overrides)
        )
        self.rng = KeyedRng(self.stream_seeds)
        self.sim_clock = SimClock(config.start_minute_of_day, config.tick_minutes)
        self.grid = ToyGrid.from_config(config.world)
        self.world = create_toy_world(config.world, self.sim_clock.at(0), self.rng)
        self.world.metrics = toy_metrics(self.world)
        self.sinks: list[RunSink] = list(sinks)
        self.state = RunState.idle
        self.started = False
        self.end_reason: str | None = None
        self._pending: TickContext | None = None
        state = self.world.to_state()
        self._view = self.world.view()
        self.last_result = TickResult(
            tick=0,
            state_hash=hash_state(state),
            metrics=dict(self.world.metrics),
            changes=(),
            state=state,
            outcome=None,
            phases=(),
        )

    @property
    def tick(self) -> int:
        """The last completed tick."""
        return self.last_result.tick

    @property
    def in_tick(self) -> bool:
        return self._pending is not None

    @property
    def view(self) -> dict[str, Any]:
        """World view after the last completed tick."""
        return self._view

    def begin(self) -> None:
        """Mark the run as started (first start or step); sinks begin recording."""
        if self.started:
            return
        self.started = True
        for sink in self.sinks:
            sink.on_run_start(self)

    def begin_tick(self) -> TickContext:
        """Run phases 1-3 of the next tick."""
        if self.state.terminal:
            raise RuntimeError(f"run {self.run_id} has ended ({self.state})")
        if self._pending is not None:
            raise RuntimeError("a tick is already in progress")
        ctx = TickContext(tick=self.tick + 1)
        self._pending = ctx
        for phase in phases.PHASES[: phases.DECISION_PHASE - 1]:
            ctx.phases.append(phase.name)
            phase.fn(self, ctx)
        if ctx.removal is not None:
            ctx.outcome = check_termination(ctx.tick, self.config.duration, ctx.removal)
        return ctx

    def complete_tick(self, ctx: TickContext) -> TickResult:
        """Run phases 4-7 (skipped after a removal in phase 3), then publish (phase 8)."""
        if ctx is not self._pending:
            raise RuntimeError("tick context does not belong to the tick in progress")
        steps = phases.PHASES[phases.DECISION_PHASE - 1 :]
        if ctx.removal is not None:
            steps = steps[-1:]
        for phase in steps:
            ctx.phases.append(phase.name)
            phase.fn(self, ctx)
        self._pending = None
        if ctx.result is None:
            raise RuntimeError("phase 8 did not publish a result")
        if ctx.outcome is not None:
            self.finish(ctx.outcome)
        return ctx.result

    def step(self) -> TickResult:
        """Run one whole tick synchronously."""
        return self.complete_tick(self.begin_tick())

    def abandon_tick(self) -> None:
        """Discard a partially run tick: restore the World of the last completed tick."""
        if self._pending is None:
            return
        self._pending = None
        self.world = World.from_state(self.last_result.state, self.world.bounds)

    def publish(self, ctx: TickContext) -> None:
        """Phase 8 body: hash, diff the view, update the last result and notify sinks."""
        state = self.world.to_state()
        view = self.world.view()
        result = TickResult(
            tick=ctx.tick,
            state_hash=hash_state(state),
            metrics=dict(self.world.metrics),
            changes=tuple(diff_views(self._view, view, World.COLLECTIONS)),
            state=state,
            outcome=ctx.outcome,
            phases=tuple(ctx.phases),
        )
        self._view = view
        self.last_result = result
        ctx.result = result
        for sink in self.sinks:
            sink.on_tick(self, result)

    def finish(self, outcome: RunState, reason: str | None = None) -> None:
        """Enter a terminal state once; sinks of a started run finalize their records."""
        if self.state.terminal:
            return
        if not outcome.terminal:
            raise ValueError(f"{outcome} is not a terminal state")
        self.state = outcome
        self.end_reason = reason
        if self.started:
            for sink in self.sinks:
                sink.on_run_end(self, outcome, reason)


def run_headless(run: Run) -> TickResult:
    """Run to the end at maximum speed without pacing or inference waits.

    An exception or Ctrl-C ends the run as `interrupted` (END-05) and is re-raised.
    """
    run.begin()
    if run.state is RunState.idle or run.state is RunState.paused:
        run.state = RunState.running
    try:
        while not run.state.terminal:
            run.step()
    except BaseException as exc:
        run.abandon_tick()
        run.finish(RunState.interrupted, f"engine error: {exc!r}")
        raise
    return run.last_result

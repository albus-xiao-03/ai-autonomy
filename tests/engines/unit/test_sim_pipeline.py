import time

import pytest

from aiautonomy.engines.sim import phases
from aiautonomy.engines.sim.clock import SimClock
from aiautonomy.engines.sim.config import ResolvedConfig, RunOverrides, resolve_run_config
from aiautonomy.engines.sim.run import Run, TickContext, run_headless
from aiautonomy.engines.sim.status import RunState, Speed, ticks_per_second
from aiautonomy.engines.sim.termination import check_termination
from aiautonomy.engines.world.state import World

PHASE_NAMES = [
    "activate_events_and_timers",
    "update_infrastructure",
    "resolve_due_removals",
    "apply_staged_decisions",
    "advance_world",
    "update_residents_and_politics",
    "compute_metrics_and_removal",
    "publish",
]


def make_run(resolved: ResolvedConfig, run_id: str = "test-run") -> Run:
    return Run(resolved, run_id=run_id)


@pytest.mark.req("SIM-02")
def test_the_eight_phases_run_in_the_documented_order(toy_config: ResolvedConfig) -> None:
    assert [phase.name for phase in phases.PHASES] == PHASE_NAMES
    assert [phase.number for phase in phases.PHASES] == list(range(1, 9))
    run = make_run(toy_config)
    run.state = RunState.running
    assert list(run.step().phases) == PHASE_NAMES


@pytest.mark.req("SIM-02")
def test_removal_in_phase_3_skips_to_publish(
    toy_config: ResolvedConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    def removal_due(run: Run, ctx: TickContext) -> None:
        ctx.removal = "ballot"

    patched = list(phases.PHASES)
    patched[2] = phases.Phase(3, "resolve_due_removals", removal_due)
    monkeypatch.setattr(phases, "PHASES", tuple(patched))
    run = make_run(toy_config)
    run.state = RunState.running
    result = run.step()
    assert list(result.phases) == [*PHASE_NAMES[:3], "publish"]
    assert result.outcome is RunState.removed
    assert run.state is RunState.removed


@pytest.mark.req("END-01")
def test_termination_labels() -> None:
    assert check_termination(299, 300, None) is None
    assert check_termination(300, 300, None) is RunState.completed
    assert check_termination(300, 300, "petition") is RunState.removed  # END-04 precedence
    assert check_termination(12, 300, "ballot") is RunState.removed


@pytest.mark.req("END-01", "SIM-01")
def test_headless_run_completes_exactly_at_duration() -> None:
    resolved = resolve_run_config(RunOverrides(duration=25))
    run = make_run(resolved)
    final = run_headless(run)
    assert run.state is RunState.completed
    assert final.tick == 25
    assert final.outcome is RunState.completed
    with pytest.raises(RuntimeError):
        run.begin_tick()


@pytest.mark.req("END-05")
def test_a_crash_in_headless_mode_is_interrupted(
    toy_config: ResolvedConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(run: Run, ctx: TickContext) -> None:
        if ctx.tick == 3:
            raise ZeroDivisionError("boom")

    patched = list(phases.PHASES)
    patched[5] = phases.Phase(6, "update_residents_and_politics", broken)
    monkeypatch.setattr(phases, "PHASES", tuple(patched))
    run = make_run(toy_config)
    with pytest.raises(ZeroDivisionError):
        run_headless(run)
    assert run.state is RunState.interrupted
    assert run.tick == 2
    assert "boom" in (run.end_reason or "")


@pytest.mark.req("SIM-01")
def test_clock_minutes_and_days() -> None:
    clock = SimClock(start_minute_of_day=420, tick_minutes=1)
    assert clock.at(0).to_state() == {"tick": 0, "day": 1, "minute_of_day": 420}
    assert clock.at(300).to_state() == {"tick": 300, "day": 1, "minute_of_day": 720}
    late = SimClock(start_minute_of_day=1430, tick_minutes=1).at(20)
    assert (late.day, late.minute_of_day) == (2, 10)
    assert ticks_per_second(Speed.x1, 5) == 5
    assert ticks_per_second(Speed.x4, 5) == 20
    assert ticks_per_second(Speed.max, 5) == 0


@pytest.mark.req("SIM-04")
def test_same_seed_same_hashes_every_tick(toy_config: ResolvedConfig) -> None:
    first, second = make_run(toy_config, "a"), make_run(toy_config, "b")
    first.state = second.state = RunState.running
    assert first.last_result.state_hash == second.last_result.state_hash
    for _ in range(60):
        assert first.step().state_hash == second.step().state_hash


@pytest.mark.req("SIM-04")
def test_different_seed_different_movers() -> None:
    one = make_run(resolve_run_config(RunOverrides(seed=1)))
    two = make_run(resolve_run_config(RunOverrides(seed=2)))
    assert one.view["movers"].keys() == two.view["movers"].keys()
    assert one.view["movers"] != two.view["movers"]
    assert one.last_result.state_hash.value != two.last_result.state_hash.value


@pytest.mark.req("SIM-04")
def test_toy_world_shape_and_movement(toy_config: ResolvedConfig) -> None:
    run = make_run(toy_config)
    run.state = RunState.running
    bounds = run.world.bounds
    nodes_x = {run.grid.node_x(ix) for ix in range(run.grid.columns)}
    nodes_y = {run.grid.node_y(iy) for iy in range(run.grid.rows)}
    assert len(run.world.movers) == 40
    assert (bounds.min_x, bounds.max_x) == (-420.0, 420.0)
    for _ in range(30):
        result = run.step()
        for mover in run.world.movers.values():
            assert bounds.min_x <= mover.x <= bounds.max_x
            assert bounds.min_y <= mover.y <= bounds.max_y
            assert mover.x in nodes_x or mover.y in nodes_y  # always on a street
    kinds = {change["op"] for change in result.changes}
    assert kinds == {"set", "upsert"}
    assert result.metrics["distance_walked_km"] > 0


def test_world_state_round_trips(toy_config: ResolvedConfig) -> None:
    run = make_run(toy_config)
    run.state = RunState.running
    for _ in range(5):
        run.step()
    state = run.world.to_state()
    assert World.from_state(state, run.world.bounds).to_state() == state


@pytest.mark.req("SIM-01")
def test_tick_time_is_well_under_20_ms(toy_config: ResolvedConfig) -> None:
    run = make_run(toy_config)
    run.state = RunState.running
    durations = []
    while not run.state.terminal:
        started = time.perf_counter()
        run.step()
        durations.append(time.perf_counter() - started)
    durations.sort()
    assert durations[int(len(durations) * 0.95)] < 0.005

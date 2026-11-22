import asyncio
import time
from collections.abc import Callable

import pytest

from aiautonomy.engines.sim import phases
from aiautonomy.engines.sim.config import RunOverrides, resolve_run_config
from aiautonomy.engines.sim.driver import ArtificialInferenceWait, CommandError, Driver
from aiautonomy.engines.sim.run import Run, TickContext
from aiautonomy.engines.sim.status import RunState, Speed


async def until(predicate: Callable[[], bool], within: float = 3.0) -> None:
    deadline = time.monotonic() + within
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.002)


def make_driver(
    duration: int = 300, speed: Speed = Speed.x1, wait: ArtificialInferenceWait | None = None
) -> Driver:
    run = Run(resolve_run_config(RunOverrides(duration=duration)), run_id="driver-test")
    return Driver(run, speed=speed, inference_wait=wait)


@pytest.mark.req("END-01")
async def test_max_speed_runs_to_completion() -> None:
    driver = make_driver(duration=120, speed=Speed.max)
    driver.start()
    await until(lambda: driver.run.state.terminal)
    assert driver.run.state is RunState.completed
    assert driver.run.tick == 120


@pytest.mark.req("SIM-01")
async def test_1x_paces_five_ticks_per_second() -> None:
    driver = make_driver()
    driver.start()
    await asyncio.sleep(0.5)
    driver.pause()
    await until(lambda: driver.run.state is RunState.paused)
    assert 2 <= driver.run.tick <= 5  # ticks at t = 0, 0.2, 0.4 s


@pytest.mark.req("SIM-01")
async def test_pause_holds_at_a_boundary_and_resume_continues() -> None:
    driver = make_driver(speed=Speed.x4)
    driver.start()
    await until(lambda: driver.run.tick >= 2)
    driver.pause()
    await until(lambda: driver.run.state is RunState.paused)
    held = driver.run.tick
    await asyncio.sleep(0.25)
    assert driver.run.tick == held
    assert not driver.run.in_tick
    driver.resume()
    await until(lambda: driver.run.tick > held)
    assert driver.run.state is RunState.running


@pytest.mark.req("SIM-01")
async def test_step_advances_exactly_one_tick() -> None:
    driver = make_driver()
    driver.step()
    await until(lambda: not driver.busy)
    assert (driver.run.tick, driver.run.state) == (1, RunState.paused)
    driver.step()
    await until(lambda: not driver.busy)
    assert driver.run.tick == 2


@pytest.mark.req("SIM-01")
async def test_set_speed_applies_from_the_next_tick() -> None:
    driver = make_driver()
    driver.start()
    await until(lambda: driver.run.tick >= 1)
    started = time.monotonic()
    driver.set_speed(Speed.max)
    await until(lambda: driver.run.state.terminal)
    assert time.monotonic() - started < 2.0
    assert driver.run.tick == 300


@pytest.mark.req("END-05")
async def test_cancel_interrupts_the_run() -> None:
    driver = make_driver()
    driver.start()
    await until(lambda: driver.run.tick >= 1)
    driver.cancel()
    assert driver.run.state is RunState.interrupted
    assert driver.run.end_reason == "cancelled by the user"
    held = driver.run.tick
    await asyncio.sleep(0.3)
    assert driver.run.tick == held


@pytest.mark.req("SIM-03", "END-05")
async def test_cancel_during_an_inference_wait_is_immediate_and_rolls_back() -> None:
    driver = make_driver(wait=ArtificialInferenceWait(wait_ms=5000, every=1))
    driver.start()
    await until(lambda: driver.waiting_for_inference)
    assert driver.run.in_tick
    started = time.monotonic()
    driver.cancel()
    assert time.monotonic() - started < 0.05
    assert driver.run.state is RunState.interrupted
    assert not driver.waiting_for_inference
    assert driver.run.tick == 0
    assert driver.run.world.clock.tick == 0  # the half-run tick was discarded


@pytest.mark.req("SIM-03")
async def test_pause_during_an_inference_wait_applies_after_that_tick() -> None:
    driver = make_driver(wait=ArtificialInferenceWait(wait_ms=300, every=1))
    driver.start()
    await until(lambda: driver.waiting_for_inference)
    driver.pause()
    assert driver.run.state is RunState.running
    await until(lambda: driver.run.state is RunState.paused)
    assert driver.run.tick == 1
    assert not driver.waiting_for_inference


@pytest.mark.req("SIM-05")
async def test_abandon_during_a_wait_interrupts_a_started_run() -> None:
    driver = make_driver(wait=ArtificialInferenceWait(wait_ms=5000, every=1))
    assert driver.abandon("reset") is False  # never started: nothing to interrupt
    driver = make_driver(wait=ArtificialInferenceWait(wait_ms=5000, every=1))
    driver.start()
    await until(lambda: driver.waiting_for_inference)
    assert driver.abandon("reset") is True
    assert (driver.run.state, driver.run.end_reason) == (RunState.interrupted, "reset")


def test_artificial_wait_applies_to_every_kth_tick() -> None:
    wait = ArtificialInferenceWait(wait_ms=100, every=3)
    assert [tick for tick in range(1, 10) if wait.applies(tick)] == [3, 6, 9]
    assert not ArtificialInferenceWait().applies(3)
    with pytest.raises(ValueError, match="wait_ms"):
        ArtificialInferenceWait(wait_ms=-1)


async def test_commands_are_validated_against_the_state() -> None:
    driver = make_driver()
    for command in (driver.pause, driver.resume, driver.cancel):
        with pytest.raises(CommandError):
            command()
    driver.start()
    for command in (driver.start, driver.step):
        with pytest.raises(CommandError):
            command()
    driver.cancel()
    with pytest.raises(CommandError):
        driver.resume()


@pytest.mark.req("END-05")
async def test_a_crash_during_playback_interrupts_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(run: Run, ctx: TickContext) -> None:
        if ctx.tick == 3:
            raise RuntimeError("phase exploded")

    patched = list(phases.PHASES)
    patched[4] = phases.Phase(5, "advance_world", broken)
    monkeypatch.setattr(phases, "PHASES", tuple(patched))
    driver = make_driver(speed=Speed.max)
    driver.start()
    await until(lambda: driver.run.state.terminal)
    assert driver.run.state is RunState.interrupted
    assert driver.run.tick == 2
    assert "phase exploded" in (driver.run.end_reason or "")

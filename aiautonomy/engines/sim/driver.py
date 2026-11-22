"""Wall-clock pacing and playback control on the asyncio loop (plans/R1.md §4.5).

Commands are synchronous, so they are handled (and acknowledged) immediately. `pause` and
`set_speed` take effect at the next tick boundary; `reset` and `cancel` take effect at once:
they cancel a pacing sleep or an in-flight inference wait and roll back a partially run tick.
A tick is synchronous and short; pacing sleeps and inference waits are awaits, so WebSocket
handling never blocks on them.

REQ: SIM-01, SIM-03, SIM-05, END-05
"""

import asyncio
import contextlib
import logging
import math
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from aiautonomy.engines.sim.run import Run
from aiautonomy.engines.sim.status import RunState, Speed, ticks_per_second

log = logging.getLogger(__name__)

MAX_SPEED_BATCH_S = 0.02
"""At max speed the driver runs ticks for at most this long before yielding to the loop."""


class CommandError(Exception):
    """A playback command is not valid in the current state."""


@dataclass(frozen=True, slots=True)
class ArtificialInferenceWait:
    """M0 stand-in for inference: await `wait_ms` before phase 4 of every `every`-th tick."""

    wait_ms: int = 0
    every: int = 1

    def __post_init__(self) -> None:
        if self.wait_ms < 0 or self.every < 1:
            raise ValueError("wait_ms must be >= 0 and every >= 1")

    @property
    def enabled(self) -> bool:
        return self.wait_ms > 0

    def applies(self, tick: int) -> bool:
        return self.enabled and tick % self.every == 0


class Driver:
    """Plays one run: pacing, pause/resume/step/speed/cancel, inference waits."""

    def __init__(
        self,
        run: Run,
        *,
        speed: Speed = Speed.x1,
        inference_wait: ArtificialInferenceWait | None = None,
        on_status: Callable[[], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.run = run
        self.speed = speed
        self.inference_wait = inference_wait or ArtificialInferenceWait()
        self.waiting_for_inference = False
        self._on_status = on_status or (lambda: None)
        self._clock = clock
        self._task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._pause_requested = False
        self._last_tick_at: float | None = None

    # --- commands ---------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def pause_pending(self) -> bool:
        return self._pause_requested

    def start(self) -> None:
        if self.run.state is not RunState.idle:
            raise CommandError(f"cannot start: the run is {self.run.state}")
        self.run.begin()
        self.run.state = RunState.running
        self._spawn(self._play())
        self._on_status()

    def pause(self) -> None:
        if self.run.state is not RunState.running:
            raise CommandError(f"cannot pause: the run is {self.run.state}")
        self._pause_requested = True
        self._wake.set()

    def resume(self) -> None:
        if self.run.state is RunState.running and self._pause_requested:
            self._pause_requested = False
            return
        if self.run.state is not RunState.paused:
            raise CommandError(f"cannot resume: the run is {self.run.state}")
        self.run.state = RunState.running
        if not self.busy:  # a step in flight continues into playback by itself
            self._spawn(self._play())
        self._on_status()

    def step(self) -> None:
        if self.run.state not in (RunState.idle, RunState.paused):
            raise CommandError(f"cannot step: the run is {self.run.state}")
        if self.busy:
            raise CommandError("cannot step: a step is already in progress")
        self.run.begin()
        self.run.state = RunState.paused
        self._spawn(self._step())
        self._on_status()

    def set_speed(self, speed: Speed) -> None:
        self.speed = speed
        self._wake.set()
        self._on_status()

    def cancel(self, reason: str = "cancelled by the user") -> None:
        """End a started run as interrupted (END-05), at once."""
        if self.run.state not in (RunState.running, RunState.paused):
            raise CommandError(f"cannot cancel: the run is {self.run.state}")
        self._halt()
        self.run.finish(RunState.interrupted, reason)
        self._on_status()

    def abandon(self, reason: str) -> bool:
        """Stop at once (reset, shutdown). A started, unfinished run ends as interrupted."""
        self._halt()
        if self.run.started and not self.run.state.terminal:
            self.run.finish(RunState.interrupted, reason)
            return True
        return False

    # --- playback ---------------------------------------------------------------

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._task = task
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task[None]) -> None:
        if self._task is task:
            self._task = None

    def _halt(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
        self.run.abandon_tick()
        self.waiting_for_inference = False
        self._pause_requested = False

    async def _play(self) -> None:
        try:
            await self._play_loop()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._crash(exc)

    async def _step(self) -> None:
        try:
            await self._tick()
            if self.run.state is RunState.running:  # resumed while the step was in flight
                await self._play_loop()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._crash(exc)

    async def _play_loop(self) -> None:
        while self.run.state is RunState.running:
            if self._pause_requested:
                self._pause_requested = False
                self.run.state = RunState.paused
                self._on_status()
                return
            if self.speed is Speed.max:
                deadline = self._clock() + MAX_SPEED_BATCH_S
                while (
                    self.run.state is RunState.running
                    and self.speed is Speed.max
                    and not self._pause_requested
                    and self._clock() < deadline
                ):
                    await self._tick()
                await asyncio.sleep(0)
                continue
            delay = self._next_due() - self._clock()
            if delay > 0:
                await self._sleep(delay)
                continue
            await self._tick()

    def _next_due(self) -> float:
        if self._last_tick_at is None:
            return -math.inf
        rate = ticks_per_second(self.speed, self.run.config.ticks_per_second)
        return self._last_tick_at + 1.0 / rate

    async def _sleep(self, delay: float) -> None:
        """Sleep until the next tick is due or a command wakes the loop."""
        self._wake.clear()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), timeout=delay)

    async def _tick(self) -> None:
        self._last_tick_at = self._clock()
        ctx = self.run.begin_tick()
        if ctx.removal is None and self.inference_wait.applies(ctx.tick):
            self.waiting_for_inference = True
            self._on_status()
            await asyncio.sleep(self.inference_wait.wait_ms / 1000)
            self.waiting_for_inference = False
            self._on_status()
        self.run.complete_tick(ctx)
        if self.run.state.terminal:
            self._on_status()

    def _crash(self, exc: Exception) -> None:
        """An application failure ends the run as interrupted (END-05)."""
        log.exception("tick failed; run %s interrupted", self.run.run_id, exc_info=exc)
        self.waiting_for_inference = False
        self._pause_requested = False
        try:
            self.run.abandon_tick()
            self.run.finish(RunState.interrupted, f"engine error: {exc!r}")
        except Exception:
            log.exception("could not finalize run %s", self.run.run_id)
        self._on_status()

"""Simulation clock: fixed ticks of whole simulated minutes, independent of rendering.

REQ: SIM-01
"""

from dataclasses import dataclass

from aiautonomy.engines.world.state import ClockState

MINUTES_PER_DAY = 1440


@dataclass(frozen=True, slots=True)
class SimClock:
    start_minute_of_day: int
    tick_minutes: int

    def at(self, tick: int) -> ClockState:
        """Clock after `tick` completed ticks (tick 0 is the scenario start, day 1)."""
        total = self.start_minute_of_day + tick * self.tick_minutes
        return ClockState(
            tick=tick, day=1 + total // MINUTES_PER_DAY, minute_of_day=total % MINUTES_PER_DAY
        )

    def seconds_per_tick(self) -> float:
        return float(self.tick_minutes * 60)

"""Run lifecycle states, playback speeds and termination labels.

REQ: SIM-01, END-01, END-05
"""

from enum import StrEnum


class RunState(StrEnum):
    """Lifecycle state of a run. `completed`, `removed` and `interrupted` are terminal."""

    idle = "idle"
    running = "running"
    paused = "paused"
    completed = "completed"
    removed = "removed"
    interrupted = "interrupted"

    @property
    def terminal(self) -> bool:
        return self in TERMINAL_STATES


TERMINAL_STATES = frozenset({RunState.completed, RunState.removed, RunState.interrupted})


class Speed(StrEnum):
    """Playback speed. `max` runs ticks back to back without wall-clock pacing."""

    x1 = "1x"
    x2 = "2x"
    x4 = "4x"
    max = "max"


SPEED_MULTIPLIER: dict[Speed, int] = {Speed.x1: 1, Speed.x2: 2, Speed.x4: 4}


def ticks_per_second(speed: Speed, base_ticks_per_second: float) -> float:
    """Nominal playback rate for `speed`; 0 means unpaced (`max`)."""
    if speed is Speed.max:
        return 0.0
    return base_ticks_per_second * SPEED_MULTIPLIER[speed]

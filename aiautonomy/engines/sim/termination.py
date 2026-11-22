"""Termination labels (plans/R1.md §4.3).

Checked after phase 7, or after phase 3 when a removal succeeded there. Removal takes
precedence over reaching the duration (END-04); nothing else ends a run early (END-02).
Cancellation and application failures end a run as `interrupted` (END-05) outside the tick.

REQ: END-01, END-05
"""

from aiautonomy.engines.sim.status import RunState


def check_termination(tick: int, duration: int, removal: str | None) -> RunState | None:
    """The terminal state reached at the end of `tick`, if any."""
    if removal is not None:
        return RunState.removed
    if tick >= duration:
        return RunState.completed
    return None

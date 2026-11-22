"""Toy metrics for the M0 walking skeleton, computed in phase 7.

REQ: EVAL-04
"""

from aiautonomy.engines.world.state import World


def toy_metrics(world: World) -> dict[str, float]:
    """`distance_walked_km` (cumulative) and `mean_distance_from_center_m` (Manhattan)."""
    walked = 0.0
    spread = 0.0
    for mover_id in sorted(world.movers):
        mover = world.movers[mover_id]
        walked += mover.odometer_m
        spread += abs(mover.x) + abs(mover.y)
    count = len(world.movers)
    return {
        "distance_walked_km": walked / 1000.0,
        "mean_distance_from_center_m": spread / count if count else 0.0,
    }

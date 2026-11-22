"""The M0 toy world: pedestrians walking a small street grid.

Coordinates are meters with x east, y north and the origin at the grid center. Every random
choice comes from the keyed RNG (placement from `population`, kind and speed from
`preferences`, turns from `traffic_background`), and movement uses only + − × ÷, min, max
and abs, so runs are bit-identical across platforms.

REQ: SIM-04
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aiautonomy.engines.core.ids import IdCounters
from aiautonomy.engines.core.rng import KeyedRng
from aiautonomy.engines.world.state import Bounds, ClockState, Mover, Node, World

MAX_HOPS_PER_TICK = 64


class ToyWorldConfig(BaseModel):
    """Scenario parameters of the toy grid."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["toy_grid"] = "toy_grid"
    columns: int = Field(default=7, ge=2, le=64)
    rows: int = Field(default=7, ge=2, le=64)
    block_m: float = Field(default=120.0, gt=0, le=1000)
    movers: int = Field(default=40, ge=0, le=10_000)
    jogger_share_bp: int = Field(default=2500, ge=0, le=10_000)
    walker_speed_mps: tuple[float, float] = (1.0, 1.6)
    jogger_speed_mps: tuple[float, float] = (2.2, 3.0)


@dataclass(frozen=True, slots=True)
class ToyGrid:
    columns: int
    rows: int
    block_m: float

    @classmethod
    def from_config(cls, config: ToyWorldConfig) -> ToyGrid:
        return cls(config.columns, config.rows, config.block_m)

    def node_x(self, ix: int) -> float:
        return (ix - (self.columns - 1) / 2) * self.block_m

    def node_y(self, iy: int) -> float:
        return (iy - (self.rows - 1) / 2) * self.block_m

    def neighbors(self, node: Node) -> tuple[Node, ...]:
        """Adjacent intersections in a fixed order: east, north, west, south."""
        ix, iy = node
        candidates = ((ix + 1, iy), (ix, iy + 1), (ix - 1, iy), (ix, iy - 1))
        return tuple(
            (cx, cy) for cx, cy in candidates if 0 <= cx < self.columns and 0 <= cy < self.rows
        )

    @property
    def bounds(self) -> Bounds:
        half_x = (self.columns - 1) / 2 * self.block_m + self.block_m / 2
        half_y = (self.rows - 1) / 2 * self.block_m + self.block_m / 2
        return Bounds(-half_x, -half_y, half_x, half_y)


def create_toy_world(config: ToyWorldConfig, clock: ClockState, rng: KeyedRng) -> World:
    """Place `config.movers` pedestrians on random street segments."""
    grid = ToyGrid.from_config(config)
    ids = IdCounters()
    movers: dict[str, Mover] = {}
    for _ in range(config.movers):
        mover_id = ids.next_id("mover")
        node = (
            rng.below("population", grid.columns, "column", mover_id),
            rng.below("population", grid.rows, "row", mover_id),
        )
        target = rng.choice("population", grid.neighbors(node), "heading", mover_id)
        along = rng.u01("population", "along", mover_id)
        x = grid.node_x(node[0]) + (grid.node_x(target[0]) - grid.node_x(node[0])) * along
        y = grid.node_y(node[1]) + (grid.node_y(target[1]) - grid.node_y(node[1])) * along
        jogger = rng.chance_bp("preferences", config.jogger_share_bp, "kind", mover_id)
        low, high = config.jogger_speed_mps if jogger else config.walker_speed_mps
        speed = rng.uniform("preferences", low, high, "speed", mover_id)
        movers[mover_id] = Mover(
            id=mover_id,
            kind="jogger" if jogger else "walker",
            x=x,
            y=y,
            speed_mps=speed,
            prev=node,
            target=target,
        )
    return World(clock=clock, ids=ids, movers=movers, metrics={}, bounds=grid.bounds)


def advance_movers(world: World, grid: ToyGrid, rng: KeyedRng, tick: int, seconds: float) -> None:
    """Walk every mover `speed × seconds` meters along the grid, turning at intersections."""
    for mover_id in sorted(world.movers):
        mover = world.movers[mover_id]
        budget = mover.speed_mps * seconds
        walked = 0.0
        hop = 0
        while budget > 0.0 and hop < MAX_HOPS_PER_TICK:
            tx = grid.node_x(mover.target[0])
            ty = grid.node_y(mover.target[1])
            distance = abs(tx - mover.x) + abs(ty - mover.y)
            if distance <= budget:
                mover.x, mover.y = tx, ty
                budget -= distance
                walked += distance
                options = grid.neighbors(mover.target)
                onward = tuple(node for node in options if node != mover.prev) or options
                nxt = rng.choice("traffic_background", onward, tick, mover_id, hop)
                mover.prev, mover.target = mover.target, nxt
                hop += 1
            else:
                if tx != mover.x:
                    mover.x += budget if tx > mover.x else -budget
                else:
                    mover.y += budget if ty > mover.y else -budget
                walked += budget
                budget = 0.0
        mover.odometer_m += walked

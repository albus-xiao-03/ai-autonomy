"""Authoritative World state (M0: the toy world).

Only engine code mutates the World. Entities live in dicts keyed by id and are always
iterated in sorted id order; `to_state()` is the canonical, hashed form and `view()` the
renderable projection sent to the frontend.

REQ: SIM-04, ARCH-01
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from aiautonomy.engines.core.ids import IdCounters

type Node = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Bounds:
    """World extent in meters; x east, y north, origin at the map center."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def to_view(self) -> dict[str, float]:
        return {"min_x": self.min_x, "min_y": self.min_y, "max_x": self.max_x, "max_y": self.max_y}


@dataclass(frozen=True, slots=True)
class ClockState:
    tick: int
    day: int
    minute_of_day: int

    def to_state(self) -> dict[str, int]:
        return {"tick": self.tick, "day": self.day, "minute_of_day": self.minute_of_day}

    @classmethod
    def from_state(cls, state: Mapping[str, int]) -> ClockState:
        return cls(tick=state["tick"], day=state["day"], minute_of_day=state["minute_of_day"])


@dataclass(slots=True)
class Mover:
    """A toy pedestrian walking from node `prev` to node `target` of the street grid."""

    id: str
    kind: str
    x: float
    y: float
    speed_mps: float
    prev: Node
    target: Node
    odometer_m: float = 0.0

    def to_state(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "x": self.x,
            "y": self.y,
            "speed_mps": self.speed_mps,
            "prev": [self.prev[0], self.prev[1]],
            "target": [self.target[0], self.target[1]],
            "odometer_m": self.odometer_m,
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> Mover:
        return cls(
            id=state["id"],
            kind=state["kind"],
            x=state["x"],
            y=state["y"],
            speed_mps=state["speed_mps"],
            prev=(state["prev"][0], state["prev"][1]),
            target=(state["target"][0], state["target"][1]),
            odometer_m=state["odometer_m"],
        )

    def view(self) -> dict[str, Any]:
        return {"id": self.id, "x": self.x, "y": self.y, "kind": self.kind}


@dataclass(slots=True)
class World:
    """The authoritative state of one run. `bounds` is static and not part of the hash."""

    COLLECTIONS: ClassVar[tuple[str, ...]] = ("movers",)

    clock: ClockState
    ids: IdCounters
    movers: dict[str, Mover]
    metrics: dict[str, float]
    bounds: Bounds

    def to_state(self) -> dict[str, Any]:
        """Canonical state: one top-level key per subsystem (the replay divergence unit)."""
        return {
            "clock": self.clock.to_state(),
            "ids": self.ids.to_state(),
            "movers": {mid: self.movers[mid].to_state() for mid in sorted(self.movers)},
            "metrics": {name: self.metrics[name] for name in sorted(self.metrics)},
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any], bounds: Bounds) -> World:
        return cls(
            clock=ClockState.from_state(state["clock"]),
            ids=IdCounters.from_state(state["ids"]),
            movers={mid: Mover.from_state(m) for mid, m in sorted(state["movers"].items())},
            metrics=dict(state["metrics"]),
            bounds=bounds,
        )

    def view(self) -> dict[str, Any]:
        """Renderable projection matching the protocol's `WorldView`."""
        return {
            "clock": self.clock.to_state(),
            "bounds": self.bounds.to_view(),
            "movers": {mid: self.movers[mid].view() for mid in sorted(self.movers)},
        }


def find_entity(state: Mapping[str, Any], entity_id: str) -> dict[str, Any] | None:
    """Look up an entity by id in the collections of a canonical state."""
    for collection in World.COLLECTIONS:
        entity = state.get(collection, {}).get(entity_id)
        if entity is not None:
            return dict(entity)
    return None

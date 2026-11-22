"""Deterministic per-type id counters (docs/engine-plan.md §4.2: ids never come from uuid4).

Counters live in the World state, so allocated ids are part of the hashed state and replay
allocates the same ids. Zero-padded numbers make sorted id order equal allocation order.

REQ: SIM-04
"""

import re
from collections.abc import Mapping

ID_DIGITS = 6
_PREFIX = re.compile(r"^[a-z][a-z0-9_]*$")


def format_id(prefix: str, number: int) -> str:
    """Return the id for the `number`-th entity of type `prefix`, e.g. `mover-000001`."""
    return f"{prefix}-{number:0{ID_DIGITS}d}"


def _check_prefix(prefix: str) -> None:
    if not _PREFIX.match(prefix):
        raise ValueError(f"invalid id prefix {prefix!r}")


class IdCounters:
    """Per-type counters; `next_id("mover")` returns `mover-000001`, then `mover-000002`."""

    __slots__ = ("_counters",)

    def __init__(self, counters: Mapping[str, int] | None = None) -> None:
        self._counters: dict[str, int] = {}
        for prefix, value in (counters or {}).items():
            _check_prefix(prefix)
            if value < 0:
                raise ValueError(f"negative counter for {prefix!r}")
            self._counters[prefix] = value

    def next_id(self, prefix: str) -> str:
        _check_prefix(prefix)
        number = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = number
        return format_id(prefix, number)

    def count(self, prefix: str) -> int:
        """Number of ids allocated so far for `prefix`."""
        return self._counters.get(prefix, 0)

    def to_state(self) -> dict[str, int]:
        return {prefix: self._counters[prefix] for prefix in sorted(self._counters)}

    @classmethod
    def from_state(cls, state: Mapping[str, int]) -> IdCounters:
        return cls(state)

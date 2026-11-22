"""Canonical JSON and blake2b state hashes (docs/engine-plan.md §4.2).

Canonical JSON: sorted keys, no whitespace, floats via `repr` (the json module's float
encoding), NaN and infinities rejected, non-JSON types rejected. The state hash covers every
top-level subsystem except `run_id`; per-subsystem hashes let replay name the subsystem that
diverged first.

REQ: SIM-04, EVAL-04
"""

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

EXCLUDED_KEYS = frozenset({"run_id"})
"""Top-level keys never hashed: the run id is wall-clock derived."""

HASH_DIGEST_SIZE = 32


def _reject(value: object) -> object:
    raise TypeError(f"not canonical JSON: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize `value` to canonical JSON text."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_reject,
    )


def check_canonical(value: Any, path: str = "$") -> None:
    """Raise TypeError or ValueError if `value` is not plain canonical-JSON data.

    `canonical_json` already rejects unknown types and NaN; this also rejects non-string
    keys (which json would silently convert) and sets. Used by tests and loaders, not per tick.
    """
    if value is None or isinstance(value, bool | int | str):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path}: non-finite float")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path}: non-string key {key!r}")
            check_canonical(item, f"{path}.{key}")
        return
    if isinstance(value, list | tuple):
        for index, item in enumerate(value):
            check_canonical(item, f"{path}[{index}]")
        return
    raise TypeError(f"{path}: not canonical JSON: {type(value).__name__}")


def blake2b_hex(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=HASH_DIGEST_SIZE).hexdigest()


@dataclass(frozen=True, slots=True)
class StateHash:
    """Hash of the whole state plus one hash per top-level subsystem."""

    value: str
    subsystems: Mapping[str, str]


def hash_state(state: Mapping[str, Any]) -> StateHash:
    """Hash canonical JSON of `state` (minus excluded keys) and of each subsystem.

    The whole-state hash is computed over exactly `canonical_json(state)`; the document is
    assembled from the per-subsystem texts so each subsystem is serialized only once.
    """
    parts = {key: canonical_json(state[key]) for key in sorted(state) if key not in EXCLUDED_KEYS}
    document = (
        "{"
        + ",".join(f"{json.dumps(key, ensure_ascii=False)}:{text}" for key, text in parts.items())
        + "}"
    )
    return StateHash(
        value=blake2b_hex(document.encode("utf-8")),
        subsystems={key: blake2b_hex(text.encode("utf-8")) for key, text in parts.items()},
    )

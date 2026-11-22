"""Keyed randomness (docs/engine-plan.md §4.2).

`u01(stream, *key)` takes the first 8 bytes of `blake2b(stream_seed ‖ key)` (default 64-byte
digest; the seed as 8 big-endian bytes, the key as compact JSON) and maps their top 53 bits
to a uniform float in [0, 1). A draw depends only on its stream seed and key, never on how
many other draws happened, so endogenous behavior cannot shift external randomness.

Each stream has its own seed, derived from the run seed unless overridden; the manifest
records every stream seed and replay uses the recorded values.

REQ: SIM-04
"""

import hashlib
import json
from collections.abc import Mapping, Sequence

STREAMS: tuple[str, ...] = (
    "population",
    "mode_assignment",
    "schedules",
    "preferences",
    "external_events",
    "event_effects",
    "medical_demand",
    "fire",
    "traffic_background",
    "services",
    "politics",
    "model_sampling",
)
"""The twelve named streams. Only the event system reads the external-event streams."""

EXTERNAL_EVENT_STREAMS = frozenset({"external_events", "event_effects"})

SEED_BYTES = 8
_SEED_DOMAIN = b"aiautonomy/stream-seed/v1"
_MANTISSA_BITS = 53
_TO_UNIT = 2.0**-_MANTISSA_BITS

type KeyPart = int | str


def _check_stream(stream: str) -> None:
    if stream not in STREAMS:
        raise KeyError(f"unknown RNG stream {stream!r}")


def _check_seed(seed: int) -> None:
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2 ** (8 * SEED_BYTES):
        raise ValueError(f"seed must be an integer in [0, 2**64): {seed!r}")


def derive_stream_seed(run_seed: int, stream: str) -> int:
    """Derive the 64-bit seed of `stream` from the run seed."""
    _check_stream(stream)
    if isinstance(run_seed, bool) or not isinstance(run_seed, int) or run_seed < 0:
        raise ValueError(f"run seed must be a non-negative integer: {run_seed!r}")
    payload = b"\x00".join((_SEED_DOMAIN, str(run_seed).encode(), stream.encode()))
    return int.from_bytes(hashlib.blake2b(payload).digest()[:SEED_BYTES], "big")


def derive_stream_seeds(
    run_seed: int, overrides: Mapping[str, int] | None = None
) -> dict[str, int]:
    """Return every stream's seed: the override when given, else derived from `run_seed`."""
    overrides = overrides or {}
    for stream, seed in overrides.items():
        _check_stream(stream)
        _check_seed(seed)
    return {
        stream: overrides[stream] if stream in overrides else derive_stream_seed(run_seed, stream)
        for stream in STREAMS
    }


def encode_key(key: Sequence[KeyPart]) -> bytes:
    """Unambiguous byte encoding of a key: compact JSON of its int and str parts."""
    for part in key:
        if isinstance(part, bool) or not isinstance(part, int | str):
            raise TypeError(f"RNG key parts must be int or str, got {type(part).__name__}")
    return json.dumps(list(key), separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class KeyedRng:
    """Stateless keyed draws over the twelve recorded streams."""

    __slots__ = ("_prefixes", "_seeds")

    def __init__(self, stream_seeds: Mapping[str, int]) -> None:
        missing = [stream for stream in STREAMS if stream not in stream_seeds]
        unknown = sorted(stream for stream in stream_seeds if stream not in STREAMS)
        if missing or unknown:
            raise ValueError(f"stream seeds: missing {missing}, unknown {unknown}")
        for seed in stream_seeds.values():
            _check_seed(seed)
        self._seeds = {stream: stream_seeds[stream] for stream in STREAMS}
        self._prefixes = {
            stream: seed.to_bytes(SEED_BYTES, "big") for stream, seed in self._seeds.items()
        }

    @classmethod
    def from_run_seed(cls, run_seed: int, overrides: Mapping[str, int] | None = None) -> KeyedRng:
        return cls(derive_stream_seeds(run_seed, overrides))

    @property
    def seeds(self) -> dict[str, int]:
        return dict(self._seeds)

    def _bits53(self, stream: str, key: Sequence[KeyPart]) -> int:
        prefix = self._prefixes.get(stream)
        if prefix is None:
            raise KeyError(f"unknown RNG stream {stream!r}")
        first8 = hashlib.blake2b(prefix + encode_key(key)).digest()[:8]
        return int.from_bytes(first8, "big") >> (64 - _MANTISSA_BITS)

    def u01(self, stream: str, *key: KeyPart) -> float:
        """Uniform float in [0, 1) for `key` on `stream`."""
        return self._bits53(stream, key) * _TO_UNIT

    def below(self, stream: str, n: int, *key: KeyPart) -> int:
        """Uniform integer in [0, n), computed with exact integer arithmetic."""
        if n <= 0:
            raise ValueError("n must be positive")
        return (self._bits53(stream, key) * n) >> _MANTISSA_BITS

    def chance_bp(self, stream: str, probability_bp: int, *key: KeyPart) -> bool:
        """True with probability `probability_bp` / 10000."""
        return self.below(stream, 10_000, *key) < probability_bp

    def uniform(self, stream: str, low: float, high: float, *key: KeyPart) -> float:
        """Uniform float in [low, high)."""
        return low + (high - low) * self.u01(stream, *key)

    def choice[T](self, stream: str, options: Sequence[T], *key: KeyPart) -> T:
        """One element of `options`, uniformly."""
        return options[self.below(stream, len(options), *key)]

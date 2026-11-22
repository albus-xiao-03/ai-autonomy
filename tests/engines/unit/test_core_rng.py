import hashlib
import json

import pytest

from aiautonomy.engines.core.rng import (
    STREAMS,
    KeyedRng,
    derive_stream_seed,
    derive_stream_seeds,
    encode_key,
)

pytestmark = pytest.mark.req("SIM-04")


def test_the_twelve_named_streams() -> None:
    assert STREAMS == (
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


def test_u01_is_the_first_8_bytes_of_blake2b_of_seed_and_key() -> None:
    seeds = derive_stream_seeds(7)
    rng = KeyedRng(seeds)
    data = seeds["fire"].to_bytes(8, "big") + json.dumps([3, "r-1"], separators=(",", ":")).encode()
    first8 = hashlib.blake2b(data).digest()[:8]
    assert rng.u01("fire", 3, "r-1") == (int.from_bytes(first8, "big") >> 11) / 2**53


def test_draws_are_pinned_across_platforms() -> None:
    # Fixed expected values guard the derivation against accidental change (bit-identical
    # on macOS and Linux, docs/engine-plan.md §4.2).
    rng = KeyedRng.from_run_seed(1)
    assert derive_stream_seed(1, "population") == 11330381679698016143
    assert rng.u01("population", "column", "mover-000001") == 0.1570459624389139
    assert rng.below("population", 1_000_000, "pin") == 563873


def test_a_draw_depends_only_on_its_key() -> None:
    busy, quiet = KeyedRng.from_run_seed(5), KeyedRng.from_run_seed(5)
    for index in range(500):
        busy.u01("medical_demand", index, "other")
        busy.u01("fire", index)
    assert busy.u01("medical_demand", 10, "res-000001") == quiet.u01(
        "medical_demand", 10, "res-000001"
    )


def test_streams_and_keys_are_independent() -> None:
    rng = KeyedRng.from_run_seed(5)
    assert len(set(rng.seeds.values())) == len(STREAMS)
    assert rng.u01("fire", 1) != rng.u01("services", 1)
    assert rng.u01("fire", 1) != rng.u01("fire", 2)
    assert rng.u01("fire", 1, 2) != rng.u01("fire", 12)
    assert KeyedRng.from_run_seed(6).u01("fire", 1) != rng.u01("fire", 1)


def test_overrides_replace_single_streams() -> None:
    seeds = derive_stream_seeds(1, {"fire": 42})
    assert seeds["fire"] == 42
    assert seeds["population"] == derive_stream_seed(1, "population")


def test_helpers_stay_in_range() -> None:
    rng = KeyedRng.from_run_seed(3)
    buckets = [0] * 10
    for index in range(5000):
        value = rng.u01("schedules", index)
        assert 0.0 <= value < 1.0
        buckets[rng.below("schedules", 10, "b", index)] += 1
        assert 2.0 <= rng.uniform("preferences", 2.0, 3.0, index) < 3.0
    assert min(buckets) > 400
    assert rng.choice("politics", ["a", "b", "c"], 1) in {"a", "b", "c"}
    assert rng.chance_bp("politics", 10_000, 1) is True
    assert rng.chance_bp("politics", 0, 1) is False


@pytest.mark.parametrize("bad", [1.5, True, None, (1, 2)])
def test_rejects_non_int_or_str_key_parts(bad: object) -> None:
    with pytest.raises(TypeError):
        encode_key([bad])  # type: ignore[list-item]


def test_rejects_unknown_streams_and_bad_seeds() -> None:
    with pytest.raises(KeyError):
        KeyedRng.from_run_seed(1).u01("weather", 1)
    with pytest.raises(KeyError):
        derive_stream_seeds(1, {"weather": 1})
    with pytest.raises(ValueError, match="seed"):
        derive_stream_seeds(1, {"fire": -1})
    with pytest.raises(ValueError, match="missing"):
        KeyedRng({"fire": 1})

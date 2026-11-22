import hashlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from aiautonomy.engines.core.canonical import canonical_json, hash_state
from aiautonomy.engines.core.money import allocate, format_cents, parse_dollars
from aiautonomy.engines.core.rng import STREAMS, KeyedRng
from aiautonomy.engines.sim.changes import coalesce, diff_views

pytestmark = pytest.mark.req("SIM-04")

key_parts = st.lists(st.one_of(st.integers(), st.text(max_size=12)), max_size=4)
json_leaf = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=8),
)
json_value = st.recursive(
    json_leaf,
    lambda inner: (
        st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=6), inner, max_size=4)
    ),
    max_leaves=20,
)


@given(seed=st.integers(min_value=0, max_value=2**53 - 1), key=key_parts, n=st.integers(1, 10**9))
def test_draws_are_in_range_and_reproducible(seed: int, key: list[int | str], n: int) -> None:
    rng = KeyedRng.from_run_seed(seed)
    for stream in STREAMS:
        value = rng.u01(stream, *key)
        assert 0.0 <= value < 1.0
        assert value == KeyedRng.from_run_seed(seed).u01(stream, *key)
        assert 0 <= rng.below(stream, n, *key) < n


@given(st.dictionaries(st.text(max_size=6), json_value, max_size=6))
def test_canonical_json_ignores_insertion_order(value: dict[str, object]) -> None:
    reordered = dict(reversed(list(value.items())))
    assert canonical_json(reordered) == canonical_json(value)
    digest = hash_state(value)
    without_run_id = {k: v for k, v in value.items() if k != "run_id"}
    expected = hashlib.blake2b(canonical_json(without_run_id).encode(), digest_size=32).hexdigest()
    assert digest.value == expected


@given(st.integers(min_value=-(10**15), max_value=10**15))
def test_money_format_parse_round_trip(cents: int) -> None:
    assert parse_dollars(format_cents(cents)) == cents


@given(
    st.integers(min_value=-(10**12), max_value=10**12),
    st.lists(st.integers(min_value=0, max_value=10**6), min_size=1, max_size=8).filter(any),
)
def test_allocate_conserves_cents(amount: int, weights: list[int]) -> None:
    shares = allocate(amount, weights)
    assert sum(shares) == amount
    assert all(share == 0 for share, weight in zip(shares, weights, strict=True) if weight == 0)


views = st.dictionaries(
    st.sampled_from(["m-1", "m-2", "m-3", "m-4"]),
    st.fixed_dictionaries({"x": st.integers(-5, 5), "kind": st.sampled_from(["a", "b"])}),
)


@given(st.lists(views, min_size=1, max_size=5), st.integers(0, 3))
def test_coalesced_diffs_rebuild_the_final_view(
    sequence: list[dict[str, object]], tick: int
) -> None:
    before = {"clock": {"tick": 0}, "movers": {}}
    current = before
    pending: dict[tuple[str, ...], dict[str, object]] = {}
    for index, movers in enumerate(sequence, start=1):
        after = {"clock": {"tick": index + tick}, "movers": movers}
        coalesce(pending, diff_views(current, after, ["movers"]))
        current = after
    rebuilt = {"clock": dict(before["clock"]), "movers": {}}
    for change in pending.values():
        if change["op"] == "set":
            rebuilt[str(change["field"])] = change["value"]
        elif change["op"] == "upsert":
            rebuilt["movers"][change["id"]] = change["value"]  # type: ignore[index]
        else:
            rebuilt["movers"].pop(change["id"], None)  # type: ignore[attr-defined]
    assert rebuilt == current

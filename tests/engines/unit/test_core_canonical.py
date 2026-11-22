import hashlib
import math

import pytest

from aiautonomy.engines.core.canonical import canonical_json, check_canonical, hash_state

pytestmark = pytest.mark.req("SIM-04")


def test_sorted_keys_no_whitespace_floats_via_repr() -> None:
    value = {"b": [1, 2.0, 0.1, 1e-7, -0.0], "a": {"z": None, "y": True}, "é": "ü"}
    assert canonical_json(value) == ('{"a":{"y":true,"z":null},"b":[1,2.0,0.1,1e-07,-0.0],"é":"ü"}')
    assert canonical_json(0.1 + 0.2) == repr(0.1 + 0.2)


@pytest.mark.parametrize("bad", [math.nan, math.inf, {1, 2}, object()])
def test_rejects_non_canonical_values(bad: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        canonical_json({"x": bad})


def test_check_canonical_rejects_non_string_keys_and_sets() -> None:
    check_canonical({"a": [1, 2.5, "x", None, {"b": False}]})
    with pytest.raises(TypeError):
        check_canonical({1: "a"})
    with pytest.raises(TypeError):
        check_canonical({"a": {1, 2}})
    with pytest.raises(ValueError, match="non-finite"):
        check_canonical({"a": math.nan})


@pytest.mark.req("EVAL-04")
def test_state_hash_is_blake2b_of_canonical_json_and_excludes_run_id() -> None:
    state = {"movers": {"m-1": {"x": 1.5}}, "clock": {"tick": 3}}
    digest = hash_state(state)
    expected = hashlib.blake2b(canonical_json(state).encode(), digest_size=32).hexdigest()
    assert digest.value == expected
    assert hash_state({**state, "run_id": "anything"}) == digest
    assert set(digest.subsystems) == {"clock", "movers"}
    assert digest.subsystems["movers"] == (
        hashlib.blake2b(canonical_json(state["movers"]).encode(), digest_size=32).hexdigest()
    )


def test_hash_changes_with_any_subsystem() -> None:
    base = hash_state({"a": 1, "b": [1.0]})
    changed = hash_state({"a": 1, "b": [1.0000000000000002]})
    assert base.value != changed.value
    assert base.subsystems["a"] == changed.subsystems["a"]
    assert base.subsystems["b"] != changed.subsystems["b"]

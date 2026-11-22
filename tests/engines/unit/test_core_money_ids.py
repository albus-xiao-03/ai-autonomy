import pytest

from aiautonomy.engines.core.ids import IdCounters, format_id
from aiautonomy.engines.core.money import allocate, apply_bp, format_cents, parse_dollars

pytestmark = pytest.mark.req("SIM-04")


@pytest.mark.parametrize(
    ("text", "cents"),
    [("12", 1200), ("12.3", 1230), ("12.34", 1234), ("-0.05", -5), ("$1,234.56", 123456)],
)
def test_parse_dollars_is_exact(text: str, cents: int) -> None:
    assert parse_dollars(text) == cents


@pytest.mark.parametrize("text", ["1.234", "abc", "", "1e3", "--1"])
def test_parse_dollars_rejects_invalid(text: str) -> None:
    with pytest.raises(ValueError, match="not a dollar amount"):
        parse_dollars(text)


def test_format_cents() -> None:
    assert format_cents(123456) == "$1,234.56"
    assert format_cents(-5) == "-$0.05"
    assert format_cents(0) == "$0.00"


def test_apply_bp_rounds_half_up_like_the_population_rule() -> None:
    # plans/R1.md §4.2: llm_count = (population × ratio_bp + 5000) // 10000
    assert apply_bp(101, 5000) == 51
    assert apply_bp(100, 5000) == 50
    assert apply_bp(3, 1667) == 1
    assert apply_bp(-101, 5000) == -51
    for population in range(0, 300, 7):
        for ratio in (0, 1, 3333, 5000, 9999, 10_000):
            assert apply_bp(population, ratio) == (population * ratio + 5000) // 10_000


def test_allocate_preserves_every_cent_deterministically() -> None:
    assert allocate(100, [1, 1, 1]) == [34, 33, 33]
    assert allocate(-100, [1, 1, 1]) == [-34, -33, -33]
    assert allocate(7, [0, 2, 1]) == [0, 5, 2]
    with pytest.raises(ValueError, match="weights"):
        allocate(10, [0, 0])


def test_id_counters_are_per_type_and_sortable() -> None:
    ids = IdCounters()
    assert [ids.next_id("mover") for _ in range(3)] == [
        "mover-000001",
        "mover-000002",
        "mover-000003",
    ]
    assert ids.next_id("project") == "project-000001"
    assert ids.to_state() == {"mover": 3, "project": 1}
    restored = IdCounters.from_state(ids.to_state())
    assert restored.next_id("mover") == "mover-000004"
    assert sorted([format_id("m", 10), format_id("m", 9)]) == ["m-000009", "m-000010"]
    with pytest.raises(ValueError, match="invalid id prefix"):
        ids.next_id("Bad Prefix")

"""Seeded LLM-resident assignment (RES-06): exact counts, nesting, seeding and top-ups."""

import pytest

from aiautonomy.engines.core.money import apply_bp
from aiautonomy.engines.core.rng import KeyedRng
from aiautonomy.engines.hybrid.residents import assign_llm, top_up
from aiautonomy.engines.sim.config import RunOverrides, resolve_run_config


@pytest.mark.req("RES-06")
def test_six_residents_at_half_give_exactly_three() -> None:
    config = resolve_run_config(
        RunOverrides(scenario="boston", population=6, llm_ratio_bp=5000)
    ).config
    assert config.llm_count == 3
    chosen = assign_llm(config.population, config.llm_count, KeyedRng.from_run_seed(config.seed))
    assert len(chosen) == 3
    assert chosen == sorted(set(chosen))
    assert set(chosen) <= set(range(6))


@pytest.mark.req("RES-06")
@pytest.mark.parametrize("population", [0, 1, 6, 7, 100, 333])
def test_counts_round_half_up_and_sets_nest(population: int) -> None:
    rng = KeyedRng.from_run_seed(11)
    previous: set[int] = set()
    for ratio_bp in (0, 1, 1667, 2500, 5000, 7500, 9999, 10_000):
        count = apply_bp(population, ratio_bp)
        assert count == (population * ratio_bp + 5000) // 10_000
        chosen = set(assign_llm(population, count, rng))
        assert len(chosen) == count
        assert previous <= chosen  # a higher ratio's LLM set contains every lower one
        previous = chosen
    assert previous == set(range(population))


@pytest.mark.req("RES-06")
def test_assignment_is_seeded() -> None:
    same = [assign_llm(100, 50, KeyedRng.from_run_seed(5)) for _ in range(2)]
    assert same[0] == same[1]
    other = assign_llm(100, 50, KeyedRng.from_run_seed(6))
    assert other != same[0]
    assert len(other) == 50


@pytest.mark.req("RES-06")
def test_top_up_reaches_the_new_target_without_changing_existing_residents() -> None:
    rng = KeyedRng.from_run_seed(3)
    before = assign_llm(6, 3, rng)
    added = top_up(6, len(before), list(range(6, 12)), 5000, rng)
    assert len(before) + len(added) == apply_bp(12, 5000) == 6
    assert set(added) <= set(range(6, 12))
    assert top_up(12, 6, [12], 5000, rng) == [12]  # 13 residents at half: 7 LLM
    assert top_up(6, 3, [], 5000, rng) == []

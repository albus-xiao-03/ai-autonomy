"""Seeded LLM-resident assignment (RES-06).

At launch the LLM residents are exactly `RunConfig.llm_count` (= (population × ratio_bp + 5000)
// 10000) residents: those with the lowest `mode_assignment` draws, ties broken by id. A draw
depends only on the resident id and the stream seed, so the LLM set of a higher ratio contains
the set of every lower ratio, and routine-only and mixed runs share the same residents.

Residents who join mid-run (a new household) are topped up to the exact target for the new
population, choosing among the newcomers only; existing residents never change mode.

REQ: RES-06
"""

from collections.abc import Iterable

from aiautonomy.engines.core.money import apply_bp
from aiautonomy.engines.core.rng import KeyedRng

STREAM = "mode_assignment"


def _ranked(resident_ids: Iterable[int], rng: KeyedRng) -> list[int]:
    return sorted(resident_ids, key=lambda rid: (rng.u01(STREAM, rid), rid))


def assign_llm(population: int, llm_count: int, rng: KeyedRng) -> list[int]:
    """The LLM residents among ids 0 … population-1, sorted by id."""
    if not 0 <= llm_count <= population:
        raise ValueError(f"llm_count {llm_count} outside 0..{population}")
    return sorted(_ranked(range(population), rng)[:llm_count])


def top_up(
    population_before: int, llm_before: int, joined: list[int], ratio_bp: int, rng: KeyedRng
) -> list[int]:
    """New LLM ids among `joined`, so the LLM count reaches the target of the new population."""
    target = apply_bp(population_before + len(joined), ratio_bp)
    need = max(0, target - llm_before)
    return sorted(_ranked(joined, rng)[:need])

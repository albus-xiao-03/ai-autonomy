"""Integer-cent money and basis-point arithmetic (docs/engine-plan.md §4.2: money is never a float).

REQ: SIM-04
"""

import re
from collections.abc import Sequence

type Cents = int

CENTS_PER_DOLLAR = 100
BP_SCALE = 10_000

_AMOUNT = re.compile(r"^(-)?\$?(\d{1,15})(?:\.(\d{1,2}))?$")


def parse_dollars(text: str) -> Cents:
    """Parse `"1234.5"`, `"-$0.05"` or `"12"` exactly into cents; at most two decimals."""
    match = _AMOUNT.match(text.strip().replace(",", ""))
    if match is None:
        raise ValueError(f"not a dollar amount: {text!r}")
    sign, whole, frac = match.groups()
    cents = int(whole) * CENTS_PER_DOLLAR + int((frac or "0").ljust(2, "0"))
    return -cents if sign else cents


def format_cents(amount: Cents) -> str:
    """Format cents for display, e.g. `-$1,234.56`."""
    sign = "-" if amount < 0 else ""
    whole, frac = divmod(abs(amount), CENTS_PER_DOLLAR)
    return f"{sign}${whole:,}.{frac:02d}"


def apply_bp(amount: int, bp: int) -> int:
    """`amount × bp / 10000`, rounded half away from zero, in exact integer arithmetic.

    For non-negative amounts this is `(amount × bp + 5000) // 10000`, the rounding
    docs/engine-plan.md §4.2 fixes for the LLM population share (halves round up, unlike
    banker's `round`).
    """
    if bp < 0:
        raise ValueError("bp must be non-negative")
    magnitude = (abs(amount) * bp + BP_SCALE // 2) // BP_SCALE
    return -magnitude if amount < 0 else magnitude


def allocate(amount: Cents, weights: Sequence[int]) -> list[Cents]:
    """Split `amount` in proportion to non-negative integer `weights` without losing a cent.

    Largest-remainder method; ties go to the earlier index, so the result is deterministic.
    """
    if not weights or any(weight < 0 for weight in weights) or sum(weights) == 0:
        raise ValueError("weights must be non-negative with a positive sum")
    total = sum(weights)
    sign = -1 if amount < 0 else 1
    magnitude = abs(amount)
    shares = [magnitude * weight // total for weight in weights]
    remainders = [magnitude * weight % total for weight in weights]
    leftover = magnitude - sum(shares)
    order = sorted(range(len(weights)), key=lambda index: (-remainders[index], index))
    for index in order[:leftover]:
        shares[index] += 1
    return [sign * share for share in shares]

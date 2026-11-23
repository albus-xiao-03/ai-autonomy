"""Mayor decisions and exceptional orders in a hybrid run: state, options, observation, cost.

- Options are derived from the recorded state at the observation tick: for each served
  incident and department, `dispatch(n)` when n available units have a reported route, and
  `prioritize` when that department's demand is waiting; `HOLD` is always offered. No option
  can site, move or remove a facility.
- The observation holds public, current facts only: no planned or future disruption.
- An accepted order costs authority only beyond the rolling allowance. A repeat of the same
  order key in the window is not distinct and costs nothing; one order counts once however
  many units it sends.

REQ: MAY-02, MAY-03, MAY-04, MAY-05, POL-01, POL-07, CITY-03
"""

import hashlib
from collections.abc import Iterable
from typing import Any

from aiautonomy.engines.contract.decisions import ActionOption, OrderAuthority
from aiautonomy.engines.core.canonical import canonical_json
from aiautonomy.engines.hybrid.catalogs import DispatchCatalog, OrderRules
from aiautonomy.engines.hybrid.decisions import Order
from aiautonomy.engines.hybrid.dispatch import ORDERED_DEPARTMENTS, SERVED_STATUSES, RouteTable
from aiautonomy.engines.hybrid.state import HybridState

MAX_OPTIONS = 12
MAX_UNITS_PER_ORDER = 3


def _label(kind: str, catalog: DispatchCatalog) -> str:
    return catalog.spec(kind).label


def derive_options(
    state: HybridState, catalog: DispatchCatalog, routes: RouteTable, tick: int
) -> list[ActionOption]:
    """Permitted actions from the recorded incidents, units and routes of `tick`."""
    found: list[ActionOption] = []
    incidents = sorted(
        (i for i in state.incidents.values() if i.status in SERVED_STATUSES),
        key=lambda i: (-i.severity, i.opened_tick, i.id),
    )
    for incident in incidents:
        label = f"{_label(incident.kind, catalog)} {incident.id} (severity {incident.severity})"
        for department in ORDERED_DEPARTMENTS:
            reachable = sum(
                1
                for unit in state.units.values()
                if unit.department == department
                and unit.available
                and routes.get((unit.id, incident.id)) is not None
            )
            for units in range(1, min(reachable, MAX_UNITS_PER_ORDER) + 1):
                noun = "unit" if units == 1 else "units"
                found.append(
                    ActionOption(
                        id="A0",
                        kind="dispatch",
                        department=department,
                        incident_id=incident.id,
                        units=units,
                        summary=f"Send {units} {department} {noun} to {label}",
                    )
                )
            waiting = department in incident.queue_since
            prioritized = incident.priority_until.get(department, -1) >= tick
            if waiting and not prioritized:
                found.append(
                    ActionOption(
                        id="A0",
                        kind="prioritize",
                        department=department,
                        incident_id=incident.id,
                        summary=f"Prioritize {label} for the {department} department",
                    )
                )
    options = [
        option.model_copy(update={"id": f"A{index}"})
        for index, option in enumerate(found[:MAX_OPTIONS], start=1)
    ]
    options.append(ActionOption(id="HOLD", kind="hold", summary="Keep standing procedures"))
    return options


def orders_in_window(orders: Iterable[Order], tick: int, window: int) -> list[Order]:
    return [
        order
        for order in orders
        if order.status == "accepted" and tick - window < order.applied_tick <= tick
    ]


def order_cost(
    orders: Iterable[Order], rules: OrderRules, key: str, tick: int, before: int
) -> OrderAuthority:
    """The authority effect of accepting an order with `key` at `tick`."""
    recent = orders_in_window(orders, tick, rules.window_ticks)
    keys = {order.key for order in recent}
    counted = key not in keys
    count = len(keys) + (1 if counted else 0)
    penalty = rules.penalty if counted and count > rules.allowance else 0
    return OrderAuthority(
        counted=counted,
        distinct_key=key,
        window_ticks=rules.window_ticks,
        window_count=count,
        allowance=rules.allowance,
        penalty=penalty,
        before=before,
        after=max(0, before - penalty),
    )


def observation_id(observation: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(observation).encode("utf-8")).hexdigest()

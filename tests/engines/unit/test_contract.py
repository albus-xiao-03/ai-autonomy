"""The hybrid engine–game contract: examples, invariants and schema export (docs/contract.md)."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from aiautonomy.engines.api.export_schema import build_schema
from aiautonomy.engines.contract.common import CONTROLLER_DISPLAY, ErrorResponse
from aiautonomy.engines.contract.decisions import (
    AuthorityChange,
    DecisionEnvelope,
    MayorDecisionRecord,
    MayorProposal,
    OrderRecord,
)
from aiautonomy.engines.contract.disruptions import DISRUPTION_TYPES, DisruptionSpec
from aiautonomy.engines.contract.runs import RouteObservation, TickObservation, TickOutcome
from aiautonomy.engines.core.paths import repo_root

EXAMPLES = repo_root() / "docs" / "contract" / "examples"
EXAMPLE_TYPES: dict[str, type[BaseModel]] = {
    "TickObservation": TickObservation,
    "TickOutcome": TickOutcome,
    "MayorDecisionRecord": MayorDecisionRecord,
    "OrderRecord": OrderRecord,
    "AuthorityChange": AuthorityChange,
}
REQUIRED_EXAMPLES = {
    "incident-observation",
    "route-availability",
    "routine-dispatch",
    "direct-mayoral-order",
    "queue",
    "authority-change",
    "recorded-outcome",
}


def _example_files() -> list[Path]:
    return sorted(EXAMPLES.glob("*.json"))


def test_every_required_example_exists() -> None:
    assert {path.stem for path in _example_files()} >= REQUIRED_EXAMPLES


@pytest.mark.req("ARCH-02", "ARCH-03")
@pytest.mark.parametrize("path", _example_files(), ids=lambda path: path.stem)
def test_examples_validate_and_show_every_field(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert set(document) == {"description", "examples"}
    assert document["description"]
    assert document["examples"]
    for example in document["examples"]:
        model = EXAMPLE_TYPES[example["type"]]
        value: dict[str, Any] = example["value"]
        parsed = model.model_validate(value)
        # Complete and canonical: no omitted defaults, nothing the model would change.
        assert parsed.model_dump(mode="json") == value


@pytest.mark.req("EVT-01")
def test_exactly_seven_disruption_types() -> None:
    assert DISRUPTION_TYPES == (
        "traffic",
        "outage",
        "gas_leakage",
        "flood",
        "storm",
        "snowstorm",
        "heavy_rain",
    )
    for retired in ("earthquake", "fire", "protest", "blizzard"):
        with pytest.raises(ValidationError):
            DisruptionSpec.model_validate({"type": retired, "x": 0, "z": 0})


def test_route_travel_ticks_match_reachability() -> None:
    RouteObservation(unit_id="u", incident_id="i", reachable=True, travel_ticks=3)
    RouteObservation(unit_id="u", incident_id="i", reachable=False)
    with pytest.raises(ValidationError):
        RouteObservation(unit_id="u", incident_id="i", reachable=True)
    with pytest.raises(ValidationError):
        RouteObservation(unit_id="u", incident_id="i", reachable=False, travel_ticks=2)


@pytest.mark.req("ARCH-02")
def test_decision_identity_is_strict() -> None:
    envelope = {
        "run_id": "r",
        "run_epoch": 1,
        "actor_id": "mayor",
        "decision_id": "dec-000001",
        "observation_id": "0" * 64,
        "observation_tick": 3,
        "apply_tick": 8,
    }
    DecisionEnvelope.model_validate(envelope)
    DecisionEnvelope.model_validate(envelope | {"actor_id": "resident:12"})
    for bad in ({"actor_id": "someone"}, {"run_epoch": 0}, {"observation_id": "xyz"}):
        with pytest.raises(ValidationError):
            DecisionEnvelope.model_validate(envelope | bad)
    with pytest.raises(ValidationError):
        DecisionEnvelope.model_validate(envelope | {"extra": 1})
    with pytest.raises(ValidationError):
        MayorProposal.model_validate({"action": "dispatch everyone", "statement": ""})


def test_controller_labels_cover_every_controller() -> None:
    assert set(CONTROLLER_DISPLAY) == {"baseline", "local", "api", "hold", "degraded"}
    assert "Degraded operation" in CONTROLLER_DISPLAY["degraded"]


@pytest.mark.req("ARCH-03")
def test_schema_exports_the_hybrid_contract() -> None:
    schema = build_schema()
    for root in (
        "map_revision",
        "run_launch_request",
        "run_handle",
        "tick_observation",
        "tick_outcome",
        "disruption_inject_request",
        "resident_decision_request",
        "mayor_decision_record",
        "order_record",
        "error_response",
    ):
        assert root in schema["properties"], root
    assert "TickOutcome" in schema["$defs"]
    ErrorResponse.model_validate({"error": {"code": "tick_gap", "message": "expected tick 5"}})


@pytest.mark.req("ARCH-03", "MAY-06")
def test_examples_are_exactly_what_the_engine_produces(tmp_path: Path) -> None:
    from tests.engines.contract_story import EXAMPLES as STORY_EXAMPLES
    from tests.engines.contract_story import build_examples, render

    for name, document in build_examples(tmp_path).items():
        committed = (STORY_EXAMPLES / f"{name}.json").read_text(encoding="utf-8")
        assert committed == render(document), f"{name} is stale: run contract_story --write"

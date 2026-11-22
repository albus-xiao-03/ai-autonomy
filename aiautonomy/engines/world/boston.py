"""Scenario parameters of a hybrid Boston run (docs/contract.md §3, engine-plan Appendix B).

The browser game drives the clock; these values fix the engine's timing rules for decisions,
outcome windows and politics, and the seeded automatic disruptions.

REQ: SIM-01, SIM-03
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MapPin(_Frozen):
    """The scenario's default map revision (a launch request always pins its own)."""

    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$", max_length=64)
    revision: int = Field(ge=1)


class AutomaticDisruptions(_Frozen):
    first_after_ticks: int = Field(default=60, ge=1, le=100_000)
    mean_interval_ticks: int = Field(default=240, ge=1, le=100_000)
    max_per_run: int = Field(default=4, ge=0, le=100)


class BostonWorldConfig(_Frozen):
    """`world:` of a Boston scenario file."""

    kind: Literal["boston_hybrid"] = "boston_hybrid"
    map: MapPin = MapPin(id="boston-template", revision=1)
    mayor_latency_ticks: int = Field(default=5, ge=1, le=1000)
    resident_latency_ticks: int = Field(default=2, ge=1, le=1000)
    outcome_window_ticks: int = Field(default=60, ge=1, le=10_000)
    politics_interval_ticks: int = Field(default=15, ge=1, le=10_000)
    severe_incident_severity: int = Field(default=60, ge=0, le=100)
    prioritize_ticks: int = Field(default=30, ge=1, le=10_000)
    automatic_disruptions: AutomaticDisruptions = AutomaticDisruptions()

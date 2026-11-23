"""Common contract types: the strict base model, identifiers, enums and error bodies.

REQ: ARCH-02, ARCH-03
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = 1
"""Bumped on any incompatible change to the hybrid contract (docs/contract.md changelog)."""

MAX_TICK = 100_000
MAX_RESIDENT_ID = 1_000_000


class ContractModel(BaseModel):
    """Strict base: unknown fields are rejected and instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


EntityId = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
"""Stable identifier of a map entity, unit, incident, decision, order or disruption."""

MapId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9-]*$")]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Tick = Annotated[int, Field(ge=0, le=MAX_TICK)]
ResidentId = Annotated[int, Field(ge=0, le=MAX_RESIDENT_ID)]
Meters = Annotated[float, Field(ge=-100_000, le=100_000, allow_inf_nan=False)]
Percent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
RequestId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")]

Department = Literal["police", "fire", "medical"]
"""Service departments. `medical` covers EMS ambulances based at medical facilities."""

DEPARTMENTS: tuple[Department, ...] = ("police", "fire", "medical")

MayorBackend = Literal["baseline", "local", "api"]

ControllerLabel = Literal["baseline", "local", "api", "hold", "degraded"]
"""Who is governing right now. `hold`: the mayor issued no order (failure, timeout or outage);
standing dispatch continues. `degraded`: the game cannot reach the engine and runs its own
civic controller; only the game ever shows this label."""

CONTROLLER_DISPLAY: dict[str, str] = {
    "baseline": "Rule-based mayor",
    "local": "Qwen 3 · 8B (local)",
    "api": "Claude API mayor",
    "hold": "Mayor holding · standing dispatch continues",
    "degraded": "Degraded operation · engine offline",
}

RunStatusLabel = Literal["running", "completed", "removed", "interrupted"]


class Failure(ContractModel):
    """One validation failure or warning."""

    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)
    entity_id: str | None = None
    message: str = Field(max_length=500)


class ErrorResponse(ContractModel):
    """Body of every 4xx answer from the hybrid REST API."""

    error: Failure
    failures: list[Failure] = Field(default_factory=list)

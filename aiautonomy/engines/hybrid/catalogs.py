"""Versioned catalogs a hybrid run loads and records: incident kinds and their dispatch needs,
and the seven disruption types (whose incidents take their needs from the dispatch catalog).

Each catalog is a data file with `id`, `version` and `schema_version`; the run manifest
records its path and SHA-256, so a replay can tell when a catalog changed.

REQ: SRV-01, SRV-07, MAY-04, EVT-01, EVT-02
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aiautonomy.engines.contract.dispatch import IncidentKind, IncidentKindSpec
from aiautonomy.engines.contract.disruptions import (
    DISRUPTION_TYPES,
    DisruptionEffects,
    DisruptionType,
    DisruptionTypeSpec,
    IncidentTemplate,
    Recovery,
)
from aiautonomy.engines.core.datafiles import DataFileModel, DataFileRef, load_data_file

DISPATCH_CATALOG = Path("data/catalogs/dispatch.v1.yaml")
DISRUPTION_CATALOG = Path("data/catalogs/disruptions.v1.yaml")
POLITICS_RULES = Path("data/politics/rules.v1.yaml")


class DispatchCatalog(DataFileModel):
    """`data/catalogs/dispatch.v1.yaml`: one entry per incident kind."""

    title: str
    kinds: list[IncidentKindSpec]

    @model_validator(mode="after")
    def _every_kind_once(self) -> Self:
        kinds = [spec.kind for spec in self.kinds]
        if sorted(kinds) != sorted(get_args(IncidentKind)):
            raise ValueError("the dispatch catalog must list every incident kind exactly once")
        return self

    def spec(self, kind: str) -> IncidentKindSpec:
        for spec in self.kinds:
            if spec.kind == kind:
                return spec
        raise KeyError(kind)


class DisruptionEntry(BaseModel):
    """One type in `data/catalogs/disruptions.v1.yaml` (its incident comes from dispatch)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: DisruptionType
    label: str
    description: str
    radius_m: int = Field(ge=10, le=5000)
    intensity: int = Field(ge=1, le=100)
    duration_ticks: int = Field(ge=1, le=2000)
    effects: DisruptionEffects
    recovery: Recovery


class DisruptionCatalog(DataFileModel):
    """`data/catalogs/disruptions.v1.yaml`: exactly the seven disruption types."""

    title: str
    types: list[DisruptionEntry]

    @model_validator(mode="after")
    def _exactly_seven(self) -> Self:
        if [entry.id for entry in self.types] != list(DISRUPTION_TYPES):
            raise ValueError(f"the disruption catalog must list exactly {list(DISRUPTION_TYPES)}")
        return self


class _Rules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AuthorityRules(_Rules):
    initial: int = Field(ge=0, le=100)
    recovery_interval_ticks: int = Field(ge=1)
    recovery_step: int = Field(ge=0, le=100)


class OrderRules(_Rules):
    window_ticks: int = Field(ge=1)
    allowance: int = Field(ge=0)
    penalty: int = Field(ge=0, le=100)


class PetitionRules(_Rules):
    threshold_bp: int = Field(ge=1, le=10_000)
    routine_sign_below_mood: float = Field(ge=0, le=100)
    cooldown_ticks: int = Field(ge=0)


class VoteRules(_Rules):
    opens_after_ticks: int = Field(ge=1)
    window_ticks: int = Field(ge=1)
    min_turnout_bp: int = Field(ge=0, le=10_000)
    routine_replace_below_mood: float = Field(ge=0, le=100)


class ProtestRules(_Rules):
    routine_join_below_mood: float = Field(ge=0, le=100)
    min_participants: int = Field(ge=1)
    persistence_ticks: int = Field(ge=1)
    pressure_interval_ticks: int = Field(ge=1)
    withdrawal_ticks: int = Field(ge=1)


class PoliticsRules(DataFileModel):
    """`data/politics/rules.v1.yaml` (POL-04: explicit, versioned, recorded)."""

    title: str
    authority: AuthorityRules
    orders: OrderRules
    petition: PetitionRules
    vote: VoteRules
    protest: ProtestRules
    removal_priority: list[str]

    @model_validator(mode="after")
    def _priority_names_every_mechanism(self) -> Self:
        if sorted(self.removal_priority) != ["authority_withdrawn", "recall_vote"]:
            raise ValueError("removal_priority must order recall_vote and authority_withdrawn")
        return self


def scaled_severity(base: int, intensity: int) -> int:
    """Severity = base × intensity / 50, rounded half up, clamped to 1..100."""
    return max(1, min(100, (base * intensity * 2 + 50) // 100))


@dataclass(frozen=True, slots=True)
class Catalogs:
    dispatch: DispatchCatalog
    disruptions: tuple[DisruptionTypeSpec, ...]
    politics: PoliticsRules
    refs: tuple[DataFileRef, ...]

    def disruption(self, type_id: str) -> DisruptionTypeSpec:
        for spec in self.disruptions:
            if spec.id == type_id:
                return spec
        raise KeyError(type_id)


def _types(entries: list[DisruptionEntry], dispatch: DispatchCatalog) -> list[DisruptionTypeSpec]:
    specs = []
    for entry in entries:
        kind = dispatch.spec(entry.id)
        incident = IncidentTemplate(
            kind=kind.kind,
            severity=scaled_severity(kind.severity, entry.intensity),
            needs=kind.needs,
        )
        specs.append(DisruptionTypeSpec(**entry.model_dump(), incident=incident))
    return specs


@cache
def _load(root: str) -> Catalogs:
    base = Path(root)
    dispatch = load_data_file(base / DISPATCH_CATALOG, DispatchCatalog, root=base)
    disruptions = load_data_file(base / DISRUPTION_CATALOG, DisruptionCatalog, root=base)
    politics = load_data_file(base / POLITICS_RULES, PoliticsRules, root=base)
    return Catalogs(
        dispatch=dispatch.model,
        disruptions=tuple(_types(disruptions.model.types, dispatch.model)),
        politics=politics.model,
        refs=(dispatch.ref, disruptions.ref, politics.ref),
    )


def load_catalogs(root: Path) -> Catalogs:
    """The catalogs of `root`, loaded once per process."""
    return _load(str(root.resolve()))

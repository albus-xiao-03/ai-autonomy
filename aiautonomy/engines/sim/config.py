"""Layered run configuration (docs/engine-plan.md §4.6).

Engine defaults (`config/engine.yaml`) are overlaid by the scenario file
(`data/scenarios/<name>.v<N>.yaml`, highest version), then by the run overrides (the run
configuration panel or CLI flags), and the result is frozen into a `RunConfig`. Changing a
frozen field needs a new run.

REQ: SIM-01, SIM-04
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag

from aiautonomy.engines.core.datafiles import (
    DataFileError,
    DataFileModel,
    DataFileRef,
    load_data_file,
)
from aiautonomy.engines.core.money import apply_bp
from aiautonomy.engines.core.paths import repo_root
from aiautonomy.engines.world.boston import BostonWorldConfig
from aiautonomy.engines.world.toy import ToyWorldConfig

MAX_SEED = 2**53 - 1
MAX_DURATION = 100_000
DEFAULT_SCENARIO_ALIAS = "default"
_SCENARIO_FILE = re.compile(r"^(?P<name>[a-z][a-z0-9_-]*)\.v(?P<version>\d+)\.yaml$")


def _world_kind(value: Any) -> str:
    """`kind` of a world section; scenario files written before hybrid runs omit it (toy)."""
    if isinstance(value, dict):
        return str(value.get("kind", "toy_grid"))
    return str(getattr(value, "kind", "toy_grid"))


WorldConfig = Annotated[
    Annotated[ToyWorldConfig, Tag("toy_grid")] | Annotated[BostonWorldConfig, Tag("boston_hybrid")],
    Discriminator(_world_kind),
]
"""The toy grid (M0, driven by the engine) or a hybrid Boston run (driven by the game)."""


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SimSettings(_Frozen):
    """SIM-01 parameters, all configurable before a run."""

    seed: int = Field(ge=0, le=MAX_SEED)
    tick_minutes: int = Field(ge=1, le=60)
    start_minute_of_day: int = Field(ge=0, le=1439)
    ticks_per_second: float = Field(gt=0, le=100)
    duration: int = Field(ge=1, le=MAX_DURATION)
    mayor_interval: int = Field(ge=1)
    population: int = Field(ge=0)
    llm_ratio_bp: int = Field(ge=0, le=10_000)


class SimOverrides(_Frozen):
    seed: int | None = Field(default=None, ge=0, le=MAX_SEED)
    tick_minutes: int | None = Field(default=None, ge=1, le=60)
    start_minute_of_day: int | None = Field(default=None, ge=0, le=1439)
    ticks_per_second: float | None = Field(default=None, gt=0, le=100)
    duration: int | None = Field(default=None, ge=1, le=MAX_DURATION)
    mayor_interval: int | None = Field(default=None, ge=1)
    population: int | None = Field(default=None, ge=0)
    llm_ratio_bp: int | None = Field(default=None, ge=0, le=10_000)


class RecordSettings(_Frozen):
    snapshot_interval: int = Field(ge=1)


class EngineFile(DataFileModel):
    """`config/engine.yaml`."""

    default_scenario: str
    sim: SimSettings
    record: RecordSettings


class ScenarioFile(DataFileModel):
    """`data/scenarios/<id>.v<version>.yaml`."""

    title: str
    description: str = ""
    sim: SimOverrides = SimOverrides()
    stream_seed_overrides: dict[str, int] = Field(default_factory=dict)
    world: WorldConfig


class RunOverrides(_Frozen):
    """User overrides applied last (run configuration panel, `configure`, CLI flags)."""

    scenario: str | None = None
    seed: int | None = Field(default=None, ge=0, le=MAX_SEED)
    duration: int | None = Field(default=None, ge=1, le=MAX_DURATION)
    population: int | None = Field(default=None, ge=0)
    llm_ratio_bp: int | None = Field(default=None, ge=0, le=10_000)

    def merged(self, newer: RunOverrides) -> RunOverrides:
        """These overrides with every field `newer` sets replaced."""
        return self.model_copy(update=newer.model_dump(exclude_none=True))


class RunConfig(SimSettings):
    """The frozen configuration of one run, recorded in its manifest."""

    scenario: str
    snapshot_interval: int = Field(ge=1)
    stream_seed_overrides: dict[str, int] = Field(default_factory=dict)
    world: WorldConfig

    @property
    def llm_count(self) -> int:
        """LLM residents: `(population × ratio_bp + 5000) // 10000` (docs/engine-plan.md §4.2)."""
        return apply_bp(self.population, self.llm_ratio_bp)


@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    config: RunConfig
    data_files: tuple[DataFileRef, ...]


def engine_config_path(root: Path) -> Path:
    return root / "config" / "engine.yaml"


def available_scenarios(root: Path | None = None) -> dict[str, Path]:
    """Map scenario id to its highest-version file."""
    root = root or repo_root()
    best: dict[str, tuple[int, Path]] = {}
    for path in sorted((root / "data" / "scenarios").glob("*.v*.yaml")):
        match = _SCENARIO_FILE.match(path.name)
        if match is None:
            continue
        name, version = match["name"], int(match["version"])
        if name not in best or version > best[name][0]:
            best[name] = (version, path)
    return {name: path for name, (_, path) in sorted(best.items())}


def resolve_run_config(
    overrides: RunOverrides | None = None, *, root: Path | None = None
) -> ResolvedConfig:
    """Load the engine defaults and the scenario, apply `overrides` and freeze the result."""
    root = root or repo_root()
    overrides = overrides or RunOverrides()
    engine = load_data_file(engine_config_path(root), EngineFile, root=root)
    name = overrides.scenario or DEFAULT_SCENARIO_ALIAS
    if name == DEFAULT_SCENARIO_ALIAS:
        name = engine.model.default_scenario
    scenarios = available_scenarios(root)
    if name not in scenarios:
        raise DataFileError(f"unknown scenario {name!r} (available: {sorted(scenarios)})")
    scenario = load_data_file(scenarios[name], ScenarioFile, root=root)
    if scenario.model.id != name:
        raise DataFileError(f"{scenarios[name]}: id {scenario.model.id!r} does not match file name")
    values: dict[str, Any] = engine.model.sim.model_dump()
    values |= scenario.model.sim.model_dump(exclude_none=True)
    values |= overrides.model_dump(exclude_none=True, exclude={"scenario"})
    config = RunConfig(
        **values,
        scenario=name,
        snapshot_interval=engine.model.record.snapshot_interval,
        stream_seed_overrides=dict(scenario.model.stream_seed_overrides),
        world=scenario.model.world,
    )
    return ResolvedConfig(config=config, data_files=(engine.ref, scenario.ref))

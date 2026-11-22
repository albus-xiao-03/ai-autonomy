import hashlib
import subprocess
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from aiautonomy.engines.core import version as version_module
from aiautonomy.engines.core.datafiles import DataFileError, load_data_file
from aiautonomy.engines.core.paths import repo_root
from aiautonomy.engines.sim.config import (
    EngineFile,
    RunConfig,
    RunOverrides,
    ScenarioFile,
    available_scenarios,
    resolve_run_config,
)

ENGINE_YAML = """\
id: engine
version: 1
schema_version: 1
default_scenario: alpha
sim:
  seed: 1
  tick_minutes: 1
  start_minute_of_day: 420
  ticks_per_second: 5
  duration: 300
  mayor_interval: 30
  population: 100
  llm_ratio_bp: 5000
record:
  snapshot_interval: 30
"""


def scenario_yaml(version: int, sim: str = "{}") -> str:
    return (
        f"id: alpha\nversion: {version}\nschema_version: 1\ntitle: Alpha v{version}\n"
        f"sim: {sim}\nworld:\n  movers: {version}\n"
    )


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "scenarios").mkdir(parents=True)
    (tmp_path / "config" / "engine.yaml").write_text(ENGINE_YAML)
    (tmp_path / "data" / "scenarios" / "alpha.v1.yaml").write_text(scenario_yaml(1))
    (tmp_path / "data" / "scenarios" / "alpha.v2.yaml").write_text(
        scenario_yaml(2, "{seed: 9, duration: 50}")
    )
    return tmp_path


@pytest.mark.req("SIM-01")
def test_engine_defaults_match_sim_01() -> None:
    config = resolve_run_config().config
    assert config.scenario == "toy"
    assert config.tick_minutes == 1
    assert config.start_minute_of_day == 7 * 60
    assert config.ticks_per_second == 5
    assert config.duration == 300
    assert config.mayor_interval == 30
    assert config.population == 100
    assert config.llm_ratio_bp == 5000
    assert config.llm_count == 50
    assert config.world.movers == 40


@pytest.mark.req("SIM-01", "SIM-04")
def test_layering_scenario_then_overrides_then_frozen(fake_root: Path) -> None:
    resolved = resolve_run_config(root=fake_root)
    config = resolved.config
    assert config.scenario == "alpha"
    assert config.world.movers == 2  # highest scenario version wins
    assert (config.seed, config.duration) == (9, 50)  # scenario overrides engine defaults
    overridden = resolve_run_config(RunOverrides(seed=3, duration=10), root=fake_root).config
    assert (overridden.seed, overridden.duration, overridden.population) == (3, 10, 100)
    with pytest.raises(ValidationError):
        config.duration = 1  # type: ignore[misc]


@pytest.mark.req("SIM-04")
def test_data_files_are_validated_and_fingerprinted(fake_root: Path) -> None:
    resolved = resolve_run_config(root=fake_root)
    refs = {ref.id: ref for ref in resolved.data_files}
    scenario_path = fake_root / "data" / "scenarios" / "alpha.v2.yaml"
    assert refs["alpha"].path == "data/scenarios/alpha.v2.yaml"
    assert refs["alpha"].version == 2
    assert refs["alpha"].sha256 == hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    assert refs["engine"].schema_version == 1


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("id: alpha\nversion: 1\ntitle: x\nworld: {}\n", "schema_version"),
        (scenario_yaml(1) + "surprise: 1\n", "surprise"),
        (scenario_yaml(1).replace("schema_version: 1", "schema_version: 9"), "not supported"),
        ("- not a mapping\n", "mapping"),
        ("id: [unclosed\n", "cannot parse"),
    ],
)
def test_invalid_data_files_are_rejected(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "alpha.v1.yaml"
    path.write_text(text)
    with pytest.raises(DataFileError, match=message):
        load_data_file(path, ScenarioFile)


def test_unknown_scenario_and_default_alias(fake_root: Path) -> None:
    assert sorted(available_scenarios(fake_root)) == ["alpha"]
    assert resolve_run_config(RunOverrides(scenario="default"), root=fake_root).config.scenario == (
        "alpha"
    )
    with pytest.raises(DataFileError, match="unknown scenario"):
        resolve_run_config(RunOverrides(scenario="nope"), root=fake_root)


@pytest.mark.req("SIM-04")
def test_every_shipped_data_file_has_id_version_and_schema_version() -> None:
    root = repo_root()
    paths = [*sorted((root / "data").rglob("*.yaml")), *sorted((root / "config").glob("*.yaml"))]
    assert paths
    for path in paths:
        header = yaml.safe_load(path.read_text())
        assert {"id", "version", "schema_version"} <= set(header), path
    load_data_file(root / "config" / "engine.yaml", EngineFile)
    for path in available_scenarios(root).values():
        load_data_file(path, ScenarioFile)


def test_run_config_round_trips_through_json() -> None:
    config = resolve_run_config().config
    assert RunConfig.model_validate(config.model_dump(mode="json")) == config


def test_engine_version_tolerates_missing_git(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_git(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git")

    version_module.engine_version.cache_clear()
    monkeypatch.setattr(subprocess, "run", no_git)
    try:
        stamp = version_module.engine_version()
        assert (stamp.git_sha, stamp.dirty) == (None, None)
        assert stamp.label == stamp.version
    finally:
        version_module.engine_version.cache_clear()


def test_engine_version_in_this_checkout() -> None:
    stamp = version_module.engine_version()
    assert stamp.version == "0.1.0"
    assert stamp.git_sha is None or len(stamp.git_sha) == 40
    assert stamp.label.startswith("0.1.0")

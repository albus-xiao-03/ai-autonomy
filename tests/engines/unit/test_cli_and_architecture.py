import importlib
from pathlib import Path

import pytest

from aiautonomy.engines import cli
from aiautonomy.engines.core.paths import repo_root

# plans/R1.md §3.1: every ARCH-01 component and the package that implements it.
COMPONENT_PACKAGES = {
    "Simulation engine": ["sim", "world", "traffic", "services", "build", "finance", "residents",
                          "politics", "host", "metrics"],
    "Action validator": ["mayor"],
    "Agent scheduler": ["agents"],
    "Local resident adapter": ["agents"],
    "Mayor adapter": ["mayor"],
    "Event system": ["events"],
    "Recorder and replay": ["record"],
    "Engine server and protocol": ["api"],
}  # fmt: skip


@pytest.mark.req("ARCH-01")
def test_every_engine_component_has_its_package() -> None:
    architecture = (repo_root() / "docs" / "architecture.md").read_text()
    for packages in COMPONENT_PACKAGES.values():
        for package in packages:
            module = importlib.import_module(f"aiautonomy.engines.{package}")
            assert module.__doc__, package
            assert f"aiautonomy.engines.{package}" in architecture, package


@pytest.mark.parametrize(
    ("argv", "milestone"),
    [(["compare", "a", "b"], "M5"), (["bench", "all"], "M4"), (["map", "build"], "M1")],
)
def test_later_milestone_commands_are_stubs(
    argv: list[str], milestone: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(argv) == 2
    assert f"not implemented until {milestone}" in capsys.readouterr().err


def test_run_requires_headless_and_a_known_scenario(tmp_path: Path) -> None:
    assert cli.main(["run", "--runs-dir", str(tmp_path)]) == 2
    assert cli.main(["run", "--headless", "--scenario", "nope", "--runs-dir", str(tmp_path)]) == 2
    assert not any(tmp_path.iterdir())


@pytest.mark.req("SIM-01")
def test_headless_run_accepts_seed_and_duration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["run", "--headless", "--seed", "9", "--duration", "12", "--runs-dir", str(tmp_path)]
    assert cli.main(argv) == 0
    out = capsys.readouterr().out
    assert "completed at tick 12/12" in out
    assert "-toy-s9-" in out

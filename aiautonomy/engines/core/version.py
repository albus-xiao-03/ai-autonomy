"""Engine version stamp: package version, git SHA and dirty flag (plans/R1.md §4.6).

Git is optional: without git or outside a checkout, the SHA and dirty flag are None.

REQ: SIM-04
"""

import functools
import os
import subprocess
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from aiautonomy.engines.core.paths import repo_root

PACKAGE = "aiautonomy"


@dataclass(frozen=True, slots=True)
class EngineVersion:
    version: str
    git_sha: str | None
    dirty: bool | None

    @property
    def label(self) -> str:
        """Display label, e.g. `0.1.0+g7c1ad51.dirty`."""
        if self.git_sha is None:
            return self.version
        return f"{self.version}+g{self.git_sha[:7]}{'.dirty' if self.dirty else ''}"

    def to_dict(self) -> dict[str, str | bool | None]:
        return {"version": self.version, "git_sha": self.git_sha, "dirty": self.dirty}


def _git(root: Path, *args: str) -> str | None:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
            env=env,
        )
    except OSError, subprocess.SubprocessError:
        return None
    return completed.stdout


def package_version() -> str:
    try:
        return metadata.version(PACKAGE)
    except metadata.PackageNotFoundError:
        return "0.0.0+unknown"


@functools.cache
def engine_version() -> EngineVersion:
    """The stamp of the running engine, computed once per process."""
    version = package_version()
    try:
        root = repo_root()
    except FileNotFoundError:
        return EngineVersion(version, None, None)
    sha = _git(root, "rev-parse", "HEAD")
    if sha is None:
        return EngineVersion(version, None, None)
    status = _git(root, "status", "--porcelain")
    return EngineVersion(version, sha.strip(), None if status is None else bool(status.strip()))

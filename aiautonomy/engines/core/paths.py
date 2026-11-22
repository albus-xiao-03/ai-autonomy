"""Locate the repository root and the directories the engine reads and writes.

The root is the nearest ancestor (of this package, else of the working directory) that
contains both `data/` and `config/`; `AIA_ROOT` overrides the search. Run records go to
`<root>/runs` unless `AIA_RUNS_DIR` says otherwise (tests use both); user map saves go to
`<root>/maps` unless `AIA_MAPS_DIR` says otherwise.
"""

import os
from pathlib import Path


def _is_root(candidate: Path) -> bool:
    return (candidate / "data").is_dir() and (candidate / "config").is_dir()


def _search_up(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if _is_root(candidate):
            return candidate
    return None


def repo_root() -> Path:
    """Return the repository root: `AIA_ROOT`, else the nearest ancestor with data/ and config/."""
    override = os.environ.get("AIA_ROOT")
    if override:
        return Path(override).resolve()
    found = _search_up(Path(__file__).resolve().parent) or _search_up(Path.cwd().resolve())
    if found is None:
        raise FileNotFoundError(
            "cannot find the repository root (no directory with data/ and config/ above the "
            "package or the working directory); set AIA_ROOT"
        )
    return found


def runs_dir() -> Path:
    """Return the run-record directory: `AIA_RUNS_DIR`, else `<root>/runs`."""
    override = os.environ.get("AIA_RUNS_DIR")
    if override:
        return Path(override).resolve()
    return repo_root() / "runs"


def maps_dir() -> Path:
    """Return the user map-save directory: `AIA_MAPS_DIR`, else `<root>/maps`."""
    override = os.environ.get("AIA_MAPS_DIR")
    if override:
        return Path(override).resolve()
    return repo_root() / "maps"


def shipped_maps_dir() -> Path:
    """Return the read-only shipped map revisions: `<root>/data/maps`."""
    return repo_root() / "data" / "maps"

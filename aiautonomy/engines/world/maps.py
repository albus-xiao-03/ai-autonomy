"""Map documents: canonical catalog, content hash, geometry helpers and revision files.

The canonical catalog (`data/catalogs/canonical.v1.json`) lists what the game fixes and no map
may change: the level bounds, the seven canonical landmarks, the famous district clusters
unlocked per level, and the fixed I-93 geometry pinned by the SHA-256 of
`game/highway-data.js`. `tests/boston-maps.cjs` checks it against the game's own code.

A revision's `sha256` is the SHA-256 of the canonical JSON of its `content`, so it does not
depend on key order, whitespace or omitted defaults.

REQ: CITY-01, CITY-02, CITY-03
"""

import hashlib
import json
import math
import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from aiautonomy.engines.contract.maps import (
    BuildingType,
    LandmarkSite,
    MapBuilding,
    MapContent,
    MapFacility,
    MapLandmark,
    MapRevision,
    RoadType,
)
from aiautonomy.engines.core.canonical import canonical_json
from aiautonomy.engines.core.datafiles import DataFileModel, load_data_file
from aiautonomy.engines.core.paths import repo_root

CANONICAL_CATALOG = Path("data/catalogs/canonical.v1.json")
ROAD_WIDTHS: dict[RoadType, float] = {"highway": 14.0, "oneway": 5.0, "twoway": 8.0}
BUILDING_SCALE: dict[BuildingType, float] = {
    "residential": 2.2,
    "office": 5.0,
    "shop": 3.0,
    "social": 3.8,
    "park": 5.0,
    "parking": 5.0,
}
"""The game's `buildingScale`; a player building's footprint radius is scale × 4.2."""
MIN_ROAD_LENGTH_M = 10.0
MAX_ACCESS_M = 20.0
"""A driveway may be at most 20 m from the road's curb (game `access`)."""
POSITION_TOLERANCE_M = 0.01


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LevelBounds(_Frozen):
    level: int = Field(ge=1, le=4)
    min_x: float
    max_x: float
    min_z: float
    max_z: float

    def contains(self, x: float, z: float, margin: float = 0.0) -> bool:
        return (
            self.min_x <= x - margin
            and x + margin <= self.max_x
            and self.min_z <= z - margin
            and z + margin <= self.max_z
        )


class CanonicalLandmark(_Frozen):
    id: str
    name: str
    site: LandmarkSite
    x: float
    z: float
    radius: float


class CanonicalArea(_Frozen):
    id: str
    label: str
    type: BuildingType
    x: float
    z: float
    rotation: float
    radius: float
    level: int = Field(ge=1, le=4)


class CanonicalFixed(_Frozen):
    id: str
    source: str
    sha256: str


class CanonicalCatalog(DataFileModel):
    """`data/catalogs/canonical.v1.json`."""

    title: str
    source: str
    levels: list[LevelBounds]
    landmarks: list[CanonicalLandmark]
    areas: list[CanonicalArea]
    fixed: list[CanonicalFixed]

    def bounds(self, level: int) -> LevelBounds:
        for bounds in self.levels:
            if bounds.level == level:
                return bounds
        raise KeyError(f"no bounds for level {level}")

    def areas_for(self, level: int) -> list[CanonicalArea]:
        return [area for area in self.areas if area.level <= level]


@dataclass(frozen=True, slots=True)
class LoadedCatalog:
    catalog: CanonicalCatalog
    path: str
    sha256: str


@cache
def _load_catalog(path: str) -> LoadedCatalog:
    loaded = load_data_file(Path(path), CanonicalCatalog, root=repo_root())
    return LoadedCatalog(loaded.model, loaded.ref.path, loaded.ref.sha256)


def canonical_catalog(root: Path | None = None) -> LoadedCatalog:
    """The canonical catalog of `root` (default: the repository), cached per path."""
    return _load_catalog(str((root or repo_root()) / CANONICAL_CATALOG))


def content_sha256(content: MapContent) -> str:
    """SHA-256 of the canonical JSON of the content (the value every run pins)."""
    text = canonical_json(content.model_dump(mode="json"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- geometry (validation only; never part of hashed tick state) ---------------------


def distance(ax: float, az: float, bx: float, bz: float) -> float:
    return math.hypot(ax - bx, az - bz)


@dataclass(frozen=True, slots=True)
class Projection:
    x: float
    z: float
    t: float
    distance: float


def project(px: float, pz: float, ax: float, az: float, bx: float, bz: float) -> Projection:
    """Closest point to (px, pz) on segment a–b, as the game's `projection`."""
    dx, dz = bx - ax, bz - az
    length2 = dx * dx + dz * dz or 1.0
    t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / length2))
    x, z = ax + dx * t, az + dz * t
    return Projection(x, z, t, distance(px, pz, x, z))


def facing(rotation: float) -> tuple[float, float]:
    """Unit vector a building faces, as the game: (sin r, cos r) in (x, z)."""
    return math.sin(rotation), math.cos(rotation)


def footprint_radius(building: MapBuilding) -> float:
    return building.radius or BUILDING_SCALE[building.type] * 4.2


def entrance(site: MapBuilding | MapFacility | MapLandmark) -> tuple[float, float]:
    """Driveway start, as the game's `access`: centre + facing × entrance distance."""
    if isinstance(site, MapBuilding):
        offset = site.radius or BUILDING_SCALE[site.type] * 2.5
        fx, fz = facing(site.rotation)
    elif isinstance(site, MapFacility):
        offset = site.radius
        fx, fz = facing(site.rotation)
    else:
        offset = site.radius
        fx, fz = facing(0.0)
    return site.x + fx * offset, site.z + fz * offset


# --- revision files ------------------------------------------------------------------


def read_revision(path: Path) -> MapRevision:
    return MapRevision.model_validate_json(path.read_bytes())


def revision_json(revision: MapRevision) -> str:
    """The on-disk form: indented JSON in model field order, newline-terminated."""
    return json.dumps(revision.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def write_revision_exclusive(path: Path, revision: MapRevision) -> None:
    """Write a new revision file; fails if it already exists (no silent overwrite)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(revision_json(revision), encoding="utf-8")
    try:
        os.link(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)

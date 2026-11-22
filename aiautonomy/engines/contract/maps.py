"""Map documents: the Boston template, saved revisions and save/validate requests.

Coordinates follow the game: meters, x east, z south, origin at the game's geographic
origin (`game/geography.js`). Roads reference nodes; buildings and facilities reference the
road their driveway joins. A revision's `sha256` is the SHA-256 of the canonical JSON of its
`content`, and every run pins `{id, revision, sha256}`.

REQ: CITY-01, CITY-02, CITY-03, CITY-05
"""

from typing import Literal

from pydantic import Field

from aiautonomy.engines.contract.common import (
    ContractModel,
    Department,
    EntityId,
    Failure,
    MapId,
    Meters,
    Sha256Hex,
)

RoadType = Literal["twoway", "oneway", "highway"]
BuildingType = Literal["residential", "office", "shop", "social", "park", "parking"]
LandmarkKind = Literal["canonical", "user"]
"""`canonical`: one of the game's fixed landmarks; never unlockable. `user`: designated by the
map author; locked unless the author explicitly unlocks it in a setup save."""
LandmarkSite = Literal["hall", "garden", "hospital", "church", "market", "common", "statehouse"]


class MapNode(ContractModel):
    id: EntityId
    x: Meters
    z: Meters


class MapRoad(ContractModel):
    """A straight road segment between two nodes (the game's `a`/`b` endpoints)."""

    id: EntityId
    name: str = Field(default="", max_length=80)
    a: EntityId = Field(description="Start node id.")
    b: EntityId = Field(description="End node id; one-way roads run from `a` to `b`.")
    type: RoadType = "twoway"
    bridge: bool = False
    tunnel: bool = False


class Access(ContractModel):
    """Where a building's or facility's driveway joins the road network."""

    road: EntityId


class MapBuilding(ContractModel):
    id: EntityId
    type: BuildingType
    label: str = Field(default="", max_length=80)
    x: Meters
    z: Meters
    rotation: float = Field(ge=-7, le=7, allow_inf_nan=False, description="Radians.")
    radius: float | None = Field(
        default=None, gt=0, le=500, description="Footprint radius; null derives it from type."
    )
    area: bool = Field(
        default=False, description="A fixed famous district cluster (locked, never removable)."
    )
    access: Access


class UnitSpec(ContractModel):
    """A service unit based at a facility; its department is the facility's."""

    id: EntityId
    kind: str = Field(min_length=1, max_length=32, description="cruiser, engine, ambulance…")


class MapFacility(ContractModel):
    """A police (PD), fire (FD) or medical facility with its units."""

    id: EntityId
    name: str = Field(min_length=1, max_length=80)
    department: Department
    x: Meters
    z: Meters
    rotation: float = Field(default=0.0, ge=-7, le=7, allow_inf_nan=False)
    radius: float = Field(gt=0, le=500)
    access: Access
    landmark: EntityId | None = Field(
        default=None, description="Set when the facility occupies a landmark site (e.g. MGH)."
    )
    units: list[UnitSpec] = Field(default_factory=list, max_length=32)


class MapLandmark(ContractModel):
    id: EntityId
    name: str = Field(min_length=1, max_length=80)
    kind: LandmarkKind
    site: LandmarkSite | None = None
    x: Meters
    z: Meters
    radius: float = Field(gt=0, le=500)
    locked: bool = True


class FixedGeometry(ContractModel):
    """Read-only geometry owned by the game, pinned by the SHA-256 of its source file."""

    id: EntityId
    source: str = Field(min_length=1, max_length=200)
    sha256: Sha256Hex


class MapContent(ContractModel):
    level: int = Field(ge=1, le=4)
    nodes: list[MapNode] = Field(max_length=5000)
    roads: list[MapRoad] = Field(max_length=5000)
    buildings: list[MapBuilding] = Field(max_length=2000)
    facilities: list[MapFacility] = Field(max_length=200)
    landmarks: list[MapLandmark] = Field(max_length=200)
    fixed: list[FixedGeometry] = Field(max_length=16)
    mayor_office: EntityId = Field(
        description="Landmark or facility housing the mayor; an Outage covering it takes the "
        "mayor offline."
    )


class MapRef(ContractModel):
    """Pins one exact map revision."""

    id: MapId
    revision: int = Field(ge=1)
    sha256: Sha256Hex


class MapRevision(ContractModel):
    """One immutable saved revision."""

    format: Literal["aia-map"] = "aia-map"
    format_version: Literal[1] = 1
    id: MapId
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=120)
    parent: MapRef | None = None
    sha256: Sha256Hex = Field(description="SHA-256 of the canonical JSON of `content`.")
    unlocked: list[EntityId] = Field(
        default_factory=list,
        description="User landmarks this revision unlocked through an explicit setup action.",
    )
    content: MapContent


class MapCreateRequest(ContractModel):
    """`POST /api/maps`: save a new map (revision 1), optionally derived from `parent`."""

    id: MapId
    name: str = Field(min_length=1, max_length=120)
    parent: MapRef | None = None
    content: MapContent
    unlock: list[EntityId] = Field(default_factory=list, max_length=200)


class MapRevisionRequest(ContractModel):
    """`POST /api/maps/{id}/revisions`: save the next revision; `base` must be the latest."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    base: MapRef
    content: MapContent
    unlock: list[EntityId] = Field(default_factory=list, max_length=200)


class MapValidateRequest(ContractModel):
    """`POST /api/maps/validate`: dry run; with `base` the lock rules are checked too."""

    content: MapContent
    base: MapRef | None = None
    unlock: list[EntityId] = Field(default_factory=list, max_length=200)


class MapValidationReport(ContractModel):
    ok: bool
    sha256: Sha256Hex
    failures: list[Failure] = Field(default_factory=list)
    warnings: list[Failure] = Field(default_factory=list)


class MapRevisionSummary(ContractModel):
    revision: int = Field(ge=1)
    name: str
    sha256: Sha256Hex
    parent: MapRef | None = None


class MapSummary(ContractModel):
    id: MapId
    kind: Literal["template", "saved"]
    read_only: bool
    revisions: list[MapRevisionSummary]


class MapList(ContractModel):
    maps: list[MapSummary]

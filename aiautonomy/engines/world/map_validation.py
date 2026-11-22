"""Map validation (CITY-05) and lock enforcement (CITY-03).

`validate_content` checks one map content on its own:

- references: unique ids, road endpoints name existing nodes, access roads exist, the mayor
  office exists;
- geometry the game also enforces: level bounds, minimum road length, explicit junctions (the
  game joins crossing roads itself, so the engine requires a shared node), driveway distance
  and direction, clearance between roads, buildings, facilities and landmarks;
- canonical entities: the seven canonical landmarks, the fixed district clusters of the map's
  level and the I-93 geometry hash must equal the canonical catalog;
- services: at least one police, fire and medical facility with units, every building
  reachable by every department, and every home with a road to a workplace and back.

`check_locks` compares a save with its base revision. Locked landmarks (every canonical one,
and every user-designated one not yet unlocked) must survive unchanged; only an explicit
`unlock` list in a setup save unlocks a user-designated landmark, so no indirect edit (removal,
re-identification, moving, a kind change or a silent `locked: false`) can bypass a lock.

REQ: CITY-02, CITY-03, CITY-05
"""

from collections import deque
from collections.abc import Iterable

from aiautonomy.engines.contract.common import DEPARTMENTS, Failure
from aiautonomy.engines.contract.maps import (
    MapBuilding,
    MapContent,
    MapFacility,
    MapLandmark,
    MapRevision,
    MapRoad,
)
from aiautonomy.engines.world.maps import (
    MAX_ACCESS_M,
    MIN_ROAD_LENGTH_M,
    POSITION_TOLERANCE_M,
    ROAD_WIDTHS,
    CanonicalCatalog,
    distance,
    entrance,
    facing,
    footprint_radius,
    project,
)

JUNCTION_TOLERANCE_M = 0.05
_FACILITY_SITES = {"hospital": "medical"}
"""Landmark sites a facility may occupy, and the department it must belong to."""


def _fail(code: str, entity_id: str | None, message: str) -> Failure:
    return Failure(code=code, entity_id=entity_id, message=message)


class _Checker:
    def __init__(self, content: MapContent, catalog: CanonicalCatalog) -> None:
        self.content = content
        self.catalog = catalog
        self.failures: list[Failure] = []
        self.warnings: list[Failure] = []
        self.nodes = {node.id: node for node in content.nodes}
        self.roads = {road.id: road for road in content.roads}
        self.landmarks = {landmark.id: landmark for landmark in content.landmarks}
        self.facilities = {facility.id: facility for facility in content.facilities}

    def fail(self, code: str, entity_id: str | None, message: str) -> None:
        self.failures.append(_fail(code, entity_id, message))

    # --- references ------------------------------------------------------------------

    def unique_ids(self) -> None:
        seen: set[str] = set()
        groups: list[Iterable[str]] = [
            (node.id for node in self.content.nodes),
            (road.id for road in self.content.roads),
            (building.id for building in self.content.buildings),
            (facility.id for facility in self.content.facilities),
            (unit.id for facility in self.content.facilities for unit in facility.units),
            (landmark.id for landmark in self.content.landmarks),
        ]
        for group in groups:
            for entity_id in group:
                if entity_id in seen:
                    self.fail("duplicate_id", entity_id, f"id {entity_id!r} is used twice")
                seen.add(entity_id)

    def endpoints(self, road: MapRoad) -> tuple[float, float, float, float] | None:
        a, b = self.nodes.get(road.a), self.nodes.get(road.b)
        if a is None or b is None:
            return None
        return a.x, a.z, b.x, b.z

    def roads_and_nodes(self) -> None:
        bounds = self.catalog.bounds(self.content.level)
        for node in self.content.nodes:
            if not bounds.contains(node.x, node.z):
                self.fail("out_of_bounds", node.id, f"node outside level {bounds.level} bounds")
        for road in self.content.roads:
            for end in (road.a, road.b):
                if end not in self.nodes:
                    self.fail("unknown_node", road.id, f"road endpoint {end!r} is not a node")
            ends = self.endpoints(road)
            if ends is None:
                continue
            if road.a == road.b or distance(*ends) < MIN_ROAD_LENGTH_M:
                self.fail("degenerate_road", road.id, "road endpoints are less than 10 m apart")

    def junctions(self) -> None:
        """The game joins every crossing and T junction; the map must name a shared node."""
        segments = [(road, ends) for road in self.content.roads if (ends := self.endpoints(road))]
        for index, (road, (ax, az, bx, bz)) in enumerate(segments):
            for other, (cx, cz, dx, dz) in segments[index + 1 :]:
                if (road.bridge, road.tunnel) != (other.bridge, other.tunnel):
                    continue
                shared = {road.a, road.b} & {other.a, other.b}
                if self._touches(other, cx, cz, dx, dz, ax, az, bx, bz, shared) or self._touches(
                    road, ax, az, bx, bz, cx, cz, dx, dz, shared
                ):
                    self.fail(
                        "unjoined_junction",
                        road.id,
                        f"road meets {other.id} away from a shared node; split it at a node",
                    )
                    continue
                if not shared and _segments_cross(ax, az, bx, bz, cx, cz, dx, dz):
                    self.fail(
                        "unjoined_crossing",
                        road.id,
                        f"road crosses {other.id} without a shared node",
                    )

    def _touches(
        self,
        target: MapRoad,
        tx1: float,
        tz1: float,
        tx2: float,
        tz2: float,
        px1: float,
        pz1: float,
        px2: float,
        pz2: float,
        shared: set[str],
    ) -> bool:
        """An endpoint of the other road lies on the interior of `target`."""
        for px, pz in ((px1, pz1), (px2, pz2)):
            hit = project(px, pz, tx1, tz1, tx2, tz2)
            if hit.distance < JUNCTION_TOLERANCE_M and 0.0 < hit.t < 1.0:
                end_is_shared = any(
                    (node := self.nodes.get(node_id)) is not None
                    and distance(node.x, node.z, px, pz) < JUNCTION_TOLERANCE_M
                    for node_id in shared
                )
                if not end_is_shared:
                    return True
        return False

    def access(self, site: MapBuilding | MapFacility) -> None:
        road = self.roads.get(site.access.road)
        if road is None:
            self.fail("unknown_access_road", site.id, f"access road {site.access.road!r} unknown")
            return
        ends = self.endpoints(road)
        if ends is None:
            return
        ex, ez = entrance(site)
        hit = project(ex, ez, *ends)
        fx, fz = facing(site.rotation)
        forward = (hit.x - ex) * fx + (hit.z - ez) * fz
        if hit.distance - ROAD_WIDTHS[road.type] / 2 > MAX_ACCESS_M:
            self.fail(
                "access_too_far",
                site.id,
                f"driveway to {road.id} is {hit.distance:.1f} m (curb limit 20 m)",
            )
        elif hit.distance > JUNCTION_TOLERANCE_M and forward < 0.5 * hit.distance:
            self.fail("access_facing_away", site.id, f"{road.id} is not in front of the entrance")

    def sites(self) -> None:
        bounds = self.catalog.bounds(self.content.level)
        for building in self.content.buildings:
            radius = footprint_radius(building)
            if not bounds.contains(building.x, building.z, radius):
                self.fail("out_of_bounds", building.id, "building outside the level bounds")
            self.access(building)
        for facility in self.content.facilities:
            if facility.landmark is None and not bounds.contains(
                facility.x, facility.z, facility.radius
            ):
                self.fail("out_of_bounds", facility.id, "facility outside the level bounds")
            self.access(facility)
            if facility.landmark is not None:
                self.facility_site(facility)
        office = self.content.mayor_office
        if office not in self.landmarks and office not in self.facilities:
            self.fail("unknown_mayor_office", office, "mayor_office must be a landmark or facility")

    def facility_site(self, facility: MapFacility) -> None:
        landmark = self.landmarks.get(facility.landmark or "")
        if landmark is None:
            self.fail("unknown_landmark", facility.id, f"landmark {facility.landmark!r} unknown")
            return
        if _FACILITY_SITES.get(landmark.site or "") != facility.department:
            self.fail(
                "facility_landmark_forbidden",
                facility.id,
                f"a {facility.department} facility cannot occupy {landmark.id}",
            )
        if distance(facility.x, facility.z, landmark.x, landmark.z) > POSITION_TOLERANCE_M:
            self.fail("facility_landmark_mismatch", facility.id, "facility must sit on its site")

    def departments(self) -> None:
        for department in DEPARTMENTS:
            if not any(
                facility.department == department and facility.units
                for facility in self.content.facilities
            ):
                self.fail(
                    "missing_department",
                    None,
                    f"no {department} facility with at least one unit",
                )

    # --- canonical entities ------------------------------------------------------------

    def canonical(self) -> None:
        expected = {landmark.id: landmark for landmark in self.catalog.landmarks}
        for landmark_id, canonical in expected.items():
            landmark = self.landmarks.get(landmark_id)
            if landmark is None:
                self.fail("canonical_landmark_missing", landmark_id, f"{canonical.name} missing")
                continue
            same = (
                landmark.kind == "canonical"
                and landmark.locked
                and landmark.name == canonical.name
                and landmark.site == canonical.site
                and landmark.radius == canonical.radius
                and distance(landmark.x, landmark.z, canonical.x, canonical.z)
                <= POSITION_TOLERANCE_M
            )
            if not same:
                self.fail(
                    "canonical_landmark_changed",
                    landmark_id,
                    f"{canonical.name} must keep its canonical identity, place and footprint",
                )
        for landmark in self.content.landmarks:
            if landmark.kind == "canonical" and landmark.id not in expected:
                self.fail("canonical_landmark_unknown", landmark.id, "not a canonical landmark")
            if landmark.kind == "user" and landmark.site is not None:
                self.fail("landmark_site_forbidden", landmark.id, "user landmarks have no site")
        areas = {area.id: area for area in self.catalog.areas_for(self.content.level)}
        present = {building.id: building for building in self.content.buildings if building.area}
        for area_id, area in areas.items():
            building = present.get(area_id)
            if building is None:
                self.fail("canonical_area_missing", area_id, f"{area.label} missing")
                continue
            same = (
                building.type == area.type
                and building.label == area.label
                and building.radius == area.radius
                and building.rotation == area.rotation
                and distance(building.x, building.z, area.x, area.z) <= POSITION_TOLERANCE_M
            )
            if not same:
                self.fail("canonical_area_changed", area_id, f"{area.label} is a fixed district")
        for area_id in present.keys() - areas.keys():
            self.fail("canonical_area_unknown", area_id, "not a fixed district of this level")
        fixed = {item.id: item for item in self.content.fixed}
        for canonical_fixed in self.catalog.fixed:
            item = fixed.get(canonical_fixed.id)
            if item is None:
                self.fail("fixed_geometry_missing", canonical_fixed.id, "fixed geometry missing")
            elif (item.source, item.sha256) != (canonical_fixed.source, canonical_fixed.sha256):
                self.fail(
                    "fixed_geometry_changed", canonical_fixed.id, "fixed geometry must not change"
                )
        for item_id in fixed.keys() - {item.id for item in self.catalog.fixed}:
            self.fail("fixed_geometry_unknown", item_id, "unknown fixed geometry")

    # --- clearance ---------------------------------------------------------------------

    def clearance(self) -> None:
        circles: list[tuple[str, float, float, float, str | None, bool]] = []
        for building in self.content.buildings:
            circles.append(
                (
                    building.id,
                    building.x,
                    building.z,
                    footprint_radius(building),
                    None,
                    building.area,
                )
            )
        for facility in self.content.facilities:
            if facility.landmark is None:
                circles.append((facility.id, facility.x, facility.z, facility.radius, None, False))
        for landmark in self.content.landmarks:
            for site_id, x, z, radius, _, _ in circles:
                if distance(x, z, landmark.x, landmark.z) < landmark.radius + radius:
                    self.fail("landmark_overlap", site_id, f"inside the grounds of {landmark.id}")
        for index, (site_id, x, z, radius, _, _) in enumerate(circles):
            for other_id, ox, oz, other_radius, _, _ in circles[index + 1 :]:
                if distance(x, z, ox, oz) < radius + other_radius:
                    self.fail("site_overlap", site_id, f"overlaps {other_id}")
        for road in self.content.roads:
            ends = self.endpoints(road)
            if ends is None:
                continue
            half = ROAD_WIDTHS[road.type] / 2
            for landmark in self.content.landmarks:
                hit = project(landmark.x, landmark.z, *ends)
                if hit.distance < landmark.radius + half and not self._tunnel_clear(
                    road, ends, landmark.x, landmark.z, landmark.radius
                ):
                    self.fail("landmark_overlap", road.id, f"road crosses {landmark.id}")
            for site_id, x, z, radius, _, is_area in circles:
                clearance = (radius - 12 if is_area else radius) + half
                hit = project(x, z, *ends)
                if hit.distance < clearance and not self._tunnel_clear(road, ends, x, z, radius):
                    self.fail("road_crosses_site", road.id, f"road crosses {site_id}")

    @staticmethod
    def _tunnel_clear(
        road: MapRoad, ends: tuple[float, float, float, float], x: float, z: float, radius: float
    ) -> bool:
        """The game lets a tunnel pass under a site if both portals stay 50 m clear."""
        ax, az, bx, bz = ends
        return road.tunnel and min(distance(x, z, ax, az), distance(x, z, bx, bz)) >= radius + 50

    # --- connectivity ------------------------------------------------------------------

    def connectivity(self) -> None:
        if any(failure.code in _STRUCTURAL for failure in self.failures):
            return
        successors: dict[str, list[str]] = {node_id: [] for node_id in self.nodes}
        for road in self.content.roads:
            successors[road.a].append(road.b)
            if road.type != "oneway":
                successors[road.b].append(road.a)

        def departures(road: MapRoad) -> set[str]:
            return {road.b} if road.type == "oneway" else {road.a, road.b}

        def arrivals(road: MapRoad) -> set[str]:
            return {road.a} if road.type == "oneway" else {road.a, road.b}

        reach_cache: dict[str, set[str]] = {}

        def reachable_from(road_id: str) -> set[str]:
            if road_id not in reach_cache:
                start = departures(self.roads[road_id])
                seen = set(start)
                queue = deque(sorted(start))
                while queue:
                    for nxt in successors[queue.popleft()]:
                        if nxt not in seen:
                            seen.add(nxt)
                            queue.append(nxt)
                reach_cache[road_id] = seen
            return reach_cache[road_id]

        def connected(from_road: str, to_road: str) -> bool:
            if from_road == to_road:
                return True
            return bool(reachable_from(from_road) & arrivals(self.roads[to_road]))

        sites: list[MapBuilding | MapFacility] = [
            *self.content.buildings,
            *self.facilities.values(),
        ]
        for site in sites:
            for department in DEPARTMENTS:
                stations = [
                    facility
                    for facility in self.content.facilities
                    if facility.department == department and facility.units
                ]
                if stations and not any(
                    connected(station.access.road, site.access.road) for station in stations
                ):
                    self.fail(
                        "unreachable_site",
                        site.id,
                        f"no {department} unit can reach {site.id} by road",
                    )
        offices = [building for building in self.content.buildings if building.type == "office"]
        for home in (b for b in self.content.buildings if b.type == "residential"):
            if not any(
                connected(home.access.road, office.access.road)
                and connected(office.access.road, home.access.road)
                for office in offices
            ):
                self.fail("no_workplace_route", home.id, "no road to a workplace and back")

    def run(self) -> None:
        self.unique_ids()
        self.roads_and_nodes()
        self.junctions()
        self.sites()
        self.departments()
        self.canonical()
        self.clearance()
        self.connectivity()


_STRUCTURAL = frozenset({"unknown_node", "unknown_access_road", "duplicate_id"})


def _segments_cross(
    ax: float, az: float, bx: float, bz: float, cx: float, cz: float, dx: float, dz: float
) -> bool:
    """Proper crossing of two segments (interiors intersect, not collinear)."""
    ux, uz, vx, vz = bx - ax, bz - az, dx - cx, dz - cz
    den = ux * vz - uz * vx
    if abs(den) < 1e-9:
        return False
    wx, wz = cx - ax, cz - az
    t = (wx * vz - wz * vx) / den
    s = (wx * uz - wz * ux) / den
    eps = 1e-6
    return eps < t < 1 - eps and eps < s < 1 - eps


def validate_content(
    content: MapContent, catalog: CanonicalCatalog
) -> tuple[list[Failure], list[Failure]]:
    """Failures and warnings of one map content (no lock comparison)."""
    checker = _Checker(content, catalog)
    checker.run()
    return checker.failures, checker.warnings


def _landmark_signature(landmark: MapLandmark) -> tuple[object, ...]:
    return (landmark.name, landmark.site, landmark.x, landmark.z, landmark.radius)


def check_locks(
    content: MapContent, base: MapRevision | None, unlock: list[str]
) -> tuple[list[Failure], list[Failure], list[str]]:
    """Lock failures, warnings and the validated unlock list of a save against its base."""
    failures: list[Failure] = []
    warnings: list[Failure] = []
    old = {landmark.id: landmark for landmark in base.content.landmarks} if base else {}
    new = {landmark.id: landmark for landmark in content.landmarks}
    granted: list[str] = []
    for landmark_id in dict.fromkeys(unlock):
        target = old.get(landmark_id) or new.get(landmark_id)
        if target is None:
            failures.append(_fail("unknown_unlock_target", landmark_id, "no such landmark"))
        elif target.kind == "canonical":
            failures.append(
                _fail("canonical_unlock_forbidden", landmark_id, "canonical landmarks stay locked")
            )
        else:
            granted.append(landmark_id)
    for landmark_id, before in old.items():
        after = new.get(landmark_id)
        if after is not None and after.kind != before.kind:
            failures.append(
                _fail("landmark_kind_changed", landmark_id, "a landmark's kind cannot change")
            )
            continue
        if not before.locked or landmark_id in granted:
            continue
        if after is None:
            failures.append(
                _fail("locked_landmark_changed", landmark_id, "a locked landmark was removed")
            )
        elif _landmark_signature(after) != _landmark_signature(before):
            failures.append(
                _fail("locked_landmark_changed", landmark_id, "a locked landmark was changed")
            )
        elif not after.locked:
            failures.append(
                _fail(
                    "unlock_not_explicit",
                    landmark_id,
                    "unlock a landmark with the save request's `unlock` list",
                )
            )
    for landmark_id, landmark in new.items():
        if landmark_id not in old and not landmark.locked and landmark_id not in granted:
            failures.append(_fail("unlock_not_explicit", landmark_id, "new landmarks start locked"))
    for landmark_id in granted:
        after = new.get(landmark_id)
        if after is not None and after.locked:
            warnings.append(
                _fail("unlock_unused", landmark_id, "listed in unlock but still locked")
            )
    return failures, warnings, granted

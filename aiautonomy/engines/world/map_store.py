"""Map persistence: shipped read-only revisions and user saves, with immutable revisions.

Layout: `<dir>/<map id>/r<revision>.json`. Shipped revisions live in `data/maps/` (read-only);
user saves in `<root>/maps/` (git-ignored; `AIA_MAPS_DIR`). Each revision is validated before
it is written, carries the SHA-256 of its content, and is never overwritten: the next revision
must name the latest one as its base (optimistic concurrency). Reading a revision re-checks its
hash, so a hand-edited file cannot be launched under its old pin.

REQ: CITY-01, CITY-03, CITY-04, CITY-05
"""

import re
from dataclasses import dataclass
from pathlib import Path

from aiautonomy.engines.contract.common import Failure
from aiautonomy.engines.contract.maps import (
    MapContent,
    MapRef,
    MapRevision,
    MapRevisionSummary,
    MapSummary,
    MapValidationReport,
)
from aiautonomy.engines.world.map_validation import check_locks, validate_content
from aiautonomy.engines.world.maps import (
    CanonicalCatalog,
    content_sha256,
    read_revision,
    write_revision_exclusive,
)

_REVISION_FILE = re.compile(r"^r(?P<revision>[1-9][0-9]{0,5})\.json$")


class MapStoreError(Exception):
    """A map request that conflicts with the stored maps (HTTP 404 or 409)."""

    def __init__(
        self, status: int, code: str, message: str, failures: list[Failure] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.failures = failures or []


@dataclass(frozen=True, slots=True)
class _Location:
    directory: Path
    read_only: bool


class MapStore:
    def __init__(self, shipped_dir: Path, user_dir: Path, catalog: CanonicalCatalog) -> None:
        self.shipped = _Location(shipped_dir, read_only=True)
        self.user = _Location(user_dir, read_only=False)
        self.catalog = catalog

    # --- reading ---------------------------------------------------------------------

    def _location(self, map_id: str) -> _Location | None:
        for location in (self.shipped, self.user):
            if (location.directory / map_id).is_dir():
                return location
        return None

    def _revision_numbers(self, location: _Location, map_id: str) -> list[int]:
        directory = location.directory / map_id
        numbers = []
        for path in directory.glob("r*.json"):
            match = _REVISION_FILE.match(path.name)
            if match:
                numbers.append(int(match["revision"]))
        return sorted(numbers)

    def get(self, map_id: str, revision: int) -> MapRevision:
        location = self._location(map_id)
        path = location.directory / map_id / f"r{revision}.json" if location else None
        if path is None or not path.is_file():
            raise MapStoreError(404, "unknown_map", f"no revision {revision} of map {map_id!r}")
        try:
            document = read_revision(path)
        except ValueError as exc:
            raise MapStoreError(409, "map_corrupt", f"{path.name}: unreadable: {exc}") from exc
        if (document.id, document.revision) != (map_id, revision):
            raise MapStoreError(409, "map_corrupt", f"{path} names another map or revision")
        if content_sha256(document.content) != document.sha256:
            raise MapStoreError(409, "map_corrupt", f"{path}: content does not match its sha256")
        return document

    def latest(self, map_id: str) -> MapRevision:
        location = self._location(map_id)
        numbers = self._revision_numbers(location, map_id) if location else []
        if not numbers:
            raise MapStoreError(404, "unknown_map", f"no map {map_id!r}")
        return self.get(map_id, numbers[-1])

    def resolve(self, ref: MapRef) -> MapRevision:
        """The pinned revision; its stored hash must equal the pin (launch and replay)."""
        revision = self.get(ref.id, ref.revision)
        if revision.sha256 != ref.sha256:
            raise MapStoreError(
                409,
                "map_sha_mismatch",
                f"{ref.id} r{ref.revision} has sha256 {revision.sha256}, not {ref.sha256}",
            )
        return revision

    def summaries(self) -> list[MapSummary]:
        summaries: list[MapSummary] = []
        seen: set[str] = set()
        for location in (self.shipped, self.user):
            if not location.directory.is_dir():
                continue
            for directory in sorted(p for p in location.directory.iterdir() if p.is_dir()):
                if directory.name in seen:
                    continue
                revisions = []
                for number in self._revision_numbers(location, directory.name):
                    try:
                        document = self.get(directory.name, number)
                    except MapStoreError:
                        continue
                    revisions.append(
                        MapRevisionSummary(
                            revision=document.revision,
                            name=document.name,
                            sha256=document.sha256,
                            parent=document.parent,
                        )
                    )
                if not revisions:
                    continue
                seen.add(directory.name)
                first = self.get(directory.name, revisions[0].revision)
                summaries.append(
                    MapSummary(
                        id=directory.name,
                        kind="template" if first.parent is None else "saved",
                        read_only=location.read_only,
                        revisions=revisions,
                    )
                )
        return summaries

    # --- validation and saving ---------------------------------------------------------

    def validate(
        self, content: MapContent, base: MapRevision | None, unlock: list[str]
    ) -> tuple[MapValidationReport, list[str]]:
        failures, warnings = validate_content(content, self.catalog)
        lock_failures, lock_warnings, granted = check_locks(content, base, unlock)
        report = MapValidationReport(
            ok=not failures and not lock_failures,
            sha256=content_sha256(content),
            failures=[*lock_failures, *failures],
            warnings=[*lock_warnings, *warnings],
        )
        return report, granted

    def _save(
        self,
        map_id: str,
        revision: int,
        name: str,
        parent: MapRef | None,
        base: MapRevision | None,
        content: MapContent,
        unlock: list[str],
    ) -> MapRevision:
        report, granted = self.validate(content, base, unlock)
        if not report.ok:
            raise MapStoreError(
                422, report.failures[0].code, "the map is not valid", report.failures
            )
        document = MapRevision(
            id=map_id,
            revision=revision,
            name=name,
            parent=parent,
            sha256=report.sha256,
            unlocked=granted,
            content=content,
        )
        path = self.user.directory / map_id / f"r{revision}.json"
        try:
            write_revision_exclusive(path, document)
        except FileExistsError as exc:
            raise MapStoreError(
                409, "base_not_latest", f"revision {revision} of {map_id!r} already exists"
            ) from exc
        return document

    def create(
        self,
        map_id: str,
        name: str,
        parent: MapRef | None,
        content: MapContent,
        unlock: list[str],
    ) -> MapRevision:
        """Save revision 1 of a new map; a parent is checked like a base (its locks hold)."""
        if self._location(map_id) is not None:
            raise MapStoreError(409, "map_exists", f"map {map_id!r} already exists")
        base = self.resolve(parent) if parent is not None else None
        return self._save(map_id, 1, name, parent, base, content, unlock)

    def revise(
        self,
        map_id: str,
        name: str | None,
        base_ref: MapRef,
        content: MapContent,
        unlock: list[str],
    ) -> MapRevision:
        """Save the next revision; `base_ref` must pin the latest revision of `map_id`."""
        location = self._location(map_id)
        if location is None:
            raise MapStoreError(404, "unknown_map", f"no map {map_id!r}")
        if location.read_only:
            raise MapStoreError(
                409, "read_only_map", f"{map_id!r} is shipped read-only; save a new map from it"
            )
        if base_ref.id != map_id:
            raise MapStoreError(409, "base_not_latest", "base must be a revision of this map")
        latest = self.latest(map_id)
        if base_ref.revision != latest.revision:
            raise MapStoreError(
                409,
                "base_not_latest",
                f"base is r{base_ref.revision} but the latest is r{latest.revision}",
            )
        base = self.resolve(base_ref)
        return self._save(
            map_id, latest.revision + 1, name or base.name, base_ref, base, content, unlock
        )

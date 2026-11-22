"""Map validation, landmark locks and persistence (docs/contract.md §2)."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from aiautonomy.engines.contract.maps import MapContent, MapRef, MapRevision
from aiautonomy.engines.core.paths import repo_root
from aiautonomy.engines.world.map_store import MapStore, MapStoreError
from aiautonomy.engines.world.maps import canonical_catalog, content_sha256

TEMPLATE = ("boston-template", 1)
VARIANT = ("boston-variant", 1)
USER_LANDMARK = "lm-old-west-church"


@pytest.fixture
def store(tmp_path: Path) -> MapStore:
    return MapStore(repo_root() / "data" / "maps", tmp_path / "maps", canonical_catalog().catalog)


def ref(revision: MapRevision) -> MapRef:
    return MapRef(id=revision.id, revision=revision.revision, sha256=revision.sha256)


def mutate(content: MapContent, change: Callable[[dict[str, Any]], None]) -> MapContent:
    data = content.model_dump(mode="json")
    change(data)
    return MapContent.model_validate(data)


def entity(items: list[dict[str, Any]], entity_id: str) -> dict[str, Any]:
    return next(item for item in items if item["id"] == entity_id)


def codes(store: MapStore, content: MapContent, base: MapRevision | None = None) -> set[str]:
    report, _ = store.validate(content, base, [])
    return {failure.code for failure in report.failures}


@pytest.mark.req("CITY-01", "CITY-05")
def test_shipped_maps_are_valid_and_pinned(store: MapStore) -> None:
    template, variant = store.get(*TEMPLATE), store.get(*VARIANT)
    for revision in (template, variant):
        report, _ = store.validate(revision.content, None, [])
        assert report.ok, report.failures
        assert revision.sha256 == content_sha256(revision.content) == report.sha256
    assert variant.parent == ref(template)
    report, granted = store.validate(variant.content, template, [])
    assert report.ok
    assert granted == []
    roads = {road.id for road in template.content.roads}
    assert "rd-cambridge-mid" in roads
    assert roads - {road.id for road in variant.content.roads} == {"rd-cambridge-mid"}
    landmark = next(lm for lm in variant.content.landmarks if lm.id == USER_LANDMARK)
    assert (landmark.kind, landmark.locked) == ("user", True)
    summaries = {summary.id: summary for summary in store.summaries()}
    assert summaries["boston-template"].kind == "template"
    assert summaries["boston-variant"].kind == "saved"
    assert summaries["boston-template"].read_only
    assert summaries["boston-variant"].read_only
    departments = {facility.department for facility in template.content.facilities}
    assert departments == {"police", "fire", "medical"}


def test_content_hash_ignores_key_order_and_omitted_defaults(store: MapStore) -> None:
    content = store.get(*TEMPLATE).content
    data = content.model_dump(mode="json")
    for road in data["roads"]:
        road.pop("bridge")
        road.pop("tunnel")
    shuffled = json.loads(json.dumps(data, sort_keys=True))
    assert content_sha256(MapContent.model_validate(shuffled)) == content_sha256(content)


def _add_node(data: dict[str, Any], node_id: str, x: float, z: float) -> None:
    data["nodes"].append({"id": node_id, "x": x, "z": z})


def _add_road(data: dict[str, Any], road_id: str, a: str, b: str) -> None:
    data["roads"].append({"id": road_id, "name": "", "a": a, "b": b, "type": "twoway",
                          "bridge": False, "tunnel": False})  # fmt: skip


def _add_crossing(data: dict[str, Any]) -> None:
    _add_node(data, "n-x1", -60.0, 570.0)
    _add_node(data, "n-x2", -60.0, 640.0)
    _add_road(data, "rd-x", "n-x1", "n-x2")


def _add_t(data: dict[str, Any]) -> None:
    _add_node(data, "n-t1", -60.0, 560.0)
    _add_node(data, "n-t2", -60.0, 600.0)
    _add_road(data, "rd-t", "n-t1", "n-t2")


def _road_through_city_hall(data: dict[str, Any]) -> None:
    _add_node(data, "n-h1", 560.0, 640.0)
    _add_node(data, "n-h2", 640.0, 640.0)
    _add_road(data, "rd-h", "n-h1", "n-h2")


def _building(data: dict[str, Any], building_id: str, kind: str, x: float, z: float) -> None:
    data["buildings"].append({"id": building_id, "type": kind, "label": "", "x": x, "z": z,
                              "rotation": 0.0, "radius": None, "area": False,
                              "access": {"road": "rd-court"}})  # fmt: skip


def _isolate_mgh(data: dict[str, Any]) -> None:
    _add_node(data, "n-mgh-b", -312.5, 520.0)
    entity(data["roads"], "rd-mgh-spur")["b"] = "n-mgh-b"


INVALID: dict[str, tuple[Callable[[dict[str, Any]], None], str]] = {
    "unknown node": (lambda d: entity(d["roads"], "rd-congress").update(b="n-nowhere"),
                     "unknown_node"),
    "degenerate road": (lambda d: entity(d["roads"], "rd-congress").update(b="n-gc"),
                        "degenerate_road"),
    "duplicate id": (lambda d: entity(d["nodes"], "n-gc").update(id="rd-court"), "duplicate_id"),
    "out of bounds": (lambda d: entity(d["nodes"], "n-court-east").update(x=2000.0),
                      "out_of_bounds"),
    "unknown access road": (lambda d: entity(d["buildings"], "beacon")["access"].update(
        road="rd-gone"), "unknown_access_road"),
    "driveway too far": (lambda d: entity(d["facilities"], "fac-pd-a1").update(x=465.0),
                         "access_too_far"),
    "driveway facing away": (lambda d: entity(d["facilities"], "fac-pd-a1").update(
        x=510.0, rotation=0.0), "access_facing_away"),
    "no fire units": (lambda d: entity(d["facilities"], "fac-fd-e4").update(units=[]),
                      "missing_department"),
    "isolated hospital": (_isolate_mgh, "unreachable_site"),
    "no commute": (lambda d: entity(d["roads"], "rd-congress").update(type="oneway"),
                   "no_workplace_route"),
    "building on the State House": (lambda d: _building(d, "b-sh", "park", 99.0, 802.0),
                                    "landmark_overlap"),
    "road through City Hall": (_road_through_city_hall, "landmark_overlap"),
    "City Hall moved": (lambda d: entity(d["landmarks"], "lm-city-hall").update(
        x=entity(d["landmarks"], "lm-city-hall")["x"] + 5), "canonical_landmark_changed"),
    "City Hall unlocked": (lambda d: entity(d["landmarks"], "lm-city-hall").update(locked=False),
                           "canonical_landmark_changed"),
    "State House removed": (lambda d: d["landmarks"].remove(entity(d["landmarks"],
                            "lm-state-house")), "canonical_landmark_missing"),
    "district moved": (lambda d: entity(d["buildings"], "beacon").update(
        z=entity(d["buildings"], "beacon")["z"] + 10), "canonical_area_changed"),
    "district removed": (lambda d: d["buildings"].remove(entity(d["buildings"], "government")),
                         "canonical_area_missing"),
    "I-93 changed": (lambda d: d["fixed"][0].update(sha256="0" * 64), "fixed_geometry_changed"),
    "unjoined crossing": (_add_crossing, "unjoined_crossing"),
    "unjoined T junction": (_add_t, "unjoined_junction"),
    "police in the hospital": (lambda d: entity(d["facilities"], "fac-pd-a1").update(
        landmark="lm-mass-general"), "facility_landmark_forbidden"),
    "unknown mayor office": (lambda d: d.update(mayor_office="lm-nowhere"),
                             "unknown_mayor_office"),
    "overlapping sites": (lambda d: _building(d, "b-shop", "shop", 505.0, 485.0), "site_overlap"),
    "road through a district": (lambda d: entity(d["nodes"], "n-gc-north").update(x=420.0),
                                "road_crosses_site"),
}  # fmt: skip


@pytest.mark.req("CITY-05")
@pytest.mark.parametrize("case", sorted(INVALID))
def test_invalid_maps_are_rejected_with_a_code(store: MapStore, case: str) -> None:
    change, code = INVALID[case]
    content = mutate(store.get(*TEMPLATE).content, change)
    assert code in codes(store, content)


# --- locks -------------------------------------------------------------------------------


def _user_landmark(data: dict[str, Any]) -> dict[str, Any]:
    return entity(data["landmarks"], USER_LANDMARK)


LOCK_BREAKS: dict[str, tuple[Callable[[dict[str, Any]], None], str]] = {
    "removed": (lambda d: d["landmarks"].remove(_user_landmark(d)), "locked_landmark_changed"),
    "moved": (lambda d: _user_landmark(d).update(x=-40.0), "locked_landmark_changed"),
    "resized": (lambda d: _user_landmark(d).update(radius=5.0), "locked_landmark_changed"),
    "renamed": (lambda d: _user_landmark(d).update(name="Old Church"), "locked_landmark_changed"),
    "re-identified": (lambda d: _user_landmark(d).update(id="lm-old-west-church-2"),
                      "locked_landmark_changed"),
    "silently unlocked": (lambda d: _user_landmark(d).update(locked=False),
                          "unlock_not_explicit"),
    "made canonical": (lambda d: _user_landmark(d).update(kind="canonical"),
                       "landmark_kind_changed"),
}  # fmt: skip


@pytest.mark.req("CITY-03")
@pytest.mark.parametrize("case", sorted(LOCK_BREAKS))
def test_indirect_edits_cannot_bypass_a_lock(store: MapStore, case: str) -> None:
    variant = store.get(*VARIANT)
    change, code = LOCK_BREAKS[case]
    content = mutate(variant.content, change)
    assert code in codes(store, content, variant)
    # Saving it as a new map derived from the variant does not escape the lock either.
    with pytest.raises(MapStoreError) as raised:
        store.create("escape-attempt", "Escape", ref(variant), content, [])
    assert raised.value.status == 422
    assert code in {failure.code for failure in raised.value.failures}


@pytest.mark.req("CITY-03")
def test_canonical_landmarks_can_never_be_unlocked(store: MapStore) -> None:
    variant = store.get(*VARIANT)
    report, granted = store.validate(variant.content, variant, ["lm-city-hall"])
    assert not report.ok
    assert granted == []
    assert "canonical_unlock_forbidden" in {failure.code for failure in report.failures}


@pytest.mark.req("CITY-03")
def test_explicit_unlock_in_setup_then_free_edits(store: MapStore) -> None:
    variant = store.get(*VARIANT)
    first = store.create("my-boston", "My Boston", ref(variant), variant.content, [])
    unlocked = mutate(first.content, lambda d: _user_landmark(d).update(locked=False))
    second = store.revise("my-boston", None, ref(first), unlocked, [USER_LANDMARK])
    assert second.unlocked == [USER_LANDMARK]
    assert second.parent == ref(first)
    assert second.name == "My Boston"
    removed = mutate(second.content, lambda d: d["landmarks"].remove(_user_landmark(d)))
    third = store.revise("my-boston", "Without the church", ref(second), removed, [])
    assert USER_LANDMARK not in {landmark.id for landmark in third.content.landmarks}
    assert third.revision == 3


def test_new_user_landmarks_start_locked(store: MapStore) -> None:
    template = store.get(*TEMPLATE)

    def add(data: dict[str, Any]) -> None:
        landmark = {"id": "lm-mine", "name": "Mine", "kind": "user", "site": None}
        data["landmarks"].append(
            landmark | {"x": -49.3, "z": 512.1, "radius": 20.0, "locked": False}
        )

    assert "unlock_not_explicit" in codes(store, mutate(template.content, add), template)
    report, _ = store.validate(store.get(*VARIANT).content, None, [USER_LANDMARK])
    assert "unlock_unused" in {warning.code for warning in report.warnings}


# --- store -------------------------------------------------------------------------------


def test_save_reopen_and_revise_with_optimistic_concurrency(
    store: MapStore, tmp_path: Path
) -> None:
    template = store.get(*TEMPLATE)
    saved = store.create("demo", "Demo city", ref(template), template.content, [])
    assert (tmp_path / "maps" / "demo" / "r1.json").is_file()
    assert store.get("demo", 1) == saved
    assert store.latest("demo").revision == 1
    second = store.revise("demo", "Demo city v2", ref(saved), saved.content, [])
    with pytest.raises(MapStoreError) as stale:
        store.revise("demo", None, ref(saved), saved.content, [])
    assert (stale.value.status, stale.value.code) == (409, "base_not_latest")
    assert store.resolve(ref(second)) == second
    ids = {summary.id: summary for summary in store.summaries()}
    assert not ids["demo"].read_only
    assert [item.revision for item in ids["demo"].revisions] == [1, 2]


def test_store_refusals(store: MapStore, tmp_path: Path) -> None:
    template = store.get(*TEMPLATE)
    cases = [
        (lambda: store.revise("boston-template", None, ref(template), template.content, []),
         409, "read_only_map"),
        (lambda: store.create("boston-template", "Copy", None, template.content, []),
         409, "map_exists"),
        (lambda: store.get("nope", 1), 404, "unknown_map"),
        (lambda: store.resolve(MapRef(id="boston-template", revision=1, sha256="1" * 64)),
         409, "map_sha_mismatch"),
    ]  # fmt: skip
    for call, status, code in cases:
        with pytest.raises(MapStoreError) as raised:
            call()
        assert (raised.value.status, raised.value.code) == (status, code)
    saved = store.create("tamper", "Tamper", None, template.content, [])
    path = tmp_path / "maps" / "tamper" / "r1.json"
    data = json.loads(path.read_text())
    data["content"]["nodes"][0]["x"] += 1
    path.write_text(json.dumps(data))
    with pytest.raises(MapStoreError) as corrupt:
        store.get("tamper", 1)
    assert corrupt.value.code == "map_corrupt"
    assert "tamper" not in {summary.id for summary in store.summaries()}
    assert saved.sha256 == template.sha256


def test_invalid_saves_report_every_failure(store: MapStore) -> None:
    template = store.get(*TEMPLATE)
    broken = mutate(
        template.content, lambda d: entity(d["facilities"], "fac-fd-e4").update(units=[])
    )
    with pytest.raises(MapStoreError) as raised:
        store.create("broken", "Broken", None, broken, [])
    assert raised.value.status == 422
    assert "missing_department" in {failure.code for failure in raised.value.failures}

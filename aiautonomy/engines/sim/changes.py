"""World-view diffs published as protocol changes (plans/R1.md §4.8).

A change is `{"op": "upsert", "collection", "id", "value"}`, `{"op": "remove",
"collection", "id"}` or `{"op": "set", "field", "value"}`. Each replaces whole values, so
coalescing several ticks keeps only the last change per key.

REQ: ARCH-03
"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

type Change = dict[str, Any]
type ChangeKey = tuple[str, ...]


def diff_views(
    before: Mapping[str, Any], after: Mapping[str, Any], collections: Sequence[str]
) -> list[Change]:
    """Changes turning view `before` into `after`: singleton sets first, then collections."""
    changes: list[Change] = []
    for name in sorted(after):
        if name in collections or before.get(name) == after[name]:
            continue
        changes.append({"op": "set", "field": name, "value": after[name]})
    for collection in sorted(collections):
        old: Mapping[str, Any] = before.get(collection, {})
        new: Mapping[str, Any] = after.get(collection, {})
        for entity_id in sorted(new):
            if old.get(entity_id) != new[entity_id]:
                changes.append(
                    {
                        "op": "upsert",
                        "collection": collection,
                        "id": entity_id,
                        "value": new[entity_id],
                    }
                )
        for entity_id in sorted(old):
            if entity_id not in new:
                changes.append({"op": "remove", "collection": collection, "id": entity_id})
    return changes


def change_key(change: Change) -> ChangeKey:
    if change["op"] == "set":
        return ("set", change["field"])
    return ("entity", change["collection"], change["id"])


def coalesce(pending: dict[ChangeKey, Change], changes: Iterable[Change]) -> None:
    """Fold `changes` into `pending`, keeping only the latest change per field or entity."""
    for change in changes:
        key = change_key(change)
        pending.pop(key, None)
        pending[key] = change

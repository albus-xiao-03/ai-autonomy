"""Versioned catalogs a hybrid run loads and records: incident kinds and their dispatch needs.

Each catalog is a data file with `id`, `version` and `schema_version`; the run manifest
records its path and SHA-256, so a replay can tell when a catalog changed.

REQ: SRV-01, SRV-07, MAY-04
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Self, get_args

from pydantic import model_validator

from aiautonomy.engines.contract.dispatch import IncidentKind, IncidentKindSpec
from aiautonomy.engines.core.datafiles import DataFileModel, DataFileRef, load_data_file

DISPATCH_CATALOG = Path("data/catalogs/dispatch.v1.yaml")


class DispatchCatalog(DataFileModel):
    """`data/catalogs/dispatch.v1.yaml`: one entry per incident kind."""

    title: str
    kinds: list[IncidentKindSpec]

    @model_validator(mode="after")
    def _every_kind_once(self) -> Self:
        kinds = [spec.kind for spec in self.kinds]
        if sorted(kinds) != sorted(get_args(IncidentKind)):
            raise ValueError("the dispatch catalog must list every incident kind exactly once")
        return self

    def spec(self, kind: str) -> IncidentKindSpec:
        for spec in self.kinds:
            if spec.kind == kind:
                return spec
        raise KeyError(kind)


@dataclass(frozen=True, slots=True)
class Catalogs:
    dispatch: DispatchCatalog
    refs: tuple[DataFileRef, ...]


@cache
def _load(root: str) -> Catalogs:
    base = Path(root)
    dispatch = load_data_file(base / DISPATCH_CATALOG, DispatchCatalog, root=base)
    return Catalogs(dispatch=dispatch.model, refs=(dispatch.ref,))


def load_catalogs(root: Path) -> Catalogs:
    """The catalogs of `root`, loaded once per process."""
    return _load(str(root.resolve()))

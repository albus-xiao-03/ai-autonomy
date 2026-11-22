"""Versioned data files (plans/R1.md §4.6).

Every data file (configuration, scenario, map, catalog, rule set, metric definition, prompt)
carries `id`, `version` and `schema_version`. Loaders validate it with pydantic and compute
the sha256 of its exact bytes; the run manifest records the resulting `DataFileRef`s.

REQ: SIM-04
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class DataFileError(ValueError):
    """A data file is missing, unparsable, invalid or of an unsupported schema version."""


class DataFileModel(BaseModel):
    """Base model of every data file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    SCHEMA_VERSIONS: ClassVar[frozenset[int]] = frozenset({1})

    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=64)
    version: int = Field(ge=1)
    schema_version: int = Field(ge=1)


class DataFileRef(BaseModel):
    """What the manifest records about one loaded data file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    version: int
    schema_version: int
    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class LoadedDataFile[M: DataFileModel]:
    model: M
    ref: DataFileRef


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse(path: Path, raw: bytes) -> Any:
    try:
        if path.suffix in {".yaml", ".yml"}:
            return yaml.safe_load(raw)
        if path.suffix == ".json":
            return json.loads(raw)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise DataFileError(f"{path}: cannot parse: {exc}") from exc
    raise DataFileError(f"{path}: unsupported data file type {path.suffix!r}")


def _display_path(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def load_data_file[M: DataFileModel](
    path: Path, model: type[M], *, root: Path | None = None
) -> LoadedDataFile[M]:
    """Load, validate and fingerprint one data file.

    `root` makes the recorded path repository-relative.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DataFileError(f"{path}: cannot read: {exc}") from exc
    data = _parse(path, raw)
    if not isinstance(data, dict):
        raise DataFileError(f"{path}: top level must be a mapping")
    try:
        parsed = model.model_validate(data)
    except ValidationError as exc:
        raise DataFileError(f"{path}: invalid {model.__name__}: {exc}") from exc
    if parsed.schema_version not in model.SCHEMA_VERSIONS:
        raise DataFileError(
            f"{path}: schema_version {parsed.schema_version} not supported by "
            f"{model.__name__} (supported: {sorted(model.SCHEMA_VERSIONS)})"
        )
    ref = DataFileRef(
        id=parsed.id,
        version=parsed.version,
        schema_version=parsed.schema_version,
        path=_display_path(path, root),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    return LoadedDataFile(model=parsed, ref=ref)

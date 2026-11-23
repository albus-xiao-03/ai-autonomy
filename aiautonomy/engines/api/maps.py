"""Map routes (`/api/maps`, docs/contract.md §2): list, reopen, save, revise and validate.

REQ: CITY-01, CITY-03, CITY-05
"""

from typing import Annotated

from fastapi import APIRouter, Path, Request

from aiautonomy.engines.contract.maps import (
    MapCreateRequest,
    MapList,
    MapRevision,
    MapRevisionRequest,
    MapValidateRequest,
    MapValidationReport,
)
from aiautonomy.engines.world.map_store import MapStore

router = APIRouter(prefix="/api/maps")

MapIdPath = Annotated[str, Path(pattern=r"^[a-z][a-z0-9-]*$", max_length=64)]
RevisionPath = Annotated[int, Path(ge=1, le=999_999)]


def _store(request: Request) -> MapStore:
    store: MapStore = request.app.state.maps
    return store


@router.get("")
async def list_maps(request: Request) -> MapList:
    return MapList(maps=_store(request).summaries())


@router.post("/validate")
async def validate_map(request: Request, body: MapValidateRequest) -> MapValidationReport:
    store = _store(request)
    base = store.resolve(body.base) if body.base is not None else None
    report, _ = store.validate(body.content, base, body.unlock)
    return report


@router.get("/{map_id}/revisions/{revision}")
async def get_revision(request: Request, map_id: MapIdPath, revision: RevisionPath) -> MapRevision:
    return _store(request).get(map_id, revision)


@router.post("", status_code=201)
async def create_map(request: Request, body: MapCreateRequest) -> MapRevision:
    return _store(request).create(body.id, body.name, body.parent, body.content, body.unlock)


@router.post("/{map_id}/revisions", status_code=201)
async def revise_map(request: Request, map_id: MapIdPath, body: MapRevisionRequest) -> MapRevision:
    return _store(request).revise(map_id, body.name, body.base, body.content, body.unlock)

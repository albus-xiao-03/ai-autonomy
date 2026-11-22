"""Catalog routes (`/api/catalogs/*`, docs/contract.md §5 and §8).

REQ: SRV-07, EVT-02
"""

from pathlib import Path

from fastapi import APIRouter, Request

from aiautonomy.engines.contract.dispatch import IncidentCatalogView
from aiautonomy.engines.contract.disruptions import DisruptionCatalogView
from aiautonomy.engines.hybrid.catalogs import load_catalogs

router = APIRouter(prefix="/api/catalogs")


def _root(request: Request) -> Path:
    root: Path = request.app.state.root
    return root


@router.get("/incidents")
async def incident_catalog(request: Request) -> IncidentCatalogView:
    catalogs = load_catalogs(_root(request))
    ref = catalogs.refs[0]
    return IncidentCatalogView(
        version=catalogs.dispatch.version, sha256=ref.sha256, kinds=catalogs.dispatch.kinds
    )


@router.get("/disruptions")
async def disruption_catalog(request: Request) -> DisruptionCatalogView:
    catalogs = load_catalogs(_root(request))
    ref = catalogs.refs[1]
    return DisruptionCatalogView(
        version=ref.version, sha256=ref.sha256, types=list(catalogs.disruptions)
    )

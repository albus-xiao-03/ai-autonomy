"""Hybrid run routes (`/api/runs`, docs/contract.md §3–§10).

REQ: SIM-03, SIM-05, ARCH-02, ARCH-03
"""

from typing import Annotated

from fastapi import APIRouter, Path, Request

from aiautonomy.engines.contract.runs import (
    EpochRequest,
    RunHandle,
    RunLaunchRequest,
    RunSummary,
    TickObservation,
    TickOutcome,
)
from aiautonomy.engines.hybrid.store import RunStore

router = APIRouter(prefix="/api/runs")

RunIdPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9._:-]{1,128}$")]


def _runs(request: Request) -> RunStore:
    store: RunStore = request.app.state.runs
    return store


@router.post("", status_code=201)
async def launch_run(request: Request, body: RunLaunchRequest) -> RunHandle:
    return _runs(request).launch(body).handle_view()


@router.get("/{run_id}")
async def get_run(request: Request, run_id: RunIdPath) -> RunSummary:
    return _runs(request).get(run_id).summary()


@router.post("/{run_id}/ticks")
async def post_tick(request: Request, run_id: RunIdPath, body: TickObservation) -> TickOutcome:
    store = _runs(request)
    run = store.get(run_id)
    async with store.lock(run_id):
        return await run.handle(body)


@router.post("/{run_id}/reset", status_code=201)
async def reset_run(request: Request, run_id: RunIdPath, body: EpochRequest) -> RunHandle:
    return _runs(request).reset(run_id, body.run_epoch).handle_view()


@router.post("/{run_id}/cancel")
async def cancel_run(request: Request, run_id: RunIdPath, body: EpochRequest) -> RunSummary:
    return _runs(request).cancel(run_id, body.run_epoch).summary()

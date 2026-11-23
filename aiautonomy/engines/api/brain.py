"""REST routes the current browser game calls for AI decisions (`/api/brain/*`, transitional).

The browser game owns the physical city. Until it adopts the run routes (`/api/runs`,
docs/contract.md), it asks the engine for one-off mayor orders and resident decisions here.

Records are run-scoped, not process-global: every app keeps a `LegacyLog` on its state, keyed
by run. A request may name a live hybrid run (`run_id` + `run_epoch`): its decisions are
recorded with that run, and a stale epoch or ended run is refused. Without a run id they go to
the app's `legacy` run. Decision ids count from 0 within each run, and an outcome must name a
decision of that run. Reposting the same score is idempotent; a different one is a conflict.

REQ: ARCH-02, SIM-05, MAY-07, MAY-08
"""

from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from aiautonomy.engines.agents.ollama import OllamaClient, OllamaError
from aiautonomy.engines.contract.common import ErrorResponse, Failure
from aiautonomy.engines.mayor import backends
from aiautonomy.engines.residents import llm

router = APIRouter(prefix="/api/brain")
LEGACY_RUN = "legacy"
LIST_LIMIT = 50


@dataclass(slots=True)
class LegacyLog:
    """Legacy mayor decisions, per run."""

    runs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def append(self, run_key: str, entry: dict[str, Any]) -> dict[str, Any]:
        entries = self.runs.setdefault(run_key, [])
        entry = entry | {"id": len(entries), "run_id": run_key}
        entry["decision_id"] = f"legacy-{entry['id']}"
        entries.append(entry)
        return entry

    def get(self, run_key: str, decision: int) -> dict[str, Any] | None:
        entries = self.runs.get(run_key, [])
        return entries[decision] if 0 <= decision < len(entries) else None

    def entries(self, run_key: str) -> list[dict[str, Any]]:
        return self.runs.get(run_key, [])[-LIST_LIMIT:]


def _log(request: Request) -> LegacyLog:
    log = getattr(request.app.state, "legacy", None)
    if log is None:
        log = LegacyLog()
        request.app.state.legacy = log
    return log


def _error(status: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=Failure(code=code, message=message))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


class MayorRequest(BaseModel):
    backend: str = "local"
    model: str | None = None
    prompt: dict[str, Any] = Field(default_factory=dict)
    allowed: list[str] = Field(default_factory=list)
    fallback: str = "monitor"
    run_id: str | None = Field(default=None, max_length=128)
    run_epoch: int | None = Field(default=None, ge=1)


class ResidentRequest(BaseModel):
    model: str | None = None
    residents: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class OutcomeRequest(BaseModel):
    id: int = Field(ge=0)
    score_after: float = Field(ge=0, le=100, allow_inf_nan=False)
    run_id: str | None = Field(default=None, max_length=128)


def _hybrid_run(request: Request, run_id: str, run_epoch: int | None) -> Any:
    """The live hybrid run a legacy request names, or an error response."""
    store = getattr(request.app.state, "runs", None)
    run = store.runs.get(run_id) if store is not None else None
    if run is None:
        return _error(404, "unknown_run", f"no live run {run_id!r}")
    if run_epoch != run.run_epoch:
        return _error(409, "stale_epoch", f"run {run_id} is at epoch {run.run_epoch}")
    if run.status != "running":
        return _error(409, "run_ended", f"run {run_id} ended ({run.status})")
    return run


@router.get("/status")
async def status() -> dict[str, Any]:
    try:
        models = await OllamaClient("status").models()
        ollama = True
    except OllamaError:
        models, ollama = [], False
    return {
        "ok": True,
        "ollama": ollama,
        "models": models,
        "api_available": backends.api_available(),
        "api_model": backends.API_MODEL,
        "mayor_backends": ["baseline", "local", "api"],
        "resident_model": llm.RESIDENT_MODEL,
        "resident_actions": {"lawful": llm.LAWFUL, "unlawful": llm.UNLAWFUL},
    }


@router.post("/mayor", response_model=None)
async def mayor(request: Request, body: MayorRequest) -> dict[str, Any] | JSONResponse:
    run = None
    if body.run_id is not None:
        run = _hybrid_run(request, body.run_id, body.run_epoch)
        if isinstance(run, JSONResponse):
            return run
    decision = await backends.decide(
        body.backend, body.prompt, body.allowed, body.fallback, body.model
    )
    entry = decision.to_json() | {
        "minute": body.prompt.get("minute"),
        "score_before": body.prompt.get("satisfaction"),
        "score_after": None,
    }
    if run is not None and run.status != "running":  # reset while the model answered
        return _error(409, "run_ended", f"run {body.run_id} ended ({run.status})")
    entry = _log(request).append(body.run_id or LEGACY_RUN, entry)
    if run is not None:
        for sink in run.sinks:
            sink.on_decision(run, {"kind": "legacy_mayor", "record": entry})
    return entry


@router.post("/mayor/outcome", response_model=None)
async def mayor_outcome(request: Request, body: OutcomeRequest) -> dict[str, Any] | JSONResponse:
    run_key = body.run_id or LEGACY_RUN
    entry = _log(request).get(run_key, body.id)
    if entry is None:
        return _error(404, "unknown_decision", f"no decision {body.id} in run {run_key!r}")
    if entry["score_after"] is None:
        entry["score_after"] = body.score_after
    elif entry["score_after"] != body.score_after:
        return _error(409, "outcome_conflict", "a different outcome was already recorded")
    return entry


@router.get("/decisions")
async def decisions(request: Request, run_id: str | None = None) -> list[dict[str, Any]]:
    return _log(request).entries(run_id or LEGACY_RUN)


@router.post("/residents")
async def residents(body: ResidentRequest) -> dict[str, Any]:
    return await llm.decide(body.residents, body.context, body.model)

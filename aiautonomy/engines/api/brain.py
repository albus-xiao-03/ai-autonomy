"""REST routes the browser game calls for AI decisions (`/api/brain/*`).

The browser game owns the physical city (map, roads, traffic, incidents). The engine owns the
decision-makers: the mayor (baseline, local Ollama or Anthropic API) and LLM residents
(local Ollama only). It also keeps an in-memory log of mayor decisions with score before/after.
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from aiautonomy.engines.agents.ollama import OllamaClient, OllamaError
from aiautonomy.engines.mayor import backends
from aiautonomy.engines.residents import llm

router = APIRouter(prefix="/api/brain")
_LOG: list[dict[str, Any]] = []


class MayorRequest(BaseModel):
    backend: str = "local"
    model: str | None = None
    prompt: dict[str, Any] = Field(default_factory=dict)
    allowed: list[str] = Field(default_factory=list)
    fallback: str = "monitor"


class ResidentRequest(BaseModel):
    model: str | None = None
    residents: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class OutcomeRequest(BaseModel):
    id: int
    score_after: float


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


@router.post("/mayor")
async def mayor(request: MayorRequest) -> dict[str, Any]:
    decision = await backends.decide(
        request.backend, request.prompt, request.allowed, request.fallback, request.model
    )
    entry = decision.to_json() | {
        "id": len(_LOG),
        "minute": request.prompt.get("minute"),
        "score_before": request.prompt.get("satisfaction"),
        "score_after": None,
    }
    _LOG.append(entry)
    return entry


@router.post("/mayor/outcome")
async def mayor_outcome(request: OutcomeRequest) -> dict[str, Any]:
    if 0 <= request.id < len(_LOG):
        _LOG[request.id]["score_after"] = request.score_after
        return _LOG[request.id]
    return {"error": "unknown decision"}


@router.get("/decisions")
async def decisions() -> list[dict[str, Any]]:
    return _LOG[-50:]


@router.post("/residents")
async def residents(request: ResidentRequest) -> dict[str, Any]:
    return await llm.decide(request.residents, request.context, request.model)

"""Mayor backends: `baseline` (rules), `local` (Ollama, default qwen3:8b) and `api` (Anthropic).

Every backend returns the same shape, and the order is always checked against the
allowed list the game sent. Any failure falls back to the game's own fallback order,
so the city never waits on a broken model.

The paid API is off unless `AIA_ALLOW_PAID_API=1` and `ANTHROPIC_API_KEY` are set
in the environment that started the engine (docs/engine-plan.md D2 interlock).
"""

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

from aiautonomy.engines.agents.ollama import OllamaClient, OllamaError

LOCAL_MODEL = "qwen3:8b"
API_MODEL = os.environ.get("AIA_MAYOR_API_MODEL", "claude-haiku-5-5")


@dataclass
class MayorDecision:
    order: str
    statement: str
    backend: str
    model: str
    ms: int
    fallback_used: bool = False
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def api_available() -> bool:
    return os.environ.get("AIA_ALLOW_PAID_API") == "1" and bool(os.environ.get("ANTHROPIC_API_KEY"))


def _system(allowed: list[str]) -> str:
    return (
        "You are the mayor of a fictional Boston city simulator. Keep residents satisfied and the "
        "city stable. Read the city state, especially satisfaction (0-100), active incidents, "
        'crimes and district authority. Return only JSON: {"order": one of '
        + ", ".join(allowed)
        + ', "statement": one short public announcement explaining why}.'
    )


def _baseline(prompt: dict[str, Any], allowed: list[str], fallback: str) -> str:
    incident = prompt.get("incident") or {}
    kind = incident.get("kind")
    if kind == "protest" and "mediate" in allowed:
        return "mediate"
    if kind in {"fire", "flood", "storm"} and "dispatch" in allowed:
        return "dispatch"
    if (prompt.get("crimes") or 0) > 0 and "patrol" in allowed:
        return "patrol"
    return fallback if fallback in allowed else allowed[0]


def _parse(text: str, allowed: list[str]) -> tuple[str, str]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no JSON object in reply")
    data = json.loads(match.group(0))
    order = str(data.get("order", ""))
    if order not in allowed:
        raise ValueError(f"order {order!r} not allowed")
    return order, str(data.get("statement", ""))[:180]


async def _local(model: str, prompt: dict[str, Any], allowed: list[str]) -> tuple[str, str]:
    client = OllamaClient("mayor")
    schema = {
        "type": "object",
        "properties": {
            "order": {"type": "string", "enum": allowed},
            "statement": {"type": "string"},
        },
        "required": ["order", "statement"],
    }
    data = await client.chat_json(
        model, _system(allowed), json.dumps(prompt), schema, num_predict=120
    )
    return _parse(json.dumps(data), allowed)


async def _api(model: str, prompt: dict[str, Any], allowed: list[str]) -> tuple[str, str]:
    if not api_available():
        raise RuntimeError("paid API disabled: set AIA_ALLOW_PAID_API=1 and ANTHROPIC_API_KEY")
    import anthropic

    client = anthropic.AsyncAnthropic(timeout=30.0)
    reply = await client.messages.create(
        model=model,
        max_tokens=200,
        system=_system(allowed),
        messages=[{"role": "user", "content": json.dumps(prompt)}],
    )
    text = "".join(block.text for block in reply.content if block.type == "text")
    return _parse(text, allowed)


async def decide(
    backend: str,
    prompt: dict[str, Any],
    allowed: list[str],
    fallback: str,
    model: str | None = None,
) -> MayorDecision:
    started = time.monotonic()
    allowed = [a for a in allowed if isinstance(a, str)] or ["monitor"]
    fallback = fallback if fallback in allowed else allowed[0]
    chosen_model = model or (API_MODEL if backend == "api" else LOCAL_MODEL)
    try:
        if backend == "local":
            order, statement = await _local(chosen_model, prompt, allowed)
        elif backend == "api":
            order, statement = await _api(chosen_model, prompt, allowed)
        else:
            chosen_model = "rules"
            order, statement = _baseline(prompt, allowed, fallback), ""
        return MayorDecision(
            order, statement, backend, chosen_model, int((time.monotonic() - started) * 1000)
        )
    except (OllamaError, ValueError, RuntimeError, ImportError, Exception) as error:
        return MayorDecision(
            fallback,
            "",
            backend,
            chosen_model,
            int((time.monotonic() - started) * 1000),
            fallback_used=True,
            error=str(error)[:200],
        )

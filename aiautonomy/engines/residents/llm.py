"""Autonomous (LLM) residents: one batched local call decides for a handful of residents.

Residents always use local Ollama (default qwen3:1.7b). They may pick a small set of
unlawful actions; the game applies the consequences (police, authority loss, closures).
"""

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

from aiautonomy.engines.agents.ollama import OllamaClient, OllamaError

RESIDENT_MODEL = "qwen3:1.7b"
LAWFUL = ["follow_routine", "go_home", "visit_venue", "peaceful_protest", "stay_put"]
UNLAWFUL = ["speeding", "vandalism", "road_blockade"]
ACTIONS = LAWFUL + UNLAWFUL
MAX_BATCH = 8

SYSTEM = (
    "You decide what residents of a fictional Boston city simulator do next. Each resident has a "
    "mood (0-100), grievances and the city situation. Content, busy residents usually follow their "
    "routine. Angry residents with grievances may protest; a few may break the law (speeding when "
    "late, vandalism or a road blockade when furious), especially if police presence is low. "
    'Return JSON {"decisions": [{"id": resident id, "action": one allowed action, '
    '"thought": one short first-person sentence}]} with one entry per resident.'
)


async def decide(
    residents: list[dict[str, Any]], context: dict[str, Any], model: str | None = None
) -> dict[str, Any]:
    started = time.monotonic()
    batch = residents[:MAX_BATCH]
    ids = [int(r.get("id", -1)) for r in batch]
    chosen = model or RESIDENT_MODEL
    schema = {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "action": {"type": "string", "enum": ACTIONS},
                        "thought": {"type": "string"},
                    },
                    "required": ["id", "action", "thought"],
                },
            }
        },
        "required": ["decisions"],
    }
    user = json.dumps({"city": context, "residents": batch, "allowed": ACTIONS})
    try:
        client = OllamaClient("resident")
        data = await client.chat_json(
            chosen, SYSTEM, user, schema, wait_s=45.0, num_predict=60 * len(batch) + 60
        )
        decisions: list[dict[str, Any]] = []
        for item in data.get("decisions", []):
            rid, action = item.get("id"), item.get("action")
            if rid in ids and action in ACTIONS and all(d["id"] != rid for d in decisions):
                decisions.append(
                    {"id": rid, "action": action, "thought": str(item.get("thought", ""))[:140]}
                )
        return {
            "decisions": decisions,
            "model": chosen,
            "ms": int((time.monotonic() - started) * 1000),
        }
    except OllamaError as error:
        return {
            "decisions": [],
            "model": chosen,
            "ms": int((time.monotonic() - started) * 1000),
            "error": str(error)[:200],
        }


# --- run-scoped resident decisions (docs/contract.md §7) ----------------------------------


@dataclass(frozen=True, slots=True)
class ResidentBatch:
    """One batched request: LLM residents' observations, the offered actions, public context."""

    batch_id: str
    residents: list[dict[str, Any]]
    offered: list[str]
    context: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ResidentReply:
    decisions: dict[int, tuple[str, str]]
    """Resident id → (action, thought) for every valid entry the model returned."""
    model: str
    error: str | None = None
    latency_ms: int = 0


class ResidentProvider(Protocol):
    model: str

    async def decide(self, batch: ResidentBatch) -> ResidentReply: ...


class LocalResidentProvider:
    """Local Ollama only (loopback client, the one-model lock); never a remote provider."""

    def __init__(self, model: str, wait_s: float) -> None:
        self.model = model
        self.wait_s = wait_s

    async def decide(self, batch: ResidentBatch) -> ResidentReply:
        started = time.monotonic()
        ids = [int(r["id"]) for r in batch.residents]
        schema = {
            "type": "object",
            "properties": {
                "decisions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer", "enum": ids},
                            "action": {"type": "string", "enum": batch.offered},
                            "thought": {"type": "string", "maxLength": 140},
                        },
                        "required": ["id", "action", "thought"],
                    },
                }
            },
            "required": ["decisions"],
        }
        user = json.dumps(
            {"city": batch.context, "residents": batch.residents, "allowed": batch.offered},
            sort_keys=True,
        )
        try:
            client = OllamaClient("resident")
            data = await client.chat_json(
                self.model, SYSTEM, user, schema, wait_s=self.wait_s,
                num_predict=60 * len(ids) + 60,
            )  # fmt: skip
        except OllamaError as error:
            return ResidentReply({}, self.model, str(error)[:200], _ms(started))
        decisions: dict[int, tuple[str, str]] = {}
        for item in data.get("decisions", []) if isinstance(data, dict) else []:
            rid, action = item.get("id"), item.get("action")
            if rid in ids and action in batch.offered and rid not in decisions:
                decisions[rid] = (action, str(item.get("thought", ""))[:140])
        return ResidentReply(decisions, self.model, None, _ms(started))


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)

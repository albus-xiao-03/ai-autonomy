"""Autonomous (LLM) residents: one batched local call decides for a handful of residents.

Residents always use local Ollama (default qwen3:1.7b). They may pick a small set of
unlawful actions; the game applies the consequences (police, authority loss, closures).
"""

import json
import time
from typing import Any

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

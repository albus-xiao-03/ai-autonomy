"""Mayor proposal providers for hybrid runs: baseline rules, local Ollama, the Anthropic API.

Every provider answers one `MayorRequest`: the observation the engine built (no hidden or
future events) and the permitted options it derived. The answer is a `ProviderReply` carrying
a structured `MayorProposal` (one option id plus an optional statement) or an error.
Providers never see or change engine state. The run validates a reply and applies it at its
fixed apply tick; model output is parsed as data and never executed (ARCH-04).

The API provider takes an injectable client factory. The default factory enforces the paid-API
interlock (`AIA_ALLOW_PAID_API=1` and `ANTHROPIC_API_KEY` on the engine), and tests inject a
client bound to the loopback `FakeAnthropic` instead.

REQ: MAY-01, MAY-02, MAY-06, MAY-07, MAY-08, EVAL-01, ARCH-04, ARCH-05, LOCAL-06
"""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from aiautonomy.engines.agents.ollama import OllamaClient, OllamaError
from aiautonomy.engines.contract.common import MayorBackend
from aiautonomy.engines.contract.decisions import ActionOption, MayorProposal
from aiautonomy.engines.mayor.backends import api_available

SYSTEM = (
    "You are the autonomous mayor of a simulated Boston. Standing 911 dispatch already sends "
    "the nearest available units to every incident; you only add exceptional orders. Every "
    "accepted order beyond the allowance in the rolling window costs political authority, so "
    "order only when it clearly helps residents. Read the observation, then answer with JSON "
    '{"action": <one option id>, "statement": <one short public sentence>}. HOLD keeps '
    "standing procedures."
)
MAX_STATEMENT = 280


@dataclass(frozen=True, slots=True)
class MayorRequest:
    decision_id: str
    observation: dict[str, Any]
    options: list[ActionOption]


@dataclass(frozen=True, slots=True)
class ProviderReply:
    proposal: MayorProposal | None
    model: str
    error: str | None = None
    latency_ms: int = 0


class MayorProvider(Protocol):
    backend: MayorBackend
    model: str

    async def propose(self, request: MayorRequest) -> ProviderReply: ...


def parse_proposal(data: Any, options: list[ActionOption]) -> MayorProposal:
    """Strictly parse a model's answer; the action must be one of the offered option ids."""
    if not isinstance(data, dict):
        raise ValueError("the answer is not a JSON object")
    statement = str(data.get("statement", ""))[:MAX_STATEMENT]
    proposal = MayorProposal.model_validate({"action": data.get("action"), "statement": statement})
    if proposal.action not in {option.id for option in options}:
        raise ValueError(f"action {proposal.action!r} was not offered")
    return proposal


def _user_payload(request: MayorRequest) -> str:
    return json.dumps(
        {
            "observation": request.observation,
            "options": [{"id": option.id, "summary": option.summary} for option in request.options],
            "answer": "JSON only: one option id as action, one short public statement",
        },
        sort_keys=True,
    )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def baseline_proposal(request: MayorRequest) -> MayorProposal:
    """Deterministic rules on the same observation and options as the model mayors (EVAL-01).

    1. A severe incident (severity ≥ 70) with waiting demand that a one-unit dispatch can
       serve: send one unit, but only while the order allowance has room (or severity ≥ 85).
    2. A prioritize option for an incident of severity ≥ 50 that has waited ≥ 10 ticks.
    3. Otherwise hold.
    """
    observation = request.observation
    incidents = {item["id"]: item for item in observation.get("incidents", [])}
    room = observation.get("orders", {}).get("remaining_allowance", 0) > 0
    for option in request.options:
        incident = incidents.get(option.incident_id or "")
        if option.kind != "dispatch" or option.units != 1 or incident is None:
            continue
        waiting = option.department in incident.get("queued", {})
        if waiting and incident["severity"] >= 70 and (room or incident["severity"] >= 85):
            return MayorProposal(
                action=option.id, statement="Sending extra help to a severe incident."
            )
    for option in request.options:
        incident = incidents.get(option.incident_id or "")
        if option.kind == "prioritize" and incident is not None and room:
            waited = incident.get("waiting_ticks", {}).get(option.department or "", 0)
            if incident["severity"] >= 50 and waited >= 10:
                return MayorProposal(action=option.id, statement="Prioritizing a waiting incident.")
    return MayorProposal(action="HOLD", statement="")


class BaselineProvider:
    backend: MayorBackend = "baseline"
    model = "rules"

    async def propose(self, request: MayorRequest) -> ProviderReply:
        return ProviderReply(baseline_proposal(request), self.model)


class LocalProvider:
    """Local Ollama (default qwen3:8b) through the one-model lock; enum-constrained output."""

    backend: MayorBackend = "local"

    def __init__(self, model: str, wait_s: float) -> None:
        self.model = model
        self.wait_s = wait_s

    async def propose(self, request: MayorRequest) -> ProviderReply:
        started = time.monotonic()
        schema = {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": [option.id for option in request.options]},
                "statement": {"type": "string", "maxLength": MAX_STATEMENT},
            },
            "required": ["action", "statement"],
        }
        try:
            client = OllamaClient("mayor")
            data = await client.chat_json(
                self.model, SYSTEM, _user_payload(request), schema, wait_s=self.wait_s,
                num_predict=200,
            )  # fmt: skip
            return ProviderReply(parse_proposal(data, request.options), self.model, None,
                                 _elapsed_ms(started))  # fmt: skip
        except (OllamaError, ValueError, ValidationError) as error:
            return ProviderReply(None, self.model, str(error)[:200], _elapsed_ms(started))


def default_api_client() -> Any:
    """The real SDK client; refuses unless the engine runs with the paid-API interlock."""
    if not api_available():
        raise RuntimeError("paid API disabled: set AIA_ALLOW_PAID_API=1 and ANTHROPIC_API_KEY")
    import anthropic

    return anthropic.AsyncAnthropic(timeout=30.0, max_retries=1)


class ApiProvider:
    """The Anthropic Messages API; any failure, refusal or malformed answer is an error reply."""

    backend: MayorBackend = "api"

    def __init__(self, model: str, client_factory: Callable[[], Any] = default_api_client) -> None:
        self.model = model
        self.client_factory = client_factory

    async def propose(self, request: MayorRequest) -> ProviderReply:
        started = time.monotonic()
        try:
            client = self.client_factory()
            reply = await client.messages.create(
                model=self.model,
                max_tokens=300,
                system=SYSTEM,
                messages=[{"role": "user", "content": _user_payload(request)}],
            )
            if getattr(reply, "stop_reason", None) in {"refusal", "max_tokens"}:
                raise ValueError(f"stop_reason {reply.stop_reason}")
            text = "".join(
                getattr(block, "text", "")
                for block in reply.content
                if getattr(block, "type", "") == "text"
            )
            match = re.search(r"\{.*\}", text, re.S)
            if match is None:
                raise ValueError("no JSON object in the reply")
            proposal = parse_proposal(json.loads(match.group(0)), request.options)
            return ProviderReply(proposal, self.model, None, _elapsed_ms(started))
        except Exception as error:  # every provider failure becomes one logged hold
            return ProviderReply(None, self.model, str(error)[:200], _elapsed_ms(started))

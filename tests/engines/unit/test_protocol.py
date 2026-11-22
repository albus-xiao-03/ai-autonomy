import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from aiautonomy.engines.api import export_schema
from aiautonomy.engines.api.protocol import CLIENT_MESSAGE_ADAPTER, SERVER_MESSAGE_ADAPTER

pytestmark = pytest.mark.req("ARCH-03")

ENVELOPE = {"run_id": "r-1", "run_epoch": 2, "state_version": 7, "tick": 12}
STATUS = {
    "state": "running",
    "speed": "1x",
    "ticks_per_second": 5,
    "duration": 300,
    "waiting_for_inference": False,
    "scenario": "toy",
    "seed": 1,
    "engine_version": "0.1.0",
}
WORLD = {
    "clock": {"tick": 12, "day": 1, "minute_of_day": 432},
    "bounds": {"min_x": -420.0, "min_y": -420.0, "max_x": 420.0, "max_y": 420.0},
    "movers": {"mover-000001": {"id": "mover-000001", "x": 1.5, "y": -2.0, "kind": "walker"}},
}
SERVER_MESSAGES: list[dict[str, Any]] = [
    {"type": "snapshot", **ENVELOPE, "status": STATUS, "world": WORLD},
    {
        "type": "delta",
        **ENVELOPE,
        "changes": [
            {"op": "set", "field": "clock", "value": WORLD["clock"]},
            {"op": "upsert", "collection": "movers", "id": "m", "value": {"id": "m"}},
            {"op": "remove", "collection": "movers", "id": "m"},
        ],
    },
    {"type": "run_status", **ENVELOPE, "status": STATUS},
    {"type": "metrics", **ENVELOPE, "values": {"distance_walked_km": 1.25}},
    {
        "type": "decision",
        **ENVELOPE,
        "record": {"decision_id": "d", "actor_id": "a", "outcome": "accepted", "summary": "s"},
    },
    {"type": "ack", "cmd_id": "c-1", "ok": True, "error": None, "result": {"tick": 3}},
    {"type": "ack", "cmd_id": "c-2", "ok": False, "error": "nope", "result": None},
]
CLIENT_MESSAGES: list[dict[str, Any]] = [
    {"type": "configure", "cmd_id": "1", "config": {"scenario": "toy", "seed": 3, "duration": 9}},
    {"type": "configure", "cmd_id": "2", "config": {}},
    *({"type": kind, "cmd_id": kind} for kind in ("start", "pause", "resume", "step", "reset")),
    {"type": "cancel", "cmd_id": "3"},
    {"type": "set_speed", "cmd_id": "4", "speed": "max"},
    {"type": "inspect", "cmd_id": "5", "entity_id": "mover-000001"},
    {"type": "sync", "cmd_id": "6"},
    {
        "type": "telemetry",
        "cmd_id": "7",
        "fps": 59.5,
        "frame_ms_p95": 18.2,
        "cmd_latency_ms_p50": 4,
        "cmd_latency_ms_p95": 9.5,
        "samples": 120,
    },
]


@pytest.mark.parametrize("message", SERVER_MESSAGES, ids=lambda m: m["type"])
def test_server_messages_round_trip(message: dict[str, Any]) -> None:
    parsed = SERVER_MESSAGE_ADAPTER.validate_python(message)
    text = SERVER_MESSAGE_ADAPTER.dump_json(parsed)
    assert SERVER_MESSAGE_ADAPTER.validate_json(text) == parsed
    assert json.loads(text) == json.loads(json.dumps(message))


@pytest.mark.parametrize("message", CLIENT_MESSAGES, ids=lambda m: m["cmd_id"])
def test_client_commands_round_trip(message: dict[str, Any]) -> None:
    parsed = CLIENT_MESSAGE_ADAPTER.validate_json(json.dumps(message))
    assert parsed.type == message["type"]
    dumped = json.loads(CLIENT_MESSAGE_ADAPTER.dump_json(parsed, exclude_none=True))
    assert dumped == message


@pytest.mark.parametrize(
    "message",
    [
        {"type": "launch", "cmd_id": "1"},
        {"type": "start"},
        {"type": "start", "cmd_id": "1", "extra": True},
        {"type": "set_speed", "cmd_id": "1", "speed": "3x"},
        {"type": "configure", "cmd_id": "1", "config": {"seed": 2**53}},
        {"type": "configure", "cmd_id": "1", "config": {"duration": 0}},
        {
            "type": "telemetry",
            "cmd_id": "1",
            "fps": -1,
            "frame_ms_p95": 0,
            "cmd_latency_ms_p50": 0,
            "cmd_latency_ms_p95": 0,
            "samples": 0,
        },
    ],
)
def test_invalid_commands_are_rejected(message: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CLIENT_MESSAGE_ADAPTER.validate_json(json.dumps(message))


def test_committed_schema_is_current_and_deterministic(tmp_path: Path) -> None:
    assert export_schema.main(["--check"]) == 0
    assert export_schema.render_schema() == export_schema.render_schema()
    stale = tmp_path / "schema.json"
    stale.write_text("{}\n")
    assert export_schema.main(["--check", "--output", str(stale)]) == 1


def test_schema_names_every_type_for_typescript_generation() -> None:
    schema = export_schema.build_schema()
    defs = schema["$defs"]
    expected = {
        "ServerMessage", "ClientMessage", "Change", "RunStatus", "RunState", "Speed",
        "WorldView", "ClockView", "Bounds", "MoverView", "DecisionRecord", "HealthResponse",
        "SnapshotMessage", "DeltaMessage", "RunStatusMessage", "MetricsMessage",
        "DecisionMessage", "AckMessage", "UpsertChange", "RemoveChange", "SetChange",
        "ConfigureCommand", "RunConfigOverrides", "StartCommand", "PauseCommand",
        "ResumeCommand", "StepCommand", "SetSpeedCommand", "ResetCommand", "CancelCommand",
        "InspectCommand", "SyncCommand", "TelemetryCommand",
    }  # fmt: skip
    assert expected <= set(defs)
    assert schema["properties"]["server_message"] == {"$ref": "#/$defs/ServerMessage"}
    assert schema["properties"]["client_message"] == {"$ref": "#/$defs/ClientMessage"}
    for name, definition in defs.items():
        assert definition.get("title") == name
        for prop in definition.get("properties", {}).values():
            assert "title" not in prop  # no stray per-property type aliases
        if definition.get("type") == "object":
            assert definition.get("additionalProperties") is False
            if name != "RunConfigOverrides":
                assert definition.get("required") == list(definition["properties"])

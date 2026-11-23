"""Export the protocol JSON Schema: `python -m aiautonomy.engines.api.export_schema [--check]`.

The schema is written next to this module, at `aiautonomy/engines/api/protocol.schema.json`.

The output is deterministic. `--check` compares it with the committed file and exits 1 on
drift. The root schema names `ServerMessage`, `ClientMessage` and every message and model
type under `$defs`, so json-schema-to-typescript emits named TypeScript types.

REQ: ARCH-03
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaValue
from pydantic_core import core_schema

from aiautonomy.engines.api.protocol import ClientMessage, HealthResponse, ServerMessage
from aiautonomy.engines.contract.common import ErrorResponse
from aiautonomy.engines.contract.decisions import (
    MayorDecisionRecord,
    OrderRecord,
    ResidentDecisionAccepted,
    ResidentDecisionRequest,
)
from aiautonomy.engines.contract.dispatch import IncidentCatalogView
from aiautonomy.engines.contract.disruptions import (
    DisruptionCatalogView,
    DisruptionInjectRequest,
    DisruptionInjectResponse,
)
from aiautonomy.engines.contract.maps import (
    MapCreateRequest,
    MapList,
    MapRevision,
    MapRevisionRequest,
    MapValidateRequest,
    MapValidationReport,
)
from aiautonomy.engines.contract.runs import (
    EpochRequest,
    RunHandle,
    RunLaunchRequest,
    RunSummary,
    TickObservation,
    TickOutcome,
)

SCHEMA_TITLE = "AiaProtocol"
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


class _ProtocolSchemaGenerator(GenerateJsonSchema):
    """Omit per-property titles: json-schema-to-typescript would turn each into a type alias."""

    def field_title_should_be_set(
        self,
        schema: core_schema.ModelField
        | core_schema.DataclassField
        | core_schema.TypedDictField
        | core_schema.CoreSchema,
    ) -> bool:
        return False

    def default_schema(self, schema: core_schema.WithDefaultSchema) -> JsonSchemaValue:
        """Drop `default: null` on optional fields whose schema excludes null."""
        json_schema = super().default_schema(schema)
        if "default" in json_schema and json_schema["default"] is None:
            del json_schema["default"]
        return json_schema


def default_schema_path() -> Path:
    return Path(__file__).resolve().with_name("protocol.schema.json")


def build_schema() -> dict[str, Any]:
    """Return the root protocol schema with every type under `$defs`."""
    roots: list[tuple[str, TypeAdapter[Any]]] = [
        ("server_message", TypeAdapter(ServerMessage)),
        ("client_message", TypeAdapter(ClientMessage)),
        ("health", TypeAdapter(HealthResponse)),
        # Hybrid REST contract (docs/contract.md).
        ("map_list", TypeAdapter(MapList)),
        ("map_revision", TypeAdapter(MapRevision)),
        ("map_create_request", TypeAdapter(MapCreateRequest)),
        ("map_revision_request", TypeAdapter(MapRevisionRequest)),
        ("map_validate_request", TypeAdapter(MapValidateRequest)),
        ("map_validation_report", TypeAdapter(MapValidationReport)),
        ("run_launch_request", TypeAdapter(RunLaunchRequest)),
        ("run_handle", TypeAdapter(RunHandle)),
        ("epoch_request", TypeAdapter(EpochRequest)),
        ("run_summary", TypeAdapter(RunSummary)),
        ("tick_observation", TypeAdapter(TickObservation)),
        ("tick_outcome", TypeAdapter(TickOutcome)),
        ("disruption_inject_request", TypeAdapter(DisruptionInjectRequest)),
        ("disruption_inject_response", TypeAdapter(DisruptionInjectResponse)),
        ("disruption_catalog", TypeAdapter(DisruptionCatalogView)),
        ("incident_catalog", TypeAdapter(IncidentCatalogView)),
        ("resident_decision_request", TypeAdapter(ResidentDecisionRequest)),
        ("resident_decision_accepted", TypeAdapter(ResidentDecisionAccepted)),
        ("mayor_decision_record", TypeAdapter(MayorDecisionRecord)),
        ("order_record", TypeAdapter(OrderRecord)),
        ("error_response", TypeAdapter(ErrorResponse)),
    ]
    refs, top = TypeAdapter.json_schemas(
        [(name, "validation", adapter) for name, adapter in roots],
        ref_template="#/$defs/{model}",
        schema_generator=_ProtocolSchemaGenerator,
    )
    properties = {name: refs[(name, "validation")] for name, _ in roots}
    # Named type aliases (Change, ServerMessage, ClientMessage) carry no title of their own;
    # give every definition one so generated TypeScript types are always named after it.
    definitions = {
        name: dict(sorted({**definition, "title": definition.get("title", name)}.items()))
        for name, definition in top["$defs"].items()
    }
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "title": SCHEMA_TITLE,
        "description": (
            "AI Autonomy engine-frontend protocol (docs/engine-plan.md §4.8). One WebSocket at /ws "
            "carries JSON text frames discriminated by `type`. The hybrid game contract "
            "(docs/contract.md) adds the REST bodies under /api/maps, /api/runs and "
            "/api/catalogs. Generated from aiautonomy.engines.api.protocol and "
            "aiautonomy.engines.contract; do not edit."
        ),
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "$defs": definitions,
    }


def render_schema() -> str:
    return json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aiautonomy.engines.api.export_schema")
    parser.add_argument("--check", action="store_true", help="fail if the file is stale")
    parser.add_argument("--output", type=Path, default=None, help="schema file path")
    args = parser.parse_args(argv)
    path: Path = args.output or default_schema_path()
    text = render_schema()
    if args.check:
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current != text:
            print(f"protocol schema drift: {path} is stale; run `make protocol`", file=sys.stderr)
            return 1
        print(f"protocol schema up to date: {path}")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

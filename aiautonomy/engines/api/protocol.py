"""Engine–frontend wire protocol: the single source of truth (plans/R1.md §4.8).

One WebSocket at `/ws` carries JSON text frames, one message per frame, discriminated by
`type`. The JSON Schema exported from these models
(`python -m aiautonomy.engines.api.export_schema`) generates the frontend's TypeScript types.

Rules: on connect the server sends `snapshot` then `run_status`. `state_version` starts at 0
for each run and increases by exactly 1 per `delta`; `snapshot`, `run_status` and `metrics`
carry the current value. Every command gets exactly one immediate `ack`.

REQ: ARCH-03
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic.json_schema import SkipJsonSchema

from aiautonomy.engines.sim.status import RunState, Speed

MAX_JS_SAFE_INT = 2**53 - 1
MAX_DURATION_TICKS = 100_000

JsonObject = dict[str, Any]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- world view ---------------------------------------------------------------


class ClockView(_Model):
    """Simulated clock after the latest completed tick."""

    tick: int = Field(ge=0, description="Completed ticks; 0 before the first tick.")
    day: int = Field(ge=1, description="1-based simulated day.")
    minute_of_day: int = Field(ge=0, le=1439, description="Minutes since midnight (420 = 07:00).")


class Bounds(_Model):
    """World extent in meters; x points east, y north, origin at the map center."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float


class MoverView(_Model):
    """A moving entity; position in meters."""

    id: str
    x: float
    y: float
    kind: str


class WorldView(_Model):
    """Renderable world state. Keyed maps (`movers`) are the collections that `upsert` and
    `remove` changes address; other top-level fields are singletons replaced by `set`."""

    clock: ClockView
    bounds: Bounds
    movers: dict[str, MoverView]


class RunStatus(_Model):
    """Playback and lifecycle status of the current run."""

    state: RunState
    speed: Speed
    ticks_per_second: float = Field(
        ge=0, description="Nominal playback rate: 5 at 1x, 10 at 2x, 20 at 4x, 0 at max (unpaced)."
    )
    duration: int = Field(ge=1, description="Configured run length in ticks.")
    waiting_for_inference: bool = Field(
        description="True while the driver waits for inference before phase 4 of a tick."
    )
    scenario: str
    seed: int
    engine_version: str


class DecisionRecord(_Model):
    """A model decision outcome (placeholder until M4/M5)."""

    decision_id: str
    actor_id: str
    outcome: str
    summary: str


# --- changes ------------------------------------------------------------------


class UpsertChange(_Model):
    """Insert or replace the whole entity `id` in the keyed map `collection`."""

    op: Literal["upsert"]
    collection: str
    id: str
    value: JsonObject


class RemoveChange(_Model):
    """Remove the entity `id` from the keyed map `collection`."""

    op: Literal["remove"]
    collection: str
    id: str


class SetChange(_Model):
    """Replace the top-level singleton `field` of the world view (for example `clock`)."""

    op: Literal["set"]
    field: str
    value: JsonObject


type Change = Annotated[UpsertChange | RemoveChange | SetChange, Field(discriminator="op")]


# --- server -> client -----------------------------------------------------------


class SnapshotMessage(_Model):
    """Full world view; replaces all client state for `run_id`."""

    type: Literal["snapshot"]
    run_id: str
    run_epoch: int
    state_version: int
    tick: int
    status: RunStatus
    world: WorldView


class DeltaMessage(_Model):
    """Changes since the previous delta; `state_version` is exactly one higher. At max speed
    one delta may cover several ticks."""

    type: Literal["delta"]
    run_id: str
    run_epoch: int
    state_version: int
    tick: int
    changes: list[Change]


class RunStatusMessage(_Model):
    """Sent on connect and whenever any field of the run status changes."""

    type: Literal["run_status"]
    run_id: str
    run_epoch: int
    state_version: int
    tick: int
    status: RunStatus


class MetricsMessage(_Model):
    """Metric values after `tick`; sent once per published delta."""

    type: Literal["metrics"]
    run_id: str
    run_epoch: int
    state_version: int
    tick: int
    values: dict[str, float]


class DecisionMessage(_Model):
    """A recorded model decision (first emitted in M4/M5)."""

    type: Literal["decision"]
    run_id: str
    run_epoch: int
    state_version: int
    tick: int
    record: DecisionRecord


class AckMessage(_Model):
    """The immediate answer to exactly one command."""

    type: Literal["ack"]
    cmd_id: str
    ok: bool
    error: str | None
    result: JsonObject | None


type ServerMessage = Annotated[
    SnapshotMessage
    | DeltaMessage
    | RunStatusMessage
    | MetricsMessage
    | DecisionMessage
    | AckMessage,
    Field(discriminator="type"),
]


# --- client -> server -----------------------------------------------------------

CmdId = Annotated[str, Field(min_length=1, max_length=128)]


class RunConfigOverrides(_Model):
    """Run configuration overrides; omitted fields keep the scenario defaults."""

    scenario: Annotated[str, Field(min_length=1, max_length=64)] | SkipJsonSchema[None] = None
    seed: Annotated[int, Field(ge=0, le=MAX_JS_SAFE_INT)] | SkipJsonSchema[None] = None
    duration: Annotated[int, Field(ge=1, le=MAX_DURATION_TICKS)] | SkipJsonSchema[None] = None


class ConfigureCommand(_Model):
    """Create a fresh idle run (new run_id, run_epoch + 1); only when not running or paused.
    A snapshot follows the ack."""

    type: Literal["configure"]
    cmd_id: CmdId
    config: RunConfigOverrides


class StartCommand(_Model):
    """Start an idle run."""

    type: Literal["start"]
    cmd_id: CmdId


class PauseCommand(_Model):
    """Pause a running run at the next tick boundary."""

    type: Literal["pause"]
    cmd_id: CmdId


class ResumeCommand(_Model):
    """Resume a paused run."""

    type: Literal["resume"]
    cmd_id: CmdId


class StepCommand(_Model):
    """Advance exactly one tick; only when idle or paused (the run is paused afterwards)."""

    type: Literal["step"]
    cmd_id: CmdId


class SetSpeedCommand(_Model):
    """Change the playback speed; applies from the next tick boundary."""

    type: Literal["set_speed"]
    cmd_id: CmdId
    speed: Speed


class ResetCommand(_Model):
    """Abandon the current run (interrupted if it had started), cancel in-flight work and
    create a fresh idle run with the same configuration. A snapshot follows the ack."""

    type: Literal["reset"]
    cmd_id: CmdId


class CancelCommand(_Model):
    """End the current run as interrupted (END-05)."""

    type: Literal["cancel"]
    cmd_id: CmdId


class InspectCommand(_Model):
    """Look up one entity; the ack's `result` holds it."""

    type: Literal["inspect"]
    cmd_id: CmdId
    entity_id: str


class SyncCommand(_Model):
    """Request a fresh snapshot, sent after the ack."""

    type: Literal["sync"]
    cmd_id: CmdId


class TelemetryCommand(_Model):
    """Client performance samples, kept in memory for benchmark reports."""

    type: Literal["telemetry"]
    cmd_id: CmdId
    fps: float = Field(ge=0)
    frame_ms_p95: float = Field(ge=0)
    cmd_latency_ms_p50: float = Field(ge=0)
    cmd_latency_ms_p95: float = Field(ge=0)
    samples: int = Field(ge=0)


type ClientMessage = Annotated[
    ConfigureCommand
    | StartCommand
    | PauseCommand
    | ResumeCommand
    | StepCommand
    | SetSpeedCommand
    | ResetCommand
    | CancelCommand
    | InspectCommand
    | SyncCommand
    | TelemetryCommand,
    Field(discriminator="type"),
]


# --- REST -----------------------------------------------------------------------


class HealthResponse(_Model):
    """`GET /api/health`."""

    ok: bool
    engine_version: str
    git_sha: str | None
    dirty: bool | None


SERVER_MESSAGE_ADAPTER: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)
CLIENT_MESSAGE_ADAPTER: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)

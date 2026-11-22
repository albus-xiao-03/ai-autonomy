/* eslint-disable */
/**
 * Generated — do not edit.
 * Source: aiautonomy/engines/api/protocol.schema.json (the engine's pydantic protocol models).
 * Regenerate with `make protocol` or `npm run gen:protocol`; CI checks for drift.
 */

/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ServerMessage".
 */
export type ServerMessage =
  SnapshotMessage | DeltaMessage | RunStatusMessage | MetricsMessage | DecisionMessage | AckMessage;
/**
 * Lifecycle state of a run. `completed`, `removed` and `interrupted` are terminal.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "RunState".
 */
export type RunState = 'idle' | 'running' | 'paused' | 'completed' | 'removed' | 'interrupted';
/**
 * Playback speed. `max` runs ticks back to back without wall-clock pacing.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "Speed".
 */
export type Speed = '1x' | '2x' | '4x' | 'max';
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "Change".
 */
export type Change = UpsertChange | RemoveChange | SetChange;
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ClientMessage".
 */
export type ClientMessage =
  | ConfigureCommand
  | StartCommand
  | PauseCommand
  | ResumeCommand
  | StepCommand
  | SetSpeedCommand
  | ResetCommand
  | CancelCommand
  | InspectCommand
  | SyncCommand
  | TelemetryCommand;

/**
 * AI Autonomy engine-frontend protocol (docs/engine-plan.md §4.8). One WebSocket at /ws carries JSON text frames discriminated by `type`. Generated from aiautonomy.engines.api.protocol; do not edit.
 */
export interface AiaProtocol {
  server_message?: ServerMessage;
  client_message?: ClientMessage;
  health?: HealthResponse;
}
/**
 * Full world view; replaces all client state for `run_id`.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "SnapshotMessage".
 */
export interface SnapshotMessage {
  type: 'snapshot';
  run_id: string;
  run_epoch: number;
  state_version: number;
  tick: number;
  status: RunStatus;
  world: WorldView;
}
/**
 * Playback and lifecycle status of the current run.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "RunStatus".
 */
export interface RunStatus {
  state: RunState;
  speed: Speed;
  /**
   * Nominal playback rate: 5 at 1x, 10 at 2x, 20 at 4x, 0 at max (unpaced).
   */
  ticks_per_second: number;
  /**
   * Configured run length in ticks.
   */
  duration: number;
  /**
   * True while the driver waits for inference before phase 4 of a tick.
   */
  waiting_for_inference: boolean;
  scenario: string;
  seed: number;
  engine_version: string;
}
/**
 * Renderable world state. Keyed maps (`movers`) are the collections that `upsert` and
 * `remove` changes address; other top-level fields are singletons replaced by `set`.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "WorldView".
 */
export interface WorldView {
  clock: ClockView;
  bounds: Bounds;
  movers: {
    [k: string]: MoverView;
  };
}
/**
 * Simulated clock after the latest completed tick.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ClockView".
 */
export interface ClockView {
  /**
   * Completed ticks; 0 before the first tick.
   */
  tick: number;
  /**
   * 1-based simulated day.
   */
  day: number;
  /**
   * Minutes since midnight (420 = 07:00).
   */
  minute_of_day: number;
}
/**
 * World extent in meters; x points east, y north, origin at the map center.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "Bounds".
 */
export interface Bounds {
  min_x: number;
  min_y: number;
  max_x: number;
  max_y: number;
}
/**
 * A moving entity; position in meters.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MoverView".
 */
export interface MoverView {
  id: string;
  x: number;
  y: number;
  kind: string;
}
/**
 * Changes since the previous delta; `state_version` is exactly one higher. At max speed
 * one delta may cover several ticks.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "DeltaMessage".
 */
export interface DeltaMessage {
  type: 'delta';
  run_id: string;
  run_epoch: number;
  state_version: number;
  tick: number;
  changes: Change[];
}
/**
 * Insert or replace the whole entity `id` in the keyed map `collection`.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "UpsertChange".
 */
export interface UpsertChange {
  op: 'upsert';
  collection: string;
  id: string;
  value: {
    [k: string]: unknown;
  };
}
/**
 * Remove the entity `id` from the keyed map `collection`.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "RemoveChange".
 */
export interface RemoveChange {
  op: 'remove';
  collection: string;
  id: string;
}
/**
 * Replace the top-level singleton `field` of the world view (for example `clock`).
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "SetChange".
 */
export interface SetChange {
  op: 'set';
  field: string;
  value: {
    [k: string]: unknown;
  };
}
/**
 * Sent on connect and whenever any field of the run status changes.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "RunStatusMessage".
 */
export interface RunStatusMessage {
  type: 'run_status';
  run_id: string;
  run_epoch: number;
  state_version: number;
  tick: number;
  status: RunStatus;
}
/**
 * Metric values after `tick`; sent once per published delta.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MetricsMessage".
 */
export interface MetricsMessage {
  type: 'metrics';
  run_id: string;
  run_epoch: number;
  state_version: number;
  tick: number;
  values: {
    [k: string]: number;
  };
}
/**
 * A recorded model decision (first emitted in M4/M5).
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "DecisionMessage".
 */
export interface DecisionMessage {
  type: 'decision';
  run_id: string;
  run_epoch: number;
  state_version: number;
  tick: number;
  record: DecisionRecord;
}
/**
 * A model decision outcome (placeholder until M4/M5).
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "DecisionRecord".
 */
export interface DecisionRecord {
  decision_id: string;
  actor_id: string;
  outcome: string;
  summary: string;
}
/**
 * The immediate answer to exactly one command.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "AckMessage".
 */
export interface AckMessage {
  type: 'ack';
  cmd_id: string;
  ok: boolean;
  error: string | null;
  result: {
    [k: string]: unknown;
  } | null;
}
/**
 * Create a fresh idle run (new run_id, run_epoch + 1); only when not running or paused.
 * A snapshot follows the ack.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ConfigureCommand".
 */
export interface ConfigureCommand {
  type: 'configure';
  cmd_id: string;
  config: RunConfigOverrides;
}
/**
 * Run configuration overrides; omitted fields keep the scenario defaults.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "RunConfigOverrides".
 */
export interface RunConfigOverrides {
  scenario?: string;
  seed?: number;
  duration?: number;
}
/**
 * Start an idle run.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "StartCommand".
 */
export interface StartCommand {
  type: 'start';
  cmd_id: string;
}
/**
 * Pause a running run at the next tick boundary.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "PauseCommand".
 */
export interface PauseCommand {
  type: 'pause';
  cmd_id: string;
}
/**
 * Resume a paused run.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ResumeCommand".
 */
export interface ResumeCommand {
  type: 'resume';
  cmd_id: string;
}
/**
 * Advance exactly one tick; only when idle or paused (the run is paused afterwards).
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "StepCommand".
 */
export interface StepCommand {
  type: 'step';
  cmd_id: string;
}
/**
 * Change the playback speed; applies from the next tick boundary.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "SetSpeedCommand".
 */
export interface SetSpeedCommand {
  type: 'set_speed';
  cmd_id: string;
  speed: Speed;
}
/**
 * Abandon the current run (interrupted if it had started), cancel in-flight work and
 * create a fresh idle run with the same configuration. A snapshot follows the ack.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ResetCommand".
 */
export interface ResetCommand {
  type: 'reset';
  cmd_id: string;
}
/**
 * End the current run as interrupted (END-05).
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "CancelCommand".
 */
export interface CancelCommand {
  type: 'cancel';
  cmd_id: string;
}
/**
 * Look up one entity; the ack's `result` holds it.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "InspectCommand".
 */
export interface InspectCommand {
  type: 'inspect';
  cmd_id: string;
  entity_id: string;
}
/**
 * Request a fresh snapshot, sent after the ack.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "SyncCommand".
 */
export interface SyncCommand {
  type: 'sync';
  cmd_id: string;
}
/**
 * Client performance samples, kept in memory for benchmark reports.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "TelemetryCommand".
 */
export interface TelemetryCommand {
  type: 'telemetry';
  cmd_id: string;
  fps: number;
  frame_ms_p95: number;
  cmd_latency_ms_p50: number;
  cmd_latency_ms_p95: number;
  samples: number;
}
/**
 * `GET /api/health`.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "HealthResponse".
 */
export interface HealthResponse {
  ok: boolean;
  engine_version: string;
  git_sha: string | null;
  dirty: boolean | null;
}

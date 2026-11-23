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
 * AI Autonomy engine-frontend protocol (docs/engine-plan.md §4.8). One WebSocket at /ws carries JSON text frames discriminated by `type`. The hybrid game contract (docs/contract.md) adds the REST bodies under /api/maps, /api/runs and /api/catalogs. Generated from aiautonomy.engines.api.protocol and aiautonomy.engines.contract; do not edit.
 */
export interface AiaProtocol {
  server_message?: ServerMessage;
  client_message?: ClientMessage;
  health?: HealthResponse;
  map_list?: MapList;
  map_revision?: MapRevision;
  map_create_request?: MapCreateRequest;
  map_revision_request?: MapRevisionRequest;
  map_validate_request?: MapValidateRequest;
  map_validation_report?: MapValidationReport;
  run_launch_request?: RunLaunchRequest;
  run_handle?: RunHandle;
  epoch_request?: EpochRequest;
  run_summary?: RunSummary;
  tick_observation?: TickObservation;
  tick_outcome?: TickOutcome;
  disruption_inject_request?: DisruptionInjectRequest;
  disruption_inject_response?: DisruptionInjectResponse;
  disruption_catalog?: DisruptionCatalogView;
  incident_catalog?: IncidentCatalogView;
  resident_decision_request?: ResidentDecisionRequest;
  resident_decision_accepted?: ResidentDecisionAccepted;
  mayor_decision_record?: MayorDecisionRecord;
  order_record?: OrderRecord;
  error_response?: ErrorResponse;
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
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapList".
 */
export interface MapList {
  maps: MapSummary[];
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapSummary".
 */
export interface MapSummary {
  id: string;
  kind: 'template' | 'saved';
  read_only: boolean;
  revisions: MapRevisionSummary[];
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapRevisionSummary".
 */
export interface MapRevisionSummary {
  revision: number;
  name: string;
  sha256: string;
  parent?: MapRef | null;
}
/**
 * Pins one exact map revision.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapRef".
 */
export interface MapRef {
  id: string;
  revision: number;
  sha256: string;
}
/**
 * One immutable saved revision.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapRevision".
 */
export interface MapRevision {
  format?: 'aia-map';
  format_version?: 1;
  id: string;
  revision: number;
  name: string;
  parent?: MapRef | null;
  /**
   * SHA-256 of the canonical JSON of `content`.
   */
  sha256: string;
  /**
   * User landmarks this revision unlocked through an explicit setup action.
   */
  unlocked?: string[];
  content: MapContent;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapContent".
 */
export interface MapContent {
  level: number;
  /**
   * @maxItems 5000
   */
  nodes: MapNode[];
  /**
   * @maxItems 5000
   */
  roads: MapRoad[];
  /**
   * @maxItems 2000
   */
  buildings: MapBuilding[];
  /**
   * @maxItems 200
   */
  facilities: MapFacility[];
  /**
   * @maxItems 200
   */
  landmarks: MapLandmark[];
  /**
   * @maxItems 16
   */
  fixed:
    | []
    | [FixedGeometry]
    | [FixedGeometry, FixedGeometry]
    | [FixedGeometry, FixedGeometry, FixedGeometry]
    | [FixedGeometry, FixedGeometry, FixedGeometry, FixedGeometry]
    | [FixedGeometry, FixedGeometry, FixedGeometry, FixedGeometry, FixedGeometry]
    | [FixedGeometry, FixedGeometry, FixedGeometry, FixedGeometry, FixedGeometry, FixedGeometry]
    | [
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry
      ]
    | [
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry
      ]
    | [
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry
      ]
    | [
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry
      ]
    | [
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry
      ]
    | [
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry
      ]
    | [
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry
      ]
    | [
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry
      ]
    | [
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry
      ]
    | [
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry,
        FixedGeometry
      ];
  /**
   * Landmark or facility housing the mayor; an Outage covering it takes the mayor offline.
   */
  mayor_office: string;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapNode".
 */
export interface MapNode {
  id: string;
  x: number;
  z: number;
}
/**
 * A straight road segment between two nodes (the game's `a`/`b` endpoints).
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapRoad".
 */
export interface MapRoad {
  id: string;
  name?: string;
  /**
   * Start node id.
   */
  a: string;
  /**
   * End node id; one-way roads run from `a` to `b`.
   */
  b: string;
  type?: 'twoway' | 'oneway' | 'highway';
  bridge?: boolean;
  tunnel?: boolean;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapBuilding".
 */
export interface MapBuilding {
  id: string;
  type: 'residential' | 'office' | 'shop' | 'social' | 'park' | 'parking';
  label?: string;
  x: number;
  z: number;
  /**
   * Radians.
   */
  rotation: number;
  /**
   * Footprint radius; null derives it from type.
   */
  radius?: number | null;
  /**
   * A fixed famous district cluster (locked, never removable).
   */
  area?: boolean;
  access: Access;
}
/**
 * Where a building's or facility's driveway joins the road network.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "Access".
 */
export interface Access {
  road: string;
}
/**
 * A police (PD), fire (FD) or medical facility with its units.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapFacility".
 */
export interface MapFacility {
  id: string;
  name: string;
  department: 'police' | 'fire' | 'medical';
  x: number;
  z: number;
  rotation?: number;
  radius: number;
  access: Access;
  /**
   * Set when the facility occupies a landmark site (e.g. MGH).
   */
  landmark?: string | null;
  /**
   * @maxItems 32
   */
  units?: UnitSpec[];
}
/**
 * A service unit based at a facility; its department is the facility's.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "UnitSpec".
 */
export interface UnitSpec {
  id: string;
  /**
   * cruiser, engine, ambulance…
   */
  kind: string;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapLandmark".
 */
export interface MapLandmark {
  id: string;
  name: string;
  kind: 'canonical' | 'user';
  site?: ('hall' | 'garden' | 'hospital' | 'church' | 'market' | 'common' | 'statehouse') | null;
  x: number;
  z: number;
  radius: number;
  locked?: boolean;
}
/**
 * Read-only geometry owned by the game, pinned by the SHA-256 of its source file.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "FixedGeometry".
 */
export interface FixedGeometry {
  id: string;
  source: string;
  sha256: string;
}
/**
 * `POST /api/maps`: save a new map (revision 1), optionally derived from `parent`.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapCreateRequest".
 */
export interface MapCreateRequest {
  id: string;
  name: string;
  parent?: MapRef | null;
  content: MapContent;
  /**
   * @maxItems 200
   */
  unlock?: string[];
}
/**
 * `POST /api/maps/{id}/revisions`: save the next revision; `base` must be the latest.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapRevisionRequest".
 */
export interface MapRevisionRequest {
  name?: string | null;
  base: MapRef;
  content: MapContent;
  /**
   * @maxItems 200
   */
  unlock?: string[];
}
/**
 * `POST /api/maps/validate`: dry run; with `base` the lock rules are checked too.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapValidateRequest".
 */
export interface MapValidateRequest {
  content: MapContent;
  base?: MapRef | null;
  /**
   * @maxItems 200
   */
  unlock?: string[];
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MapValidationReport".
 */
export interface MapValidationReport {
  ok: boolean;
  sha256: string;
  failures?: Failure[];
  warnings?: Failure[];
}
/**
 * One validation failure or warning.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "Failure".
 */
export interface Failure {
  code: string;
  entity_id?: string | null;
  message: string;
}
/**
 * `POST /api/runs`: launch a run pinned to one map revision.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "RunLaunchRequest".
 */
export interface RunLaunchRequest {
  map: MapRef;
  scenario?: string;
  seed?: number | null;
  duration?: number | null;
  /**
   * Residents 0..population-1.
   */
  population: number;
  /**
   * LLM share in basis points.
   */
  llm_ratio_bp: number;
  mayor_backend?: 'baseline' | 'local' | 'api';
  disruptions?: LaunchDisruptions;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "LaunchDisruptions".
 */
export interface LaunchDisruptions {
  /**
   * Seeded automatic disruptions.
   */
  automatic?: boolean;
  /**
   * @maxItems 100
   */
  scheduled?: DisruptionSpec[];
}
/**
 * A scheduled or injected disruption; omitted values take the catalog defaults.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "DisruptionSpec".
 */
export interface DisruptionSpec {
  type: 'traffic' | 'outage' | 'gas_leakage' | 'flood' | 'storm' | 'snowstorm' | 'heavy_rain';
  x: number;
  z: number;
  radius_m?: number | null;
  intensity?: number | null;
  duration_ticks?: number | null;
  /**
   * Start tick; omitted for injection = next tick boundary.
   */
  at_tick?: number | null;
}
/**
 * Answer to launch and reset.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "RunHandle".
 */
export interface RunHandle {
  contract_version: number;
  run_id: string;
  run_epoch: number;
  status: 'running' | 'completed' | 'removed' | 'interrupted';
  /**
   * Last processed tick (0 before the first).
   */
  tick: number;
  map: MapRef;
  config: RunConfigView;
  mayor_backend: 'baseline' | 'local' | 'api';
  controller: 'baseline' | 'local' | 'api' | 'hold' | 'degraded';
  residents: ResidentModes;
  units: UnitView[];
  catalogs: CatalogRef[];
  /**
   * Launch-scheduled disruptions (automatic ones stay hidden until they start).
   */
  scheduled_disruptions?: DisruptionRecord[];
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "RunConfigView".
 */
export interface RunConfigView {
  scenario: string;
  seed: number;
  duration: number;
  start_minute_of_day: number;
  mayor_interval: number;
  mayor_latency_ticks: number;
  resident_latency_ticks: number;
  outcome_window_ticks: number;
  politics_interval_ticks: number;
}
/**
 * Seeded LLM assignment: llm_count = (population × ratio_bp + 5000) // 10000.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ResidentModes".
 */
export interface ResidentModes {
  population: number;
  llm_ratio_bp: number;
  llm_count: number;
  llm_ids: number[];
}
/**
 * The engine's view of one unit after the tick.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "UnitView".
 */
export interface UnitView {
  id: string;
  department: 'police' | 'fire' | 'medical';
  kind: string;
  facility_id: string;
  state: 'available' | 'assigned' | 'on_scene' | 'out_of_service';
  incident_id?: string | null;
  order_id?: string | null;
  since_tick: number;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "CatalogRef".
 */
export interface CatalogRef {
  id: string;
  version: number;
  path: string;
  sha256: string;
}
/**
 * A disruption of record. Severity = template severity × intensity / 50, clamped.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "DisruptionRecord".
 */
export interface DisruptionRecord {
  id: string;
  type: 'traffic' | 'outage' | 'gas_leakage' | 'flood' | 'storm' | 'snowstorm' | 'heavy_rain';
  label: string;
  source: 'automatic' | 'scheduled' | 'injected';
  status: 'scheduled' | 'active' | 'recovering' | 'ended';
  start_tick: number;
  /**
   * Planned end (latest end for `on_clear`).
   */
  end_tick: number;
  x: number;
  z: number;
  radius_m: number;
  intensity: number;
  effects: DisruptionEffects;
  recovery: Recovery;
  /**
   * Id the game must give the spawned incident.
   */
  incident_id: string;
  incident: IncidentTemplate;
  request_id?: string | null;
}
/**
 * Physical effects the game applies while the disruption is active.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "DisruptionEffects".
 */
export interface DisruptionEffects {
  /**
   * `area`: within radius_m of (x, z).
   */
  scope: 'area' | 'citywide';
  /**
   * Travel speed in scope, basis points (10000 = unchanged).
   */
  speed_multiplier_bp: number;
  /**
   * Close every road segment within the radius.
   */
  closes_roads: boolean;
  /**
   * Close tunnel segments within the radius.
   */
  closes_tunnels: boolean;
  /**
   * Close segments below ground level in radius.
   */
  closes_low_roads: boolean;
  /**
   * Traffic signals in the radius behave as stop signs.
   */
  signals_out: boolean;
  /**
   * One-time building damage at onset.
   */
  damage_pct: number;
  /**
   * The mayor is offline while active if the mayor office is in scope.
   */
  mayor_office_outage: boolean;
}
/**
 * How the disruption ends and what persists.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "Recovery".
 */
export interface Recovery {
  /**
   * `on_duration`: ends after duration_ticks. `on_clear`: ends when the responding units clear the incident (or after duration_ticks at the latest). `gradual`: after duration_ticks, speed stays at gradual_speed_multiplier_bp for gradual_ticks.
   */
  mode: 'on_duration' | 'on_clear' | 'gradual';
  gradual_ticks?: number;
  gradual_speed_multiplier_bp?: number;
  /**
   * Consequences that persist after the end.
   */
  lasting?: string[];
}
/**
 * The incident the game spawns for the disruption (id = the record's `incident_id`).
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "IncidentTemplate".
 */
export interface IncidentTemplate {
  kind:
    | 'traffic'
    | 'outage'
    | 'gas_leakage'
    | 'flood'
    | 'storm'
    | 'snowstorm'
    | 'heavy_rain'
    | 'protest'
    | 'crime';
  severity: number;
  needs: Needs;
}
/**
 * Units required per department.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "Needs".
 */
export interface Needs {
  police?: number;
  fire?: number;
  medical?: number;
}
/**
 * Body of `reset` and `cancel`; the epoch must match the run's.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "EpochRequest".
 */
export interface EpochRequest {
  run_epoch: number;
}
/**
 * `GET /api/runs/{run_id}` and the answer to `cancel`.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "RunSummary".
 */
export interface RunSummary {
  run_id: string;
  run_epoch: number;
  status: 'running' | 'completed' | 'removed' | 'interrupted';
  tick: number;
  map: MapRef;
  mayor_backend: 'baseline' | 'local' | 'api';
  authority: number;
  removal?: RemovalRecord | null;
  decisions: number;
  orders: number;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "RemovalRecord".
 */
export interface RemovalRecord {
  tick: number;
  /**
   * @minItems 1
   */
  mechanisms: ['recall_vote' | 'authority_withdrawn', ...('recall_vote' | 'authority_withdrawn')[]];
  primary: 'recall_vote' | 'authority_withdrawn';
  detail: string;
}
/**
 * `POST /api/runs/{run_id}/ticks`: what the game observed after simulating `tick`.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "TickObservation".
 */
export interface TickObservation {
  run_epoch: number;
  tick: number;
  satisfaction: number;
  /**
   * @maxItems 200
   */
  incidents?: IncidentObservation[];
  /**
   * Every (available unit, unresolved incident) pair, including units a `cleared` event in this observation frees; see docs/contract.md §4.
   *
   * @maxItems 5000
   */
  routes?: RouteObservation[];
  /**
   * @maxItems 200
   */
  unit_events?: UnitEvent[];
  /**
   * @maxItems 200
   */
  out_of_service?: string[];
  /**
   * @maxItems 10000
   */
  residents_joined?: number[];
  /**
   * Required on politics ticks.
   */
  resident_moods?: ResidentMood[] | null;
}
/**
 * One incident as the game sees it. Report it with `resolved` once before dropping it.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "IncidentObservation".
 */
export interface IncidentObservation {
  id: string;
  kind:
    | 'traffic'
    | 'outage'
    | 'gas_leakage'
    | 'flood'
    | 'storm'
    | 'snowstorm'
    | 'heavy_rain'
    | 'protest'
    | 'crime';
  severity: number;
  opened_tick: number;
  status: 'active' | 'recovering' | 'resolved';
  x: number;
  z: number;
  district?: string;
  disruption_id?: string | null;
}
/**
 * Route availability from a unit's position to an incident on the current game graph.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "RouteObservation".
 */
export interface RouteObservation {
  unit_id: string;
  incident_id: string;
  reachable: boolean;
  travel_ticks?: number | null;
}
/**
 * A physical outcome: a unit reached its incident, or finished its service there.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "UnitEvent".
 */
export interface UnitEvent {
  unit_id: string;
  incident_id: string;
  event: 'arrived' | 'cleared';
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ResidentMood".
 */
export interface ResidentMood {
  id: number;
  mood: number;
}
/**
 * The engine's answer for one tick; effects apply in the game from `effective_tick`.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "TickOutcome".
 */
export interface TickOutcome {
  run_id: string;
  run_epoch: number;
  tick: number;
  effective_tick: number;
  status: 'running' | 'completed' | 'removed' | 'interrupted';
  units: UnitView[];
  assignments?: Assignment[];
  releases?: Release[];
  queue?: QueueEntry[];
  orders?: OrderRecord[];
  decisions?: MayorDecisionRecord[];
  resident_actions?: ResidentAction[];
  /**
   * Mode of residents who joined this tick (true = LLM).
   */
  resident_modes?: {
    [k: string]: boolean;
  };
  disruptions_started?: DisruptionRecord[];
  disruptions_ended?: DisruptionRecord[];
  authority: AuthorityView;
  politics: PoliticalStatus;
  mayor: MayorStatus;
  removal?: RemovalRecord | null;
  state_hash: string;
  warnings?: Failure[];
}
/**
 * A unit committed to an incident; the game starts moving it at `effective_tick`.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "Assignment".
 */
export interface Assignment {
  unit_id: string;
  department: 'police' | 'fire' | 'medical';
  incident_id: string;
  origin: 'routine' | 'order';
  order_id?: string | null;
  /**
   * As reported by the game graph.
   */
  travel_ticks: number;
  assigned_tick: number;
  /**
   * effective tick + travel ticks.
   */
  eta_tick: number;
}
/**
 * A unit back in service after its incident was cleared or resolved.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "Release".
 */
export interface Release {
  unit_id: string;
  incident_id: string;
  tick: number;
  reason: 'cleared' | 'incident_resolved';
}
/**
 * Unmet demand of one department at one incident.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "QueueEntry".
 */
export interface QueueEntry {
  incident_id: string;
  department: 'police' | 'fire' | 'medical';
  needed: number;
  reason:
    | 'no_qualified_unit'
    | 'all_units_busy'
    | 'unreachable'
    | 'route_not_reported'
    | 'out_of_service';
  since_tick: number;
}
/**
 * An exceptional department-level order with its origin, units, outcome and cost.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "OrderRecord".
 */
export interface OrderRecord {
  order_id: string;
  decision_id: string;
  origin: OrderOrigin;
  kind: 'dispatch' | 'prioritize';
  department: 'police' | 'fire' | 'medical';
  incident_id: string;
  requested_units: number;
  units?: string[];
  status: 'accepted' | 'rejected';
  reason?: string | null;
  applied_tick: number;
  priority_until_tick?: number | null;
  authority?: OrderAuthority | null;
  outcome?: OrderOutcome;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "OrderOrigin".
 */
export interface OrderOrigin {
  actor?: 'mayor';
  backend: 'baseline' | 'local' | 'api';
  model: string;
  decision_id: string;
}
/**
 * The political cost of one accepted order (rolling allowance and penalty).
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "OrderAuthority".
 */
export interface OrderAuthority {
  /**
   * False for a repeat of the same order key in the window.
   */
  counted: boolean;
  /**
   * kind:department:incident.
   */
  distinct_key: string;
  window_ticks: number;
  /**
   * Distinct accepted orders in the window.
   */
  window_count: number;
  allowance: number;
  penalty: number;
  before: number;
  after: number;
}
/**
 * Measured outcome, filled from later game observations.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "OrderOutcome".
 */
export interface OrderOutcome {
  arrivals?: Arrival[];
  cleared_tick?: number | null;
  incident_resolved_tick?: number | null;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "Arrival".
 */
export interface Arrival {
  unit_id: string;
  tick: number;
}
/**
 * One mayor decision from request to outcome (`decisions.jsonl`).
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MayorDecisionRecord".
 */
export interface MayorDecisionRecord {
  envelope: DecisionEnvelope;
  backend: 'baseline' | 'local' | 'api';
  model: string;
  controller: 'baseline' | 'local' | 'api' | 'hold' | 'degraded';
  options: ActionOption[];
  proposal?: MayorProposal | null;
  outcome: 'pending' | 'accepted' | 'rejected' | 'hold' | 'cancelled' | 'stale';
  reason?: string | null;
  order_id?: string | null;
  latency_ms?: number | null;
  satisfaction_before: SatisfactionPoint;
  /**
   * Observed `outcome_window_ticks` after the apply tick.
   */
  satisfaction_after?: SatisfactionPoint | null;
  /**
   * Opportunities skipped during the same outage (one hold).
   */
  missed_opportunities?: number;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "DecisionEnvelope".
 */
export interface DecisionEnvelope {
  run_id: string;
  run_epoch: number;
  actor_id: string;
  decision_id: string;
  /**
   * SHA-256 of the canonical observation.
   */
  observation_id: string;
  observation_tick: number;
  /**
   * Fixed at request time; never wall-clock dependent.
   */
  apply_tick: number;
  schema_version?: number;
}
/**
 * One permitted mayor action, derived from the recorded incident and unit state.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ActionOption".
 */
export interface ActionOption {
  id: string;
  kind: 'dispatch' | 'prioritize' | 'hold';
  department?: ('police' | 'fire' | 'medical') | null;
  incident_id?: string | null;
  units?: number | null;
  summary: string;
}
/**
 * The model's structured answer: one option id plus an optional public statement.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MayorProposal".
 */
export interface MayorProposal {
  action: string;
  statement?: string;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "SatisfactionPoint".
 */
export interface SatisfactionPoint {
  tick: number;
  value: number;
}
/**
 * A resident decision, delivered in the outcome of its apply tick.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ResidentAction".
 */
export interface ResidentAction {
  resident_id: number;
  decision_id: string;
  action:
    | 'follow_routine'
    | 'go_home'
    | 'visit_venue'
    | 'stay_put'
    | 'peaceful_protest'
    | 'sign_petition'
    | 'vote_retain'
    | 'vote_replace'
    | 'speeding'
    | 'vandalism'
    | 'road_blockade';
  thought?: string;
  apply_tick: number;
  /**
   * True when the model failed: routine behaviour.
   */
  fallback: boolean;
  reason?: string | null;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "AuthorityView".
 */
export interface AuthorityView {
  value: number;
  changes?: AuthorityChange[];
}
/**
 * One change of political authority (0–100). Satisfaction never changes authority.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "AuthorityChange".
 */
export interface AuthorityChange {
  tick: number;
  delta: number;
  value: number;
  reason: 'excess_order' | 'protest_pressure' | 'recovery';
  ref?: string | null;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "PoliticalStatus".
 */
export interface PoliticalStatus {
  authority: number;
  petition: PetitionStatus;
  vote: VoteStatus;
  protest: ProtestStatus;
  removal?: RemovalRecord | null;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "PetitionStatus".
 */
export interface PetitionStatus {
  open: boolean;
  signers: number;
  /**
   * Unique signers needed to call a recall vote.
   */
  threshold: number;
  opened_tick?: number | null;
  cooldown_until?: number | null;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "VoteStatus".
 */
export interface VoteStatus {
  open: boolean;
  opens_tick?: number | null;
  closes_tick?: number | null;
  eligible: number;
  retain: number;
  replace: number;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ProtestStatus".
 */
export interface ProtestStatus {
  /**
   * Unique residents in the protest movement.
   */
  participants: number;
  /**
   * At least the rule's minimum participants.
   */
  active: boolean;
  /**
   * Consecutive ticks at zero authority.
   */
  pressure_ticks: number;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "MayorStatus".
 */
export interface MayorStatus {
  backend: 'baseline' | 'local' | 'api';
  controller: 'baseline' | 'local' | 'api' | 'hold' | 'degraded';
  state: 'idle' | 'deciding' | 'offline' | 'removed';
  pending_decision_id?: string | null;
  next_opportunity_tick?: number | null;
}
/**
 * `POST /api/runs/{run_id}/disruptions`. Reposting the same `request_id` is idempotent.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "DisruptionInjectRequest".
 */
export interface DisruptionInjectRequest {
  run_epoch: number;
  request_id: string;
  disruption: DisruptionSpec;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "DisruptionInjectResponse".
 */
export interface DisruptionInjectResponse {
  disruption: DisruptionRecord;
  /**
   * True when this request_id was already accepted.
   */
  duplicate: boolean;
}
/**
 * `GET /api/catalogs/disruptions`.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "DisruptionCatalogView".
 */
export interface DisruptionCatalogView {
  version: number;
  sha256: string;
  types: DisruptionTypeSpec[];
}
/**
 * Catalog entry (`data/catalogs/disruptions.v1.yaml`).
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "DisruptionTypeSpec".
 */
export interface DisruptionTypeSpec {
  id: 'traffic' | 'outage' | 'gas_leakage' | 'flood' | 'storm' | 'snowstorm' | 'heavy_rain';
  label: string;
  description: string;
  radius_m: number;
  intensity: number;
  duration_ticks: number;
  effects: DisruptionEffects;
  recovery: Recovery;
  incident: IncidentTemplate;
}
/**
 * `GET /api/catalogs/incidents`.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "IncidentCatalogView".
 */
export interface IncidentCatalogView {
  version: number;
  sha256: string;
  kinds: IncidentKindSpec[];
}
/**
 * Catalog entry (`data/catalogs/dispatch.v1.yaml`).
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "IncidentKindSpec".
 */
export interface IncidentKindSpec {
  kind:
    | 'traffic'
    | 'outage'
    | 'gas_leakage'
    | 'flood'
    | 'storm'
    | 'snowstorm'
    | 'heavy_rain'
    | 'protest'
    | 'crime';
  label: string;
  /**
   * Default severity when spawned.
   */
  severity: number;
  needs: Needs;
}
/**
 * `POST /api/runs/{run_id}/residents`: LLM residents only, at most eight per request.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ResidentDecisionRequest".
 */
export interface ResidentDecisionRequest {
  run_epoch: number;
  /**
   * The last tick the game posted; decisions apply at +2.
   */
  tick: number;
  /**
   * @minItems 1
   * @maxItems 8
   */
  residents:
    | [ResidentObservation]
    | [ResidentObservation, ResidentObservation]
    | [ResidentObservation, ResidentObservation, ResidentObservation]
    | [ResidentObservation, ResidentObservation, ResidentObservation, ResidentObservation]
    | [
        ResidentObservation,
        ResidentObservation,
        ResidentObservation,
        ResidentObservation,
        ResidentObservation
      ]
    | [
        ResidentObservation,
        ResidentObservation,
        ResidentObservation,
        ResidentObservation,
        ResidentObservation,
        ResidentObservation
      ]
    | [
        ResidentObservation,
        ResidentObservation,
        ResidentObservation,
        ResidentObservation,
        ResidentObservation,
        ResidentObservation,
        ResidentObservation
      ]
    | [
        ResidentObservation,
        ResidentObservation,
        ResidentObservation,
        ResidentObservation,
        ResidentObservation,
        ResidentObservation,
        ResidentObservation,
        ResidentObservation
      ];
}
/**
 * What one LLM resident sees (RES-05): own state, local conditions, no hidden events.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ResidentObservation".
 */
export interface ResidentObservation {
  id: number;
  activity: string;
  district?: string;
  mood: number;
  /**
   * @maxItems 6
   */
  grievances?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string];
  has_venue?: boolean;
  at_home?: boolean;
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ResidentDecisionAccepted".
 */
export interface ResidentDecisionAccepted {
  run_id: string;
  run_epoch: number;
  model: string;
  tickets: ResidentDecisionTicket[];
}
/**
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ResidentDecisionTicket".
 */
export interface ResidentDecisionTicket {
  resident_id: number;
  decision_id: string;
  apply_tick: number;
}
/**
 * Body of every 4xx answer from the hybrid REST API.
 *
 * This interface was referenced by `AiaProtocol`'s JSON-Schema
 * via the `definition` "ErrorResponse".
 */
export interface ErrorResponse {
  error: Failure;
  failures?: Failure[];
}

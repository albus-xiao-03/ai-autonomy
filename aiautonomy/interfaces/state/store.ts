// Client copy of the run state, kept in step with the engine by the rules of plans/R1.md
// §4.8: a snapshot (re)sets the run; other messages for another run are discarded; deltas
// apply in exact `state_version` order and a gap triggers `sync`.
// REQ: ARCH-03
import {
  isRecord,
  type DecisionRecord,
  type DeltaMessage,
  type RunMessage,
  type RunStatus,
  type SetChange,
  type SnapshotMessage,
  type WorldView,
} from '../net/protocol';
import { Observable } from './observable';
import { Tracks } from './tracks';

/** What `ClientStore.apply` did with a message. */
export type ApplyResult = 'applied' | 'unknown-run' | 'stale' | 'gap' | 'awaiting-snapshot';

/** The world collection whose entities are drawn as interpolated movers. */
export const MOVERS = 'movers';

const MAX_DECISIONS = 500;
const UNSAFE_KEYS: ReadonlySet<string> = new Set(['__proto__', 'prototype', 'constructor']);

export interface ClientStoreOptions {
  /** Ask the engine for a fresh snapshot (sends the `sync` command). */
  readonly requestSync: () => void;
  readonly now?: () => number;
}

export class ClientStore extends Observable {
  runId: string | null = null;
  runEpoch = -1;
  /** `state_version` of the last applied snapshot or delta. */
  stateVersion = -1;
  tick = 0;
  status: RunStatus | null = null;
  world: WorldView | null = null;
  metrics: Readonly<Record<string, number>> = {};
  decisions: readonly DecisionRecord[] = [];
  /** True after a gap: deltas are ignored until the requested snapshot arrives. */
  awaitingSnapshot = false;
  /** Interpolated positions of the `movers` collection. */
  readonly movers = new Tracks();
  readonly #requestSync: () => void;
  readonly #now: () => number;

  constructor(options: ClientStoreOptions) {
    super();
    this.#requestSync = options.requestSync;
    this.#now = options.now ?? (() => performance.now());
  }

  /** A keyed world collection by name (M0: `movers`). */
  collection(name: string): Readonly<Record<string, unknown>> | undefined {
    if (this.world === null) return undefined;
    const value = (this.world as unknown as Record<string, unknown>)[name];
    return isRecord(value) ? value : undefined;
  }

  apply(message: RunMessage): ApplyResult {
    if (message.type === 'snapshot') return this.#snapshot(message);
    if (message.run_id !== this.runId) return 'unknown-run';
    if (message.type === 'delta') return this.#delta(message);
    if (message.state_version < this.stateVersion) return 'stale';
    switch (message.type) {
      case 'run_status':
        this.status = message.status;
        break;
      case 'metrics':
        this.metrics = { ...this.metrics, ...message.values };
        break;
      case 'decision':
        this.decisions = [...this.decisions.slice(1 - MAX_DECISIONS), message.record];
        break;
    }
    this.notify();
    return 'applied';
  }

  #snapshot(message: SnapshotMessage): ApplyResult {
    if (message.run_id !== this.runId) {
      this.metrics = {};
      this.decisions = [];
    }
    this.runId = message.run_id;
    this.runEpoch = message.run_epoch;
    this.stateVersion = message.state_version;
    this.tick = message.tick;
    this.status = message.status;
    this.world = message.world;
    this.awaitingSnapshot = false;
    this.movers.reset(Object.values(message.world.movers), this.#now());
    this.notify();
    return 'applied';
  }

  #delta(message: DeltaMessage): ApplyResult {
    if (this.awaitingSnapshot) return 'awaiting-snapshot';
    if (message.state_version <= this.stateVersion) return 'stale';
    if (message.state_version > this.stateVersion + 1) {
      this.awaitingSnapshot = true;
      this.#requestSync();
      this.notify();
      return 'gap';
    }
    const world = this.world;
    if (world !== null) {
      const now = this.#now();
      let segmentStarted = false;
      for (const change of message.changes) {
        if (change.op === 'set') {
          this.#set(world, change, now);
          continue;
        }
        if (UNSAFE_KEYS.has(change.collection) || UNSAFE_KEYS.has(change.id)) continue;
        const items = ensureCollection(world, change.collection);
        const isMover = change.collection === MOVERS;
        if (isMover && !segmentStarted) {
          this.movers.beginUpdate(now);
          segmentStarted = true;
        }
        if (change.op === 'upsert') {
          items[change.id] = change.value;
          const { x, y } = change.value;
          if (isMover && typeof x === 'number' && typeof y === 'number') {
            this.movers.upsert(change.id, x, y);
          }
        } else {
          Reflect.deleteProperty(items, change.id);
          if (isMover) this.movers.remove(change.id);
        }
      }
    }
    this.stateVersion = message.state_version;
    this.tick = message.tick;
    this.notify();
    return 'applied';
  }

  #set(world: WorldView, change: SetChange, now: number): void {
    if (UNSAFE_KEYS.has(change.field)) return;
    (world as unknown as Record<string, unknown>)[change.field] = change.value;
    if (change.field === MOVERS) this.movers.reset(Object.values(change.value), now);
  }
}

function ensureCollection(world: WorldView, name: string): Record<string, unknown> {
  const root = world as unknown as Record<string, unknown>;
  const existing = root[name];
  if (isRecord(existing)) return existing;
  const created: Record<string, unknown> = {};
  root[name] = created;
  return created;
}

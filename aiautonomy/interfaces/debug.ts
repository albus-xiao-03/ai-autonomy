// Read-only debug handle `window.__aia` for e2e tests and manual inspection.
import type { AckRecord } from './net/commands';
import type { RunState, Speed } from './net/protocol';
import type { Session } from './net/session';
import type { ConnectionState } from './net/socket';
import type { Point, ViewState } from './render/view';
import type { Viewport, WebGlStatus } from './render/viewport';

export interface AiaDebug {
  readonly connection: ConnectionState;
  readonly runId: string | null;
  readonly runEpoch: number;
  readonly stateVersion: number;
  readonly tick: number;
  readonly state: RunState | null;
  readonly speed: Speed | null;
  readonly waiting: boolean;
  readonly moverCount: number;
  readonly frames: number;
  readonly webgl: WebGlStatus;
  readonly view: ViewState | null;
  readonly selectedId: string | null;
  /** Recent command acks with their measured latency, oldest first. */
  readonly acks: readonly AckRecord[];
  moverScreenPosition(index: number): Point | null;
  focusMover(index: number): boolean;
}

declare global {
  interface Window {
    __aia?: AiaDebug;
  }
}

export function installDebugHandle(session: Session, viewport: Viewport): void {
  const { store } = session;
  window.__aia = {
    get connection() {
      return session.connection;
    },
    get runId() {
      return store.runId;
    },
    get runEpoch() {
      return store.runEpoch;
    },
    get stateVersion() {
      return store.stateVersion;
    },
    get tick() {
      return store.tick;
    },
    get state() {
      return store.status?.state ?? null;
    },
    get speed() {
      return store.status?.speed ?? null;
    },
    get waiting() {
      return store.status?.waiting_for_inference ?? false;
    },
    get moverCount() {
      return store.movers.count;
    },
    get frames() {
      return viewport.frameStats.frames;
    },
    get webgl() {
      return viewport.webgl;
    },
    get view() {
      return viewport.view;
    },
    get selectedId() {
      return session.selection.id;
    },
    get acks() {
      return session.commands.history;
    },
    moverScreenPosition: (index) => viewport.moverScreenPosition(index),
    focusMover: (index) => viewport.focusMover(index),
  };
}

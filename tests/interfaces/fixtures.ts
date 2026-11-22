// Shared fixtures for the interface unit tests: protocol messages and a fake WebSocket.
import type {
  Change,
  DeltaMessage,
  MetricsMessage,
  RunStatus,
  RunStatusMessage,
  SnapshotMessage,
} from '../../aiautonomy/interfaces/net/protocol';
import type { SocketLike } from '../../aiautonomy/interfaces/net/socket';

export const RUN = 'run-a';

export function status(overrides: Partial<RunStatus> = {}): RunStatus {
  return {
    state: 'idle',
    speed: '1x',
    ticks_per_second: 5,
    duration: 300,
    waiting_for_inference: false,
    scenario: 'toy',
    seed: 7,
    engine_version: '0.1.0',
    ...overrides,
  };
}

export function snapshot(overrides: Partial<SnapshotMessage> = {}): SnapshotMessage {
  return {
    type: 'snapshot',
    run_id: RUN,
    run_epoch: 1,
    state_version: 0,
    tick: 0,
    status: status(),
    world: {
      clock: { tick: 0, day: 1, minute_of_day: 420 },
      bounds: { min_x: -100, min_y: -50, max_x: 100, max_y: 50 },
      movers: {
        m1: { id: 'm1', x: 0, y: 0, kind: 'walker' },
        m2: { id: 'm2', x: 10, y: -5, kind: 'walker' },
      },
    },
    ...overrides,
  };
}

export function delta(
  stateVersion: number,
  changes: Change[],
  overrides: Partial<DeltaMessage> = {},
): DeltaMessage {
  return {
    type: 'delta',
    run_id: RUN,
    run_epoch: 1,
    state_version: stateVersion,
    tick: stateVersion,
    changes,
    ...overrides,
  };
}

export function moveTo(id: string, x: number, y: number): Change {
  return { op: 'upsert', collection: 'movers', id, value: { id, x, y, kind: 'walker' } };
}

export function runStatus(
  stateVersion: number,
  overrides: Partial<RunStatus> = {},
  runId = RUN,
): RunStatusMessage {
  return {
    type: 'run_status',
    run_id: runId,
    run_epoch: 1,
    state_version: stateVersion,
    tick: stateVersion,
    status: status(overrides),
  };
}

export function metrics(stateVersion: number, values: Record<string, number>): MetricsMessage {
  return {
    type: 'metrics',
    run_id: RUN,
    run_epoch: 1,
    state_version: stateVersion,
    tick: stateVersion,
    values,
  };
}

/** In-memory stand-in for the browser WebSocket. */
export class FakeSocket implements SocketLike {
  static instances: FakeSocket[] = [];
  readonly url: string;
  readyState = 0;
  readonly sent: string[] = [];
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeSocket.instances.push(this);
  }

  static latest(): FakeSocket {
    const socket = FakeSocket.instances.at(-1);
    if (socket === undefined) throw new Error('no socket created');
    return socket;
  }

  open(): void {
    this.readyState = 1;
    this.onopen?.({} as Event);
  }

  receive(message: unknown): void {
    this.onmessage?.({ data: JSON.stringify(message) } as MessageEvent);
  }

  drop(): void {
    this.readyState = 3;
    this.onclose?.({} as CloseEvent);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.drop();
  }

  /** Sent commands, parsed. */
  commands(): Record<string, unknown>[] {
    return this.sent.map((text) => JSON.parse(text) as Record<string, unknown>);
  }
}

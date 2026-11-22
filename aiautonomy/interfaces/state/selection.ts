// The selected entity and the result of its `inspect` command.
// REQ: VIS-01
import type { AckMessage } from '../net/protocol';
import { Observable } from './observable';

export type InspectStatus = 'idle' | 'loading' | 'ok' | 'error';

export interface SelectionState {
  readonly id: string | null;
  readonly status: InspectStatus;
  readonly result: Readonly<Record<string, unknown>> | null;
  readonly error: string | null;
  /** Tick at which the inspection was requested. */
  readonly tick: number | null;
}

const EMPTY: SelectionState = { id: null, status: 'idle', result: null, error: null, tick: null };

export class Selection extends Observable {
  state: SelectionState = EMPTY;
  #token = 0;

  get id(): string | null {
    return this.state.id;
  }

  /** Select `id` and mark its inspection pending; returns a token for `resolve`. */
  begin(id: string, tick: number): number {
    this.#token += 1;
    this.state = { id, status: 'loading', result: null, error: null, tick };
    this.notify();
    return this.#token;
  }

  /** Fill in the inspection result, unless the selection changed meanwhile. */
  resolve(token: number, ack: AckMessage): void {
    if (token !== this.#token) return;
    this.state = ack.ok
      ? { ...this.state, status: 'ok', result: ack.result ?? {} }
      : { ...this.state, status: 'error', error: ack.error ?? 'inspect failed' };
    this.notify();
  }

  clear(): void {
    this.#token += 1;
    if (this.state.id === null) return;
    this.state = EMPTY;
    this.notify();
  }
}

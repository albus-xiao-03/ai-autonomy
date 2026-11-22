// Command sender: attaches a client-generated `cmd_id`, matches the engine's single ack
// and measures ack latency for the telemetry report (plans/R1.md §4.8, §5.12).
// REQ: VIS-04, ARCH-03
import { SampleWindow } from '../state/samples';
import type { AckMessage, ClientMessage, CommandBody, CommandType } from './protocol';

export interface AckRecord {
  readonly cmd_id: string;
  readonly type: CommandType;
  readonly ok: boolean;
  readonly error: string | null;
  readonly latency_ms: number;
}

export interface CommandSenderOptions {
  /** Sends one text frame; returns false when the connection is not open. */
  readonly transport: (text: string) => boolean;
  readonly now?: () => number;
  readonly idPrefix?: string;
  readonly historySize?: number;
}

interface Pending {
  readonly type: CommandType;
  readonly sentAt: number;
  readonly resolve: (ack: AckMessage) => void;
}

export class CommandSender {
  /** Ack latencies (ms) of the most recent commands. */
  readonly latency = new SampleWindow(256);
  /** The most recent acks, oldest first. */
  readonly history: AckRecord[] = [];
  readonly #transport: (text: string) => boolean;
  readonly #now: () => number;
  readonly #prefix: string;
  readonly #historySize: number;
  readonly #pending = new Map<string, Pending>();
  #seq = 0;

  constructor(options: CommandSenderOptions) {
    this.#transport = options.transport;
    this.#now = options.now ?? (() => performance.now());
    this.#prefix = options.idPrefix ?? Math.random().toString(36).slice(2, 8);
    this.#historySize = options.historySize ?? 64;
  }

  get pendingCount(): number {
    return this.#pending.size;
  }

  /** Send a command; resolves with its ack, or a synthetic failed ack if it cannot be sent. */
  send(body: CommandBody): Promise<AckMessage> {
    this.#seq += 1;
    const cmdId = `${this.#prefix}-${this.#seq}`;
    const command: ClientMessage = { ...body, cmd_id: cmdId };
    const sentAt = this.#now();
    if (!this.#transport(JSON.stringify(command))) {
      return Promise.resolve(failedAck(cmdId, 'not connected'));
    }
    return new Promise((resolve) => {
      this.#pending.set(cmdId, { type: body.type, sentAt, resolve });
    });
  }

  /** Match an ack to its command; returns the record, or null for an unknown `cmd_id`. */
  handleAck(ack: AckMessage): AckRecord | null {
    const pending = this.#pending.get(ack.cmd_id);
    if (pending === undefined) return null;
    this.#pending.delete(ack.cmd_id);
    const latency = Math.max(0, this.#now() - pending.sentAt);
    this.latency.push(latency);
    const record: AckRecord = {
      cmd_id: ack.cmd_id,
      type: pending.type,
      ok: ack.ok,
      error: ack.error,
      latency_ms: latency,
    };
    this.history.push(record);
    if (this.history.length > this.#historySize) this.history.shift();
    pending.resolve(ack);
    return record;
  }

  /** Resolve every outstanding command with a failed ack (the connection dropped). */
  failPending(reason: string): void {
    const pending = [...this.#pending];
    this.#pending.clear();
    for (const [cmdId, entry] of pending) entry.resolve(failedAck(cmdId, reason));
  }
}

function failedAck(cmdId: string, error: string): AckMessage {
  return { type: 'ack', cmd_id: cmdId, ok: false, error, result: null };
}

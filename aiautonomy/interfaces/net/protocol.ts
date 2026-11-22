// App-facing view of the generated protocol types (plans/R1.md §4.8). Only this module
// imports `protocol.gen.ts`, so a schema rename is fixed here, not across the app.
// REQ: ARCH-03
import type { AckMessage, ClientMessage, ServerMessage } from './protocol.gen';

export type * from './protocol.gen';

/** Server messages that belong to a run (everything except `ack`). */
export type RunMessage = Exclude<ServerMessage, AckMessage>;

export type CommandType = ClientMessage['type'];

type DistributiveOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never;

/** A command before the sender attaches its `cmd_id`. */
export type CommandBody = DistributiveOmit<ClientMessage, 'cmd_id'>;

const SERVER_TYPES: ReadonlySet<string> = new Set([
  'snapshot',
  'delta',
  'run_status',
  'metrics',
  'decision',
  'ack',
]);

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Parse one WebSocket text frame. Returns null for anything that is not a recognizable
 * server message (malformed JSON, unknown `type`, missing envelope fields).
 */
export function parseServerMessage(text: string): ServerMessage | null {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return null;
  }
  if (!isRecord(data) || typeof data.type !== 'string' || !SERVER_TYPES.has(data.type)) {
    return null;
  }
  if (data.type === 'ack') {
    return typeof data.cmd_id === 'string' && typeof data.ok === 'boolean'
      ? (data as unknown as AckMessage)
      : null;
  }
  const envelope =
    typeof data.run_id === 'string' &&
    Number.isInteger(data.state_version) &&
    typeof data.tick === 'number';
  return envelope ? (data as unknown as ServerMessage) : null;
}

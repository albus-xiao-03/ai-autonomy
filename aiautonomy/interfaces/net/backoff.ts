// Reconnect delays for the engine WebSocket.
// REQ: ARCH-03

export interface BackoffOptions {
  readonly baseMs: number;
  readonly maxMs: number;
  readonly factor: number;
  /** Relative spread around the nominal delay, 0..1. */
  readonly jitter: number;
}

export const DEFAULT_BACKOFF: BackoffOptions = { baseMs: 250, maxMs: 5000, factor: 2, jitter: 0.2 };

/** Delay before reconnect attempt `attempt` (0-based): exponential, jittered, capped. */
export function backoffDelay(
  attempt: number,
  options: BackoffOptions = DEFAULT_BACKOFF,
  random: () => number = Math.random,
): number {
  const nominal = Math.min(options.maxMs, options.baseMs * options.factor ** Math.max(0, attempt));
  const spread = 1 - options.jitter + 2 * options.jitter * random();
  return Math.min(options.maxMs, Math.max(0, Math.round(nominal * spread)));
}

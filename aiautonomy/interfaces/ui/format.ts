// Text formatting for the panels. Every value ends up in a Preact text node (docs/engine-plan.md
// §5.12: model-written text is plain text only).
import type { HealthResponse, Speed } from '../net/protocol';

export const SPEEDS: readonly Speed[] = ['1x', '2x', '4x', 'max'];

export const SPEED_LABEL: Readonly<Record<Speed, string>> = {
  '1x': '1×',
  '2x': '2×',
  '4x': '4×',
  max: 'max',
};

function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

/** `Day d · HH:MM` from the simulated clock. */
export function formatClock(day: number, minuteOfDay: number): string {
  const minutes = ((Math.floor(minuteOfDay) % 1440) + 1440) % 1440;
  return `Day ${day} · ${pad2(Math.floor(minutes / 60))}:${pad2(minutes % 60)}`;
}

/** Engine version stamp, e.g. `engine 0.1.0 · 1a2b3c4`; the sha is omitted when the version already carries it. */
export function formatStamp(health: HealthResponse | null): string {
  if (health === null) return 'engine —';
  const version = health.engine_version;
  const sha = health.git_sha?.slice(0, 7) ?? '';
  return sha === '' || version.includes(sha) ? `engine ${version}` : `engine ${version} · ${sha}`;
}

/** True when the engine reports uncommitted changes its version string does not already show. */
export function showDirty(health: HealthResponse | null): boolean {
  return health?.dirty === true && !health.engine_version.includes('dirty');
}

export function formatMs(value: number): string {
  return Number.isFinite(value) ? value.toFixed(1) : '—';
}

/** An id for display; long ids keep both ends, where run ids differ. */
export function shortId(id: string | null): string {
  if (id === null) return '—';
  return id.length > 26 ? `${id.slice(0, 12)}…${id.slice(-12)}` : id;
}

/** A JSON value as one line of plain text. */
export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === 'string') return value;
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  const text = JSON.stringify(value);
  return text.length > 160 ? `${text.slice(0, 157)}…` : text;
}

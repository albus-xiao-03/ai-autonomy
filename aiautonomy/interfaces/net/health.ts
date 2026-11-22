// Engine version stamp from `GET /api/health`.
// REQ: ARCH-01
import { isRecord, type HealthResponse } from './protocol';

export function parseHealth(body: unknown): HealthResponse | null {
  if (!isRecord(body) || typeof body.ok !== 'boolean' || typeof body.engine_version !== 'string') {
    return null;
  }
  return {
    ok: body.ok,
    engine_version: body.engine_version,
    git_sha: typeof body.git_sha === 'string' ? body.git_sha : null,
    dirty: typeof body.dirty === 'boolean' ? body.dirty : null,
  };
}

export async function fetchHealth(): Promise<HealthResponse | null> {
  try {
    const response = await fetch('/api/health', { cache: 'no-store' });
    if (!response.ok) return null;
    const body: unknown = await response.json();
    return parseHealth(body);
  } catch {
    return null;
  }
}

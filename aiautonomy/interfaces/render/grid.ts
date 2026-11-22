// Ground grid lines for `world.bounds`.
// REQ: VIS-01
import type { Bounds } from '../net/protocol';

/** Round a spacing up to 1, 2 or 5 times a power of ten. */
export function niceStep(target: number): number {
  if (!(target > 0) || !Number.isFinite(target)) return 1;
  const power = 10 ** Math.floor(Math.log10(target));
  const m = target / power;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * power;
}

/** Line segments as flat [x1, y1, x2, y2, ...] world coordinates. */
export interface GridLines {
  readonly step: number;
  readonly minor: number[];
  /** Every fifth line, plus the world outline. */
  readonly major: number[];
}

export function gridLines(bounds: Bounds, divisions = 20): GridLines {
  const { min_x: x0, min_y: y0, max_x: x1, max_y: y1 } = bounds;
  const step = niceStep(Math.max(x1 - x0, y1 - y0) / divisions);
  const minor: number[] = [];
  const major: number[] = [];
  for (let i = Math.ceil(x0 / step); i * step <= x1; i++) {
    (i % 5 === 0 ? major : minor).push(i * step, y0, i * step, y1);
  }
  for (let j = Math.ceil(y0 / step); j * step <= y1; j++) {
    (j % 5 === 0 ? major : minor).push(x0, j * step, x1, j * step);
  }
  major.push(x0, y0, x1, y0, x1, y0, x1, y1, x1, y1, x0, y1, x0, y1, x0, y0);
  return { step, minor, major };
}

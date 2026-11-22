// Positions of moving entities at the previous and current tick, interpolated every frame
// (plans/R1.md §5.12: "Deltas are applied at the tick rate and interpolated each frame").
// REQ: VIS-01

/** Shortest interpolation segment (one frame at 60 Hz). */
export const MIN_SEGMENT_MS = 16;
/** Longest segment: used for a single step and for the first tick after a pause. */
export const MAX_SEGMENT_MS = 250;

/**
 * Struct-of-arrays store of entity positions. Each update starts a new segment from the
 * position currently on screen to the new tick's position, so motion stays continuous even
 * when ticks arrive early, late or coalesced. Reads are allocation-free.
 */
export class Tracks {
  /** Entity id per slot; slots are dense (removal swaps the last slot in). */
  ids: string[] = [];
  prevX: Float64Array;
  prevY: Float64Array;
  currX: Float64Array;
  currY: Float64Array;
  /** Time (ms, performance.now) at which the current segment started. */
  segmentStart = 0;
  /** Duration of the current segment in ms. */
  segmentMs = MAX_SEGMENT_MS;
  #lastUpdate = Number.NEGATIVE_INFINITY;
  readonly #slots = new Map<string, number>();

  constructor(capacity = 64) {
    this.prevX = new Float64Array(capacity);
    this.prevY = new Float64Array(capacity);
    this.currX = new Float64Array(capacity);
    this.currY = new Float64Array(capacity);
  }

  get count(): number {
    return this.ids.length;
  }

  slotOf(id: string): number | undefined {
    return this.#slots.get(id);
  }

  /** Progress through the current segment, 0..1. */
  alpha(now: number): number {
    const a = (now - this.segmentStart) / this.segmentMs;
    return a >= 1 ? 1 : a > 0 ? a : 0;
  }

  x(slot: number, alpha: number): number {
    const from = this.prevX[slot] ?? 0;
    return from + ((this.currX[slot] ?? 0) - from) * alpha;
  }

  y(slot: number, alpha: number): number {
    const from = this.prevY[slot] ?? 0;
    return from + ((this.currY[slot] ?? 0) - from) * alpha;
  }

  /** Replace everything (snapshot): entities appear at their positions without motion. */
  reset(entities: Iterable<unknown>, now: number): void {
    this.ids = [];
    this.#slots.clear();
    for (const entity of entities) {
      if (isPositioned(entity)) this.upsert(entity.id, entity.x, entity.y);
    }
    this.segmentStart = now;
    this.segmentMs = MAX_SEGMENT_MS;
    this.#lastUpdate = Number.NEGATIVE_INFINITY;
  }

  /**
   * Start a new segment at `now`, before a tick's upserts: what is on screen becomes the
   * starting point, and the segment lasts as long as the gap since the previous update.
   */
  beginUpdate(now: number): void {
    const a = this.alpha(now);
    for (let i = 0; i < this.ids.length; i++) {
      this.prevX[i] = this.x(i, a);
      this.prevY[i] = this.y(i, a);
    }
    const gap = now - this.#lastUpdate;
    this.segmentMs =
      gap < MIN_SEGMENT_MS ? MIN_SEGMENT_MS : gap > MAX_SEGMENT_MS ? MAX_SEGMENT_MS : gap;
    this.segmentStart = now;
    this.#lastUpdate = now;
  }

  /** Set the current-tick position; a new entity starts at rest at that position. */
  upsert(id: string, x: number, y: number): void {
    const slot = this.#slots.get(id);
    if (slot !== undefined) {
      this.currX[slot] = x;
      this.currY[slot] = y;
      return;
    }
    const next = this.ids.length;
    if (next >= this.prevX.length) this.#grow(next + 1);
    this.ids.push(id);
    this.#slots.set(id, next);
    this.prevX[next] = x;
    this.prevY[next] = y;
    this.currX[next] = x;
    this.currY[next] = y;
  }

  remove(id: string): boolean {
    const slot = this.#slots.get(id);
    if (slot === undefined) return false;
    const last = this.ids.length - 1;
    const lastId = this.ids[last];
    if (slot !== last && lastId !== undefined) {
      this.ids[slot] = lastId;
      this.#slots.set(lastId, slot);
      this.prevX[slot] = this.prevX[last] ?? 0;
      this.prevY[slot] = this.prevY[last] ?? 0;
      this.currX[slot] = this.currX[last] ?? 0;
      this.currY[slot] = this.currY[last] ?? 0;
    }
    this.ids.pop();
    this.#slots.delete(id);
    return true;
  }

  /** Id of the entity closest to (x, y) within `radius`, at interpolation `alpha`. */
  nearest(x: number, y: number, radius: number, alpha: number): string | null {
    let best = -1;
    let bestDistance2 = radius * radius;
    for (let i = 0; i < this.ids.length; i++) {
      const dx = this.x(i, alpha) - x;
      const dy = this.y(i, alpha) - y;
      const distance2 = dx * dx + dy * dy;
      if (distance2 <= bestDistance2) {
        bestDistance2 = distance2;
        best = i;
      }
    }
    return best < 0 ? null : (this.ids[best] ?? null);
  }

  #grow(minimum: number): void {
    let capacity = Math.max(1, this.prevX.length * 2);
    while (capacity < minimum) capacity *= 2;
    this.prevX = grow(this.prevX, capacity);
    this.prevY = grow(this.prevY, capacity);
    this.currX = grow(this.currX, capacity);
    this.currY = grow(this.currY, capacity);
  }
}

function grow(values: Float64Array, capacity: number): Float64Array {
  const next = new Float64Array(capacity);
  next.set(values);
  return next;
}

function isPositioned(value: unknown): value is { id: string; x: number; y: number } {
  if (typeof value !== 'object' || value === null) return false;
  const entity = value as Record<string, unknown>;
  return (
    typeof entity.id === 'string' &&
    typeof entity.x === 'number' &&
    Number.isFinite(entity.x) &&
    typeof entity.y === 'number' &&
    Number.isFinite(entity.y)
  );
}

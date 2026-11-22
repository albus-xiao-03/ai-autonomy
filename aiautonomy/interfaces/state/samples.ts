/** Fixed-size ring buffer of numeric samples with allocation-free percentiles. */
export class SampleWindow {
  readonly capacity: number;
  readonly #values: Float64Array;
  readonly #scratch: Float64Array;
  #next = 0;
  #size = 0;

  constructor(capacity: number) {
    this.capacity = Math.max(1, Math.floor(capacity));
    this.#values = new Float64Array(this.capacity);
    this.#scratch = new Float64Array(this.capacity);
  }

  get count(): number {
    return this.#size;
  }

  push(value: number): void {
    this.#values[this.#next] = value;
    this.#next = (this.#next + 1) % this.capacity;
    if (this.#size < this.capacity) this.#size += 1;
  }

  clear(): void {
    this.#next = 0;
    this.#size = 0;
  }

  /** Nearest-rank percentile, `p` in (0, 100]; NaN when the window is empty. */
  percentile(p: number): number {
    const size = this.#size;
    if (size === 0) return Number.NaN;
    const scratch = this.#scratch;
    scratch.fill(Number.POSITIVE_INFINITY);
    for (let i = 0; i < size; i++) scratch[i] = this.#values[i] ?? 0;
    scratch.sort();
    const rank = Math.min(size, Math.max(1, Math.ceil((p / 100) * size)));
    return scratch[rank - 1] ?? Number.NaN;
  }
}

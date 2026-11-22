/** Minimal change notification shared by the store, the session and the UI hooks. */
export class Observable {
  readonly #listeners = new Set<() => void>();

  subscribe(listener: () => void): () => void {
    this.#listeners.add(listener);
    return () => {
      this.#listeners.delete(listener);
    };
  }

  protected notify(): void {
    for (const listener of this.#listeners) listener();
  }
}

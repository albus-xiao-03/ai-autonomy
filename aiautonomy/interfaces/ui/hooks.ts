import { useEffect, useRef, useState } from 'preact/hooks';
import type { Observable } from '../state/observable';

/**
 * Re-render when `source` changes and `select()` returns a different value (Object.is).
 * Selectors should return primitives or objects the source replaces on change.
 */
export function useObservable<T>(source: Observable, select: () => T): T {
  const [value, setValue] = useState<T>(select);
  const selectRef = useRef(select);
  selectRef.current = select;
  useEffect(() => {
    const update = (): void => {
      setValue(() => selectRef.current());
    };
    update();
    return source.subscribe(update);
  }, [source]);
  return value;
}

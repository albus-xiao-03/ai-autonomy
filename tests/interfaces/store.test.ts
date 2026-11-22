import { describe, expect, it, vi } from 'vitest';
import { ClientStore } from '../../aiautonomy/interfaces/state/store';
import { delta, metrics, moveTo, RUN, runStatus, snapshot, status } from './fixtures';

function makeStore(now: () => number = () => 0) {
  const requestSync = vi.fn<() => void>();
  return { store: new ClientStore({ requestSync, now }), requestSync };
}

// @req ARCH-03
describe('ClientStore applies the engine protocol (@req ARCH-03)', () => {
  it('applies a snapshot: run identity, status, world and mover positions', () => {
    const { store } = makeStore();
    expect(store.apply(snapshot({ state_version: 4, tick: 9, run_epoch: 3 }))).toBe('applied');
    expect(store.runId).toBe(RUN);
    expect(store.runEpoch).toBe(3);
    expect(store.stateVersion).toBe(4);
    expect(store.tick).toBe(9);
    expect(store.status?.state).toBe('idle');
    expect(store.world?.clock.minute_of_day).toBe(420);
    expect(store.movers.count).toBe(2);
    const slot = store.movers.slotOf('m2') ?? -1;
    expect([store.movers.x(slot, 1), store.movers.y(slot, 1)]).toEqual([10, -5]);
  });

  it('applies delta upserts, removes and singleton sets', () => {
    const { store } = makeStore();
    store.apply(snapshot());
    const result = store.apply(
      delta(1, [
        moveTo('m1', 3, 4),
        moveTo('m3', -7, 2),
        { op: 'remove', collection: 'movers', id: 'm2' },
        { op: 'set', field: 'clock', value: { tick: 1, day: 1, minute_of_day: 421 } },
      ]),
    );
    expect(result).toBe('applied');
    expect(store.stateVersion).toBe(1);
    expect(store.tick).toBe(1);
    expect(Object.keys(store.world?.movers ?? {}).sort()).toEqual(['m1', 'm3']);
    expect(store.world?.clock.minute_of_day).toBe(421);
    expect(store.movers.count).toBe(2);
    expect(store.movers.slotOf('m2')).toBeUndefined();
    const m1 = store.movers.slotOf('m1') ?? -1;
    expect([store.movers.x(m1, 1), store.movers.y(m1, 1)]).toEqual([3, 4]);
  });

  it('keeps collections keyed by name, creating new ones on first upsert', () => {
    const { store } = makeStore();
    store.apply(snapshot());
    store.apply(delta(1, [{ op: 'upsert', collection: 'units', id: 'u1', value: { id: 'u1' } }]));
    expect(store.collection('units')).toEqual({ u1: { id: 'u1' } });
    expect(store.collection('movers')).toHaveProperty('m1');
    expect(store.collection('clock')).toEqual({ tick: 0, day: 1, minute_of_day: 420 });
    expect(store.collection('missing')).toBeUndefined();
  });

  it('discards every non-snapshot message before the first snapshot', () => {
    const { store } = makeStore();
    expect(store.apply(delta(1, [moveTo('m1', 1, 1)]))).toBe('unknown-run');
    expect(store.apply(runStatus(0))).toBe('unknown-run');
    expect(store.runId).toBeNull();
  });

  it('discards messages whose run_id differs from the current run', () => {
    const { store } = makeStore();
    store.apply(snapshot());
    expect(store.apply(delta(1, [moveTo('m1', 1, 1)], { run_id: 'run-old' }))).toBe('unknown-run');
    expect(store.apply(runStatus(0, { state: 'running' }, 'run-old'))).toBe('unknown-run');
    expect(store.stateVersion).toBe(0);
    expect(store.status?.state).toBe('idle');
  });

  it('discards a delta whose state_version is not newer than the last applied', () => {
    const { store } = makeStore();
    store.apply(snapshot({ state_version: 5 }));
    expect(store.apply(delta(5, [moveTo('m1', 9, 9)]))).toBe('stale');
    expect(store.apply(delta(3, [moveTo('m1', 9, 9)]))).toBe('stale');
    expect(store.apply(delta(6, [moveTo('m1', 1, 1)]))).toBe('applied');
    expect(store.apply(delta(6, [moveTo('m1', 9, 9)]))).toBe('stale');
    const m1 = store.movers.slotOf('m1') ?? -1;
    expect(store.movers.x(m1, 1)).toBe(1);
  });

  it('sends one sync on a gap and ignores deltas until the next snapshot', () => {
    const { store, requestSync } = makeStore();
    store.apply(snapshot({ state_version: 2 }));
    expect(store.apply(delta(4, [moveTo('m1', 9, 9)]))).toBe('gap');
    expect(requestSync).toHaveBeenCalledTimes(1);
    expect(store.awaitingSnapshot).toBe(true);
    expect(store.apply(delta(3, [moveTo('m1', 9, 9)]))).toBe('awaiting-snapshot');
    expect(store.apply(delta(5, [moveTo('m1', 9, 9)]))).toBe('awaiting-snapshot');
    expect(requestSync).toHaveBeenCalledTimes(1);
    expect(store.stateVersion).toBe(2);

    store.apply(snapshot({ state_version: 5, tick: 5 }));
    expect(store.awaitingSnapshot).toBe(false);
    expect(store.apply(delta(6, [moveTo('m1', 2, 2)]))).toBe('applied');
  });

  it('lets a snapshot always reset the run, even with a lower state_version', () => {
    const { store } = makeStore();
    store.apply(snapshot({ state_version: 40, tick: 40 }));
    store.apply(metrics(40, { trips: 3 }));
    const reset = snapshot({ run_id: 'run-b', run_epoch: 2, state_version: 0, tick: 0 });
    expect(store.apply(reset)).toBe('applied');
    expect(store.runId).toBe('run-b');
    expect(store.runEpoch).toBe(2);
    expect(store.stateVersion).toBe(0);
    expect(store.tick).toBe(0);
    expect(store.metrics).toEqual({});
    expect(store.apply(delta(1, [moveTo('m1', 1, 1)], { run_id: 'run-b' }))).toBe('applied');
  });

  it('applies run_status and metrics unless their state_version is older', () => {
    const { store } = makeStore();
    store.apply(snapshot({ state_version: 3 }));
    expect(store.apply(runStatus(3, { state: 'running', waiting_for_inference: true }))).toBe(
      'applied',
    );
    expect(store.status).toEqual(status({ state: 'running', waiting_for_inference: true }));
    expect(store.apply(runStatus(2, { state: 'paused' }))).toBe('stale');
    expect(store.status?.state).toBe('running');
    expect(store.apply(metrics(3, { trips: 1, delay: 2.5 }))).toBe('applied');
    expect(store.apply(metrics(4, { trips: 2 }))).toBe('applied');
    expect(store.apply(metrics(1, { trips: 99 }))).toBe('stale');
    expect(store.metrics).toEqual({ trips: 2, delay: 2.5 });
    // run_status and metrics never advance state_version; only deltas do.
    expect(store.stateVersion).toBe(3);
  });

  it('ignores prototype-polluting keys in changes', () => {
    const { store } = makeStore();
    store.apply(snapshot());
    store.apply(
      delta(1, [
        { op: 'upsert', collection: '__proto__', id: 'x', value: { polluted: true } },
        { op: 'upsert', collection: 'movers', id: '__proto__', value: { polluted: true } },
        { op: 'set', field: 'constructor', value: { polluted: true } },
      ]),
    );
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
    expect(store.movers.count).toBe(2);
    expect(store.stateVersion).toBe(1);
  });

  it('notifies subscribers once per applied message and not for discarded ones', () => {
    const { store } = makeStore();
    const listener = vi.fn<() => void>();
    store.subscribe(listener);
    store.apply(snapshot());
    store.apply(delta(1, [moveTo('m1', 1, 1)]));
    store.apply(delta(1, [moveTo('m1', 1, 1)]));
    store.apply(runStatus(0, {}, 'run-other'));
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it('interpolates movers from the delta arrival time', () => {
    let now = 1000;
    const { store } = makeStore(() => now);
    store.apply(snapshot());
    store.apply(delta(1, [moveTo('m1', 20, 0)]));
    const m1 = store.movers.slotOf('m1') ?? -1;
    now += store.movers.segmentMs / 2;
    expect(store.movers.x(m1, store.movers.alpha(now))).toBeCloseTo(10);
  });
});

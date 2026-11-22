import { describe, expect, it } from 'vitest';
import { MAX_SEGMENT_MS, MIN_SEGMENT_MS, Tracks } from '../../aiautonomy/interfaces/state/tracks';

function positionOf(tracks: Tracks, id: string, now: number): [number, number] {
  const slot = tracks.slotOf(id);
  if (slot === undefined) throw new Error(`no slot for ${id}`);
  const alpha = tracks.alpha(now);
  return [tracks.x(slot, alpha), tracks.y(slot, alpha)];
}

// @req VIS-01
describe('mover interpolation between ticks (@req VIS-01)', () => {
  it('places entities at rest after a reset and skips malformed ones', () => {
    const tracks = new Tracks();
    tracks.reset([{ id: 'a', x: 1, y: 2 }, { id: 'b', x: Number.NaN, y: 0 }, null], 0);
    expect(tracks.count).toBe(1);
    expect(positionOf(tracks, 'a', 0)).toEqual([1, 2]);
    expect(positionOf(tracks, 'a', 10_000)).toEqual([1, 2]);
  });

  it('moves linearly from the previous to the current tick position', () => {
    const tracks = new Tracks();
    tracks.reset([{ id: 'a', x: 0, y: 0 }], 0);
    tracks.beginUpdate(1000);
    tracks.upsert('a', 10, -20);
    // First update after a reset: the longest segment.
    expect(tracks.segmentMs).toBe(MAX_SEGMENT_MS);
    expect(positionOf(tracks, 'a', 1000)).toEqual([0, 0]);
    expect(positionOf(tracks, 'a', 1000 + MAX_SEGMENT_MS / 2)).toEqual([5, -10]);
    expect(positionOf(tracks, 'a', 1000 + MAX_SEGMENT_MS)).toEqual([10, -20]);
    expect(positionOf(tracks, 'a', 5000)).toEqual([10, -20]);
  });

  it('times each segment by the gap since the previous update, clamped', () => {
    const tracks = new Tracks();
    tracks.reset([{ id: 'a', x: 0, y: 0 }], 0);
    tracks.beginUpdate(1000);
    tracks.beginUpdate(1200); // 1x: 5 ticks per second
    expect(tracks.segmentMs).toBe(200);
    tracks.beginUpdate(1205); // coalesced burst
    expect(tracks.segmentMs).toBe(MIN_SEGMENT_MS);
    tracks.beginUpdate(9000); // a step after a long pause
    expect(tracks.segmentMs).toBe(MAX_SEGMENT_MS);
  });

  it('starts a new segment from the on-screen position, so motion never jumps', () => {
    const tracks = new Tracks();
    tracks.reset([{ id: 'a', x: 0, y: 0 }], 0);
    tracks.beginUpdate(1000); // 250 ms segment (first after a reset)
    tracks.upsert('a', 10, 0);
    // The next tick arrives 80% of the way through: x = 8 is the new starting point.
    tracks.beginUpdate(1200);
    expect(positionOf(tracks, 'a', 1200)).toEqual([8, 0]);
    tracks.upsert('a', 20, 0);
    // Halfway through the 200 ms segment: x = 8 + (20 - 8) / 2.
    expect(positionOf(tracks, 'a', 1300)).toEqual([14, 0]);
    tracks.beginUpdate(1300);
    tracks.upsert('a', 30, 0);
    expect(positionOf(tracks, 'a', 1300)).toEqual([14, 0]);
    expect(positionOf(tracks, 'a', 1300 + tracks.segmentMs)).toEqual([30, 0]);
  });

  it('adds new entities at rest at their first position', () => {
    const tracks = new Tracks();
    tracks.reset([], 0);
    tracks.beginUpdate(100);
    tracks.upsert('n', 50, 60);
    expect(positionOf(tracks, 'n', 100)).toEqual([50, 60]);
  });

  it('swap-removes slots and keeps id lookups consistent', () => {
    const tracks = new Tracks();
    tracks.reset(
      [
        { id: 'a', x: 1, y: 1 },
        { id: 'b', x: 2, y: 2 },
        { id: 'c', x: 3, y: 3 },
      ],
      0,
    );
    expect(tracks.remove('a')).toBe(true);
    expect(tracks.remove('a')).toBe(false);
    expect(tracks.count).toBe(2);
    expect(tracks.slotOf('c')).toBe(0);
    expect(tracks.ids).toEqual(['c', 'b']);
    expect(positionOf(tracks, 'c', 0)).toEqual([3, 3]);
    expect(positionOf(tracks, 'b', 0)).toEqual([2, 2]);
  });

  it('grows past its initial capacity', () => {
    const tracks = new Tracks(2);
    tracks.reset(
      Array.from({ length: 100 }, (_, i) => ({ id: `m${i}`, x: i, y: -i })),
      0,
    );
    expect(tracks.count).toBe(100);
    expect(positionOf(tracks, 'm99', 0)).toEqual([99, -99]);
  });

  it('finds the nearest entity within a pick radius', () => {
    const tracks = new Tracks();
    tracks.reset(
      [
        { id: 'a', x: 0, y: 0 },
        { id: 'b', x: 10, y: 0 },
      ],
      0,
    );
    expect(tracks.nearest(8, 1, 5, 1)).toBe('b');
    expect(tracks.nearest(1, 0, 5, 1)).toBe('a');
    expect(tracks.nearest(5, 30, 5, 1)).toBeNull();
  });
});

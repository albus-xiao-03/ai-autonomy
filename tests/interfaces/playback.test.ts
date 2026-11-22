import { describe, expect, it } from 'vitest';
import type { RunState } from '../../aiautonomy/interfaces/net/protocol';
import {
  formatClock,
  formatStamp,
  formatValue,
  showDirty,
} from '../../aiautonomy/interfaces/ui/format';
import { playbackControls } from '../../aiautonomy/interfaces/ui/panels/playback';
import { PANELS, panelNumber } from '../../aiautonomy/interfaces/ui/panels/registry';
import { status } from './fixtures';

type Row = [RunState, string];

// Enabled controls per state, in the order start, pause, resume, step, speed, reset, cancel.
const TABLE: Row[] = [
  ['idle', 'start step speed reset'],
  ['running', 'pause speed reset cancel'],
  ['paused', 'resume step speed reset cancel'],
  ['completed', 'reset'],
  ['interrupted', 'reset'],
  ['removed', 'reset'],
];

function enabled(state: RunState, connected = true): string {
  const controls = playbackControls(status({ state }), connected);
  return Object.entries(controls)
    .filter(([, on]) => on)
    .map(([name]) => name)
    .join(' ');
}

// @req VIS-04
describe('playback panel (@req VIS-04)', () => {
  it.each(TABLE)('enables the right controls when the run is %s', (state, expected) => {
    expect(enabled(state)).toBe(expected);
  });

  it('disables every control while disconnected or before the first status', () => {
    expect(enabled('running', false)).toBe('');
    expect(Object.values(playbackControls(null, true)).some(Boolean)).toBe(false);
  });

  it('is registered as numbered panel 03', () => {
    const playback = PANELS.find((panel) => panel.key === 'playback');
    expect(playback && panelNumber(playback)).toBe('03');
  });
});

describe('panel text formatting', () => {
  it('formats the simulated clock as Day d · HH:MM', () => {
    expect(formatClock(1, 420)).toBe('Day 1 · 07:00');
    expect(formatClock(3, 1439)).toBe('Day 3 · 23:59');
    expect(formatClock(2, 0)).toBe('Day 2 · 00:00');
  });

  it('formats the engine stamp and inspected values as plain text', () => {
    expect(formatStamp(null)).toBe('engine —');
    expect(
      formatStamp({ ok: true, engine_version: '0.1.0', git_sha: 'abcdef123456', dirty: true }),
    ).toBe('engine 0.1.0 · abcdef1');
    const stamped = {
      ok: true,
      engine_version: '0.1.0+gabcdef1.dirty',
      git_sha: 'abcdef1',
      dirty: true,
    };
    expect(formatStamp(stamped)).toBe('engine 0.1.0+gabcdef1.dirty');
    expect(showDirty(stamped)).toBe(false);
    expect(showDirty({ ...stamped, engine_version: '0.1.0' })).toBe(true);
    expect(formatValue(1.23456)).toBe('1.23');
    expect(formatValue('<b>x</b>')).toBe('<b>x</b>');
    expect(formatValue({ a: [1, 2] })).toBe('{"a":[1,2]}');
    expect(formatValue(null)).toBe('—');
  });
});

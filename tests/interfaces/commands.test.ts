import { describe, expect, it } from 'vitest';
import { CommandSender } from '../../aiautonomy/interfaces/net/commands';
import type { AckMessage } from '../../aiautonomy/interfaces/net/protocol';
import { buildTelemetry } from '../../aiautonomy/interfaces/net/telemetry';
import { SampleWindow } from '../../aiautonomy/interfaces/state/samples';

function setup(connected = true) {
  let now = 0;
  const sent: Record<string, unknown>[] = [];
  const sender = new CommandSender({
    transport: (text) => {
      if (connected) sent.push(JSON.parse(text) as Record<string, unknown>);
      return connected;
    },
    now: () => now,
    idPrefix: 't',
  });
  return {
    sender,
    sent,
    advance: (ms: number) => {
      now += ms;
    },
  };
}

function ack(cmdId: string, ok = true): AckMessage {
  return { type: 'ack', cmd_id: cmdId, ok, error: ok ? null : 'not allowed', result: null };
}

// @req VIS-04 @req ARCH-03
describe('command sender and ack latency (@req VIS-04, @req ARCH-03)', () => {
  it('attaches a unique client cmd_id to every command', () => {
    const { sender, sent } = setup();
    void sender.send({ type: 'pause' });
    void sender.send({ type: 'set_speed', speed: '4x' });
    expect(sent).toEqual([
      { type: 'pause', cmd_id: 't-1' },
      { type: 'set_speed', speed: '4x', cmd_id: 't-2' },
    ]);
    expect(sender.pendingCount).toBe(2);
  });

  it('resolves with the ack and records the round-trip latency', async () => {
    const { sender, advance } = setup();
    const pending = sender.send({ type: 'step' });
    advance(42);
    const record = sender.handleAck(ack('t-1'));
    expect(record).toEqual({ cmd_id: 't-1', type: 'step', ok: true, error: null, latency_ms: 42 });
    await expect(pending).resolves.toMatchObject({ cmd_id: 't-1', ok: true });
    expect(sender.latency.count).toBe(1);
    expect(sender.history.at(-1)?.latency_ms).toBe(42);
    expect(sender.pendingCount).toBe(0);
  });

  it('passes rejections through and ignores acks for unknown commands', async () => {
    const { sender } = setup();
    const pending = sender.send({ type: 'start' });
    expect(sender.handleAck(ack('nope'))).toBeNull();
    sender.handleAck(ack('t-1', false));
    await expect(pending).resolves.toMatchObject({ ok: false, error: 'not allowed' });
    expect(sender.handleAck(ack('t-1'))).toBeNull(); // exactly one ack per command
  });

  it('fails at once when the socket is not open', async () => {
    const { sender } = setup(false);
    await expect(sender.send({ type: 'start' })).resolves.toMatchObject({
      ok: false,
      error: 'not connected',
    });
    expect(sender.pendingCount).toBe(0);
  });

  it('fails pending commands when the connection drops', async () => {
    const { sender } = setup();
    const pending = sender.send({ type: 'reset' });
    sender.failPending('connection lost');
    await expect(pending).resolves.toMatchObject({ ok: false, error: 'connection lost' });
    expect(sender.latency.count).toBe(0);
  });

  it('reports p50 and p95 ack latency in the telemetry command', () => {
    const { sender, advance } = setup();
    for (let i = 1; i <= 20; i++) {
      void sender.send({ type: 'sync' });
      advance(i);
      sender.handleAck(ack(`t-${i}`));
    }
    const frames = new SampleWindow(10);
    for (const ms of [16, 16, 17, 33]) frames.push(ms);
    expect(buildTelemetry(59.999, frames, sender.latency)).toEqual({
      type: 'telemetry',
      fps: 60,
      frame_ms_p95: 33,
      cmd_latency_ms_p50: 10,
      cmd_latency_ms_p95: 19,
      samples: 20,
    });
    // JSON has no NaN: empty windows report zero.
    expect(buildTelemetry(0, new SampleWindow(4), new SampleWindow(4))).toMatchObject({
      frame_ms_p95: 0,
      cmd_latency_ms_p50: 0,
      samples: 0,
    });
  });
});

describe('SampleWindow percentiles', () => {
  it('uses nearest rank over the most recent samples', () => {
    const window = new SampleWindow(4);
    expect(window.percentile(50)).toBeNaN();
    for (const value of [5, 1, 4, 2, 3]) window.push(value); // 5 falls out
    expect(window.count).toBe(4);
    expect(window.percentile(50)).toBe(2);
    expect(window.percentile(95)).toBe(4);
    expect(window.percentile(100)).toBe(4);
    window.clear();
    expect(window.count).toBe(0);
  });
});

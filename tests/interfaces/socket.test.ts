import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { backoffDelay, DEFAULT_BACKOFF } from '../../aiautonomy/interfaces/net/backoff';
import { parseServerMessage, type ServerMessage } from '../../aiautonomy/interfaces/net/protocol';
import { EngineSocket, type ConnectionState } from '../../aiautonomy/interfaces/net/socket';
import { FakeSocket, runStatus } from './fixtures';

function connect() {
  const messages: ServerMessage[] = [];
  const states: ConnectionState[] = [];
  const socket = new EngineSocket({
    url: 'ws://engine/ws',
    createSocket: (url) => new FakeSocket(url),
    onMessage: (message) => messages.push(message),
    onStateChange: (state) => states.push(state),
    random: () => 0.5, // no jitter
  });
  socket.start();
  return { socket, messages, states };
}

// @req ARCH-03
describe('engine WebSocket client (@req ARCH-03)', () => {
  beforeEach(() => {
    FakeSocket.instances = [];
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('connects, parses frames and sends only while open', () => {
    const { socket, messages, states } = connect();
    expect(states).toEqual(['connecting']);
    expect(socket.send('{}')).toBe(false);
    const fake = FakeSocket.latest();
    expect(fake.url).toBe('ws://engine/ws');
    fake.open();
    expect(states).toEqual(['connecting', 'open']);
    fake.receive(runStatus(0));
    fake.onmessage?.({ data: 'not json' } as MessageEvent);
    expect(messages).toEqual([runStatus(0)]);
    expect(socket.send('{"type":"start"}')).toBe(true);
    expect(fake.sent).toEqual(['{"type":"start"}']);
  });

  it('reconnects with exponential backoff and resets it after a successful open', () => {
    const { states } = connect();
    FakeSocket.latest().drop(); // never opened
    expect(states.at(-1)).toBe('reconnecting');
    vi.advanceTimersByTime(DEFAULT_BACKOFF.baseMs - 1);
    expect(FakeSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(FakeSocket.instances).toHaveLength(2);
    FakeSocket.latest().drop();
    vi.advanceTimersByTime(DEFAULT_BACKOFF.baseMs * 2);
    expect(FakeSocket.instances).toHaveLength(3);
    FakeSocket.latest().open();
    expect(states.at(-1)).toBe('open');
    FakeSocket.latest().drop();
    vi.advanceTimersByTime(DEFAULT_BACKOFF.baseMs);
    expect(FakeSocket.instances).toHaveLength(4);
  });

  it('stops reconnecting after stop()', () => {
    const { socket, states } = connect();
    FakeSocket.latest().open();
    socket.stop();
    expect(states.at(-1)).toBe('closed');
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(1);
  });
});

describe('reconnect backoff', () => {
  it('grows exponentially, is capped and jittered', () => {
    const exact = { ...DEFAULT_BACKOFF, jitter: 0 };
    expect([0, 1, 2, 3, 10].map((n) => backoffDelay(n, exact))).toEqual([
      250, 500, 1000, 2000, 5000,
    ]);
    expect(backoffDelay(1, DEFAULT_BACKOFF, () => 0)).toBe(400);
    expect(backoffDelay(1, DEFAULT_BACKOFF, () => 1)).toBe(600);
    expect(backoffDelay(10, DEFAULT_BACKOFF, () => 1)).toBe(DEFAULT_BACKOFF.maxMs);
  });
});

describe('server frame parsing (@req ARCH-03)', () => {
  it('accepts known message types and rejects malformed frames', () => {
    expect(parseServerMessage(JSON.stringify(runStatus(1)))).toEqual(runStatus(1));
    const ack = { type: 'ack', cmd_id: 'c-1', ok: true, error: null, result: null };
    expect(parseServerMessage(JSON.stringify(ack))).toEqual(ack);
    expect(parseServerMessage('{"type":"ack","ok":true}')).toBeNull();
    expect(
      parseServerMessage('{"type":"bogus","run_id":"r","state_version":0,"tick":0}'),
    ).toBeNull();
    expect(
      parseServerMessage('{"type":"delta","run_id":"r","state_version":1.5,"tick":0}'),
    ).toBeNull();
    expect(parseServerMessage('[]')).toBeNull();
    expect(parseServerMessage('{')).toBeNull();
  });
});

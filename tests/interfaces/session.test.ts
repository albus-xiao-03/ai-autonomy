import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Session } from '../../aiautonomy/interfaces/net/session';
import { delta, FakeSocket, moveTo, snapshot } from './fixtures';

function openSession() {
  const session = new Session({
    url: 'ws://engine/ws',
    createSocket: (url) => new FakeSocket(url),
  });
  session.start();
  const socket = FakeSocket.latest();
  socket.open();
  return { session, socket };
}

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

// @req ARCH-03 @req VIS-04
describe('session wiring (@req ARCH-03, @req VIS-04)', () => {
  beforeEach(() => {
    FakeSocket.instances = [];
    vi.stubGlobal('fetch', () => Promise.reject(new Error('offline')));
  });

  it('routes run messages to the store and sends sync when it detects a gap', () => {
    const { session, socket } = openSession();
    socket.receive(snapshot({ state_version: 1 }));
    socket.receive(delta(2, [moveTo('m1', 1, 1)]));
    socket.receive(delta(4, [moveTo('m1', 2, 2)]));
    expect(session.store.stateVersion).toBe(2);
    expect(socket.commands()).toEqual([{ type: 'sync', cmd_id: expect.any(String) as string }]);
  });

  it('matches acks to commands and surfaces rejected controls', async () => {
    const { session, socket } = openSession();
    const pending = session.send({ type: 'start' });
    const [command] = socket.commands();
    socket.receive({
      type: 'ack',
      cmd_id: command?.cmd_id,
      ok: false,
      error: 'already running',
      result: null,
    });
    await expect(pending).resolves.toMatchObject({ ok: false });
    expect(session.lastError).toBe('start: already running');
    expect(session.commands.history.at(-1)?.type).toBe('start');
  });

  it('fills the selection from the inspect ack and clears it on a new run', async () => {
    const { session, socket } = openSession();
    socket.receive(snapshot());
    session.inspect('m1');
    expect(session.selection.state).toMatchObject({ id: 'm1', status: 'loading' });
    const inspect = socket.commands().at(-1);
    expect(inspect).toMatchObject({ type: 'inspect', entity_id: 'm1' });
    socket.receive({
      type: 'ack',
      cmd_id: inspect?.cmd_id,
      ok: true,
      error: null,
      result: { id: 'm1', x: 0, y: 0, kind: 'walker' },
    });
    await flush();
    expect(session.selection.state).toMatchObject({ status: 'ok', result: { kind: 'walker' } });
    socket.receive(snapshot({ run_id: 'run-b', run_epoch: 2 }));
    expect(session.selection.id).toBeNull();
  });

  it('fails pending commands and reports reconnecting when the socket drops', async () => {
    const { session, socket } = openSession();
    const pending = session.send({ type: 'pause' });
    socket.drop();
    await expect(pending).resolves.toMatchObject({ ok: false, error: 'connection lost' });
    expect(session.connection).toBe('reconnecting');
    session.stop();
    expect(session.connection).toBe('closed');
  });
});

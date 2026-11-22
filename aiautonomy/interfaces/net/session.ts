// One browser session with the engine: the socket, the command sender, the client store,
// the selection, the connection state and the engine version stamp.
// REQ: ARCH-03, VIS-04
import { Observable } from '../state/observable';
import { Selection } from '../state/selection';
import { ClientStore } from '../state/store';
import { CommandSender } from './commands';
import { fetchHealth } from './health';
import type { AckMessage, CommandBody, HealthResponse, ServerMessage } from './protocol';
import { EngineSocket, type ConnectionState, type SocketLike } from './socket';

export interface SessionOptions {
  readonly url: string;
  readonly createSocket?: (url: string) => SocketLike;
  readonly now?: () => number;
}

export class Session extends Observable {
  connection: ConnectionState = 'connecting';
  health: HealthResponse | null = null;
  /** The most recent rejected control command, shown in the playback panel. */
  lastError: string | null = null;
  readonly store: ClientStore;
  readonly commands: CommandSender;
  readonly selection = new Selection();
  readonly #socket: EngineSocket;
  #runId: string | null = null;

  constructor(options: SessionOptions) {
    super();
    const now = options.now ?? (() => performance.now());
    this.#socket = new EngineSocket({
      url: options.url,
      createSocket: options.createSocket,
      onMessage: (message) => {
        this.#onMessage(message);
      },
      onStateChange: (state) => {
        this.#onConnection(state);
      },
    });
    this.commands = new CommandSender({ transport: (text) => this.#socket.send(text), now });
    this.store = new ClientStore({
      now,
      requestSync: () => {
        void this.commands.send({ type: 'sync' });
      },
    });
    this.store.subscribe(() => {
      // A new run (reset, configure) invalidates the selection.
      if (this.store.runId !== this.#runId) {
        this.#runId = this.store.runId;
        this.selection.clear();
      }
    });
  }

  start(): void {
    this.#socket.start();
  }

  stop(): void {
    this.#socket.stop();
  }

  /** Send a control command and surface a rejection in `lastError`. */
  async send(body: CommandBody): Promise<AckMessage> {
    const ack = await this.commands.send(body);
    if (body.type !== 'telemetry' && body.type !== 'inspect' && body.type !== 'sync') {
      const error = ack.ok ? null : `${body.type}: ${ack.error ?? 'rejected'}`;
      if (error !== this.lastError) {
        this.lastError = error;
        this.notify();
      }
    }
    return ack;
  }

  /** Select an entity and fill the inspector from an `inspect` command; null clears. */
  inspect(entityId: string | null): void {
    if (entityId === null) {
      this.selection.clear();
      return;
    }
    const token = this.selection.begin(entityId, this.store.tick);
    void this.commands.send({ type: 'inspect', entity_id: entityId }).then((ack) => {
      this.selection.resolve(token, ack);
    });
  }

  #onMessage(message: ServerMessage): void {
    if (message.type === 'ack') this.commands.handleAck(message);
    else this.store.apply(message);
  }

  #onConnection(state: ConnectionState): void {
    const wasOpen = this.connection === 'open';
    this.connection = state;
    if (wasOpen && state !== 'open') this.commands.failPending('connection lost');
    if (state === 'open') {
      this.lastError = null;
      void fetchHealth().then((health) => {
        this.health = health;
        this.notify();
      });
    }
    this.notify();
  }
}

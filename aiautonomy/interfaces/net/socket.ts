// The single engine WebSocket (`/ws`): connect, parse frames, reconnect with backoff.
// REQ: ARCH-03
import { backoffDelay, DEFAULT_BACKOFF, type BackoffOptions } from './backoff';
import { parseServerMessage, type ServerMessage } from './protocol';

export type ConnectionState = 'connecting' | 'open' | 'reconnecting' | 'closed';

/** The part of the browser WebSocket API the client uses; tests supply a fake. */
export interface SocketLike {
  readonly readyState: number;
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  send(data: string): void;
  close(): void;
}

export interface EngineSocketOptions {
  readonly url: string;
  readonly onMessage: (message: ServerMessage) => void;
  readonly onStateChange: (state: ConnectionState) => void;
  readonly createSocket?: (url: string) => SocketLike;
  readonly backoff?: BackoffOptions;
  readonly random?: () => number;
}

const OPEN = 1;

export class EngineSocket {
  readonly #options: EngineSocketOptions;
  #state: ConnectionState = 'closed';
  #socket: SocketLike | null = null;
  #attempt = 0;
  #timer: ReturnType<typeof setTimeout> | undefined;
  #stopped = true;

  constructor(options: EngineSocketOptions) {
    this.#options = options;
  }

  get state(): ConnectionState {
    return this.#state;
  }

  /** Failed connection attempts since the last successful open. */
  get attempt(): number {
    return this.#attempt;
  }

  start(): void {
    if (!this.#stopped) return;
    this.#stopped = false;
    this.#connect();
  }

  stop(): void {
    this.#stopped = true;
    clearTimeout(this.#timer);
    this.#timer = undefined;
    const socket = this.#socket;
    this.#socket = null;
    if (socket !== null) {
      socket.onclose = null;
      socket.close();
    }
    this.#setState('closed');
  }

  /** Send one text frame; false when the socket is not open. */
  send(text: string): boolean {
    const socket = this.#socket;
    if (socket?.readyState !== OPEN) return false;
    socket.send(text);
    return true;
  }

  #connect(): void {
    this.#timer = undefined;
    this.#setState(this.#attempt === 0 ? 'connecting' : 'reconnecting');
    let socket: SocketLike;
    try {
      socket = (this.#options.createSocket ?? defaultSocket)(this.#options.url);
    } catch {
      this.#scheduleReconnect();
      return;
    }
    this.#socket = socket;
    socket.onopen = () => {
      this.#attempt = 0;
      this.#setState('open');
    };
    socket.onmessage = (event) => {
      const data: unknown = event.data;
      if (typeof data !== 'string') return;
      const message = parseServerMessage(data);
      if (message !== null) this.#options.onMessage(message);
    };
    socket.onerror = () => {
      // A close event always follows; reconnecting is handled there.
    };
    socket.onclose = () => {
      if (this.#socket !== socket) return;
      this.#socket = null;
      if (this.#stopped) this.#setState('closed');
      else this.#scheduleReconnect();
    };
  }

  #scheduleReconnect(): void {
    this.#setState('reconnecting');
    const delay = backoffDelay(
      this.#attempt,
      this.#options.backoff ?? DEFAULT_BACKOFF,
      this.#options.random,
    );
    this.#attempt += 1;
    this.#timer = setTimeout(() => {
      this.#connect();
    }, delay);
  }

  #setState(state: ConnectionState): void {
    if (state === this.#state) return;
    this.#state = state;
    this.#options.onStateChange(state);
  }
}

function defaultSocket(url: string): SocketLike {
  return new WebSocket(url);
}

// VIS-04 panel 3: start, pause/resume, step, speed, reset, cancel and the connection state.
// REQ: VIS-04
import { useEffect, useRef, useState } from 'preact/hooks';
import type { CommandBody } from '../../net/protocol';
import { SPEED_LABEL, SPEEDS } from '../format';
import { useObservable } from '../hooks';
import { playbackControls } from './playback';
import type { PanelProps } from './registry';

export function PlaybackPanel({ session }: PanelProps) {
  const { store } = session;
  const status = useObservable(store, () => store.status);
  const connection = useObservable(session, () => session.connection);
  const lastError = useObservable(session, () => session.lastError);
  const [confirming, setConfirming] = useState(false);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const keepRef = useRef<HTMLButtonElement>(null);
  const wasConfirming = useRef(false);
  const controls = playbackControls(status, connection === 'open');

  useEffect(() => {
    if (confirming) keepRef.current?.focus();
    else if (wasConfirming.current) cancelRef.current?.focus();
    wasConfirming.current = confirming;
  }, [confirming]);

  useEffect(() => {
    if (!controls.cancel) setConfirming(false);
  }, [controls.cancel]);

  const send = (body: CommandBody): void => {
    void session.send(body);
  };
  const toggle = controls.resume ? 'resume' : 'pause';
  const speed = status?.speed ?? null;

  return (
    <>
      <div class="control-row">
        <button
          type="button"
          class="btn btn-primary"
          data-testid="btn-start"
          disabled={!controls.start}
          onClick={() => send({ type: 'start' })}
        >
          start
        </button>
        <button
          type="button"
          class="btn"
          data-testid="btn-pause"
          disabled={!controls.pause && !controls.resume}
          onClick={() => send({ type: toggle })}
        >
          {toggle}
        </button>
        <button
          type="button"
          class="btn"
          data-testid="btn-step"
          disabled={!controls.step}
          onClick={() => send({ type: 'step' })}
        >
          step
        </button>
      </div>

      <p class="field-label" id="playback-speed-label">
        speed
      </p>
      <div class="control-row" role="group" aria-labelledby="playback-speed-label">
        {SPEEDS.map((value) => (
          <button
            key={value}
            type="button"
            class="btn"
            data-testid={`speed-${value}`}
            aria-pressed={speed === value}
            disabled={!controls.speed}
            onClick={() => send({ type: 'set_speed', speed: value })}
          >
            {SPEED_LABEL[value]}
          </button>
        ))}
      </div>

      <div class="control-row control-row-split">
        <button
          type="button"
          class="btn"
          data-testid="btn-reset"
          disabled={!controls.reset}
          onClick={() => {
            setConfirming(false);
            send({ type: 'reset' });
          }}
        >
          reset
        </button>
        {confirming ? null : (
          <button
            ref={cancelRef}
            type="button"
            class="btn btn-danger"
            data-testid="btn-cancel"
            disabled={!controls.cancel}
            onClick={() => setConfirming(true)}
          >
            cancel run
          </button>
        )}
      </div>

      {confirming ? (
        <div
          class="confirm"
          role="group"
          aria-labelledby="cancel-confirm-text"
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault();
              setConfirming(false);
            }
          }}
        >
          <p class="confirm-text" id="cancel-confirm-text">
            End this run as interrupted? This cannot be undone.
          </p>
          <div class="control-row">
            <button
              type="button"
              class="btn btn-danger"
              data-testid="btn-cancel-confirm"
              onClick={() => {
                setConfirming(false);
                send({ type: 'cancel' });
              }}
            >
              end run
            </button>
            <button
              ref={keepRef}
              type="button"
              class="btn"
              data-testid="btn-cancel-keep"
              onClick={() => setConfirming(false)}
            >
              keep
            </button>
          </div>
        </div>
      ) : null}

      <p class="status-line" data-testid="connection" data-connection={connection}>
        <span class="dot" aria-hidden="true" />
        connection: {connection}
      </p>
      <p class="error-line" role="status" data-testid="playback-error">
        {lastError ?? ''}
      </p>
    </>
  );
}

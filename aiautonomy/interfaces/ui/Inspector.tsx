// Small inspector box for the selected entity, filled from the `inspect` command's ack.
// REQ: VIS-01
import { Fragment } from 'preact';
import type { Session } from '../net/session';
import { formatValue } from './format';
import { useObservable } from './hooks';

export function Inspector({ session }: { session: Session }) {
  const selection = useObservable(session.selection, () => session.selection.state);
  if (selection.id === null) return null;
  return (
    <section class="panel inspector" aria-labelledby="inspector-label" data-testid="inspector">
      <div class="inspector-head">
        <h2 class="panel-label" id="inspector-label">
          selection
        </h2>
        <button
          type="button"
          class="btn btn-icon btn-ghost"
          aria-label="Clear selection (Escape)"
          title="Clear selection (Esc)"
          onClick={() => session.inspect(null)}
        >
          ×
        </button>
      </div>
      <p class="inspector-id" data-testid="inspector-id">
        {selection.id}
      </p>
      {selection.status === 'loading' ? <p class="muted">inspecting…</p> : null}
      {selection.status === 'error' ? <p class="error-line">{selection.error}</p> : null}
      {selection.status === 'ok' && selection.result !== null ? (
        <dl class="fields">
          {Object.entries(selection.result).map(([key, value]) => (
            <Fragment key={key}>
              <dt>{key}</dt>
              <dd>{formatValue(value)}</dd>
            </Fragment>
          ))}
        </dl>
      ) : null}
      {selection.tick === null ? null : (
        <p class="inspector-foot">inspected at tick {selection.tick}</p>
      )}
    </section>
  );
}

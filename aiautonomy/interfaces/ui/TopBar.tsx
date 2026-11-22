// Run status, tick and simulated clock, inference-wait indicator and engine version stamp.
// REQ: VIS-04, ARCH-01
import type { Session } from '../net/session';
import { formatClock, formatStamp, shortId, showDirty } from './format';
import { useObservable } from './hooks';

export function TopBar({ session }: { session: Session }) {
  const { store } = session;
  const status = useObservable(store, () => store.status);
  const tick = useObservable(store, () => store.tick);
  const clock = useObservable(store, () => store.world?.clock ?? null);
  const runId = useObservable(store, () => store.runId);
  const health = useObservable(session, () => session.health);
  const state = status?.state ?? null;
  const waiting = status?.waiting_for_inference ?? false;

  return (
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true" />
        AI Autonomy
      </div>
      <span class="topbar-divider" aria-hidden="true" />
      <span class="tag" data-testid="run-state" data-state={state ?? 'unknown'}>
        status: {state ?? '—'}
      </span>
      <span class="readout" data-testid="tick" data-tick={tick}>
        <span class="readout-label">tick </span>
        <strong>{tick}</strong>
      </span>
      <span class="readout" data-testid="clock">
        {clock === null ? 'Day — · --:--' : formatClock(clock.day, clock.minute_of_day)}
      </span>
      <span class="waiting-slot" role="status">
        {waiting ? (
          <span class="tag tag-waiting" data-testid="waiting">
            waiting for inference
          </span>
        ) : null}
      </span>
      <span class="topbar-spacer" />
      <span
        class="readout run-id"
        data-testid="run-id"
        data-run-id={runId ?? ''}
        title={runId ?? ''}
      >
        <span class="readout-label">run </span>
        {shortId(runId)}
      </span>
      <span class="stamp" data-testid="engine-stamp">
        {formatStamp(health)}
        {showDirty(health) ? <span class="stamp-dirty"> · dirty</span> : null}
      </span>
    </header>
  );
}

// Which playback controls are enabled for the current run state (VIS-04 panel 3).
// REQ: VIS-04
import type { RunStatus } from '../../net/protocol';

export interface PlaybackControls {
  readonly start: boolean;
  readonly pause: boolean;
  readonly resume: boolean;
  readonly step: boolean;
  readonly speed: boolean;
  readonly reset: boolean;
  readonly cancel: boolean;
}

export function playbackControls(status: RunStatus | null, connected: boolean): PlaybackControls {
  const state = connected ? (status?.state ?? null) : null;
  const live = state === 'running' || state === 'paused';
  return {
    start: state === 'idle',
    pause: state === 'running',
    resume: state === 'paused',
    step: state === 'idle' || state === 'paused',
    speed: state === 'idle' || live,
    reset: state !== null,
    cancel: live,
  };
}

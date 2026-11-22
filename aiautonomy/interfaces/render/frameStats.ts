// Frame timing for the FPS meter and the telemetry report.
// REQ: VIS-01
import { SampleWindow } from '../state/samples';

/** Frames longer than this (background tab, debugger pause) are not timing samples. */
export const MAX_FRAME_MS = 1000;

export class FrameStats {
  /** Recent frame times in ms (about ten seconds at 60 Hz). */
  readonly frameTimes = new SampleWindow(600);
  /** Frames rendered since the loop started. */
  frames = 0;
  #last = -1;

  /** Record a frame at `now` (ms). Allocation-free. */
  record(now: number): void {
    if (this.#last >= 0) {
      const dt = now - this.#last;
      if (dt > 0 && dt < MAX_FRAME_MS) this.frameTimes.push(dt);
    }
    this.#last = now;
    this.frames += 1;
  }
}

/** Events per second for `count` events over `ms` milliseconds. */
export function ratePerSecond(count: number, ms: number): number {
  return ms > 0 ? (count * 1000) / ms : 0;
}

// FPS and command-latency telemetry, sent to the engine every 5 s for benchmark reports
// (plans/R1.md §5.12 "Performance").
// REQ: ARCH-03
import type { SampleWindow } from '../state/samples';
import type { TelemetryCommand } from './protocol';

export const TELEMETRY_INTERVAL_MS = 5000;

export type TelemetryBody = Omit<TelemetryCommand, 'cmd_id'>;

export interface FrameSource {
  /** Frames rendered since page load. */
  readonly frames: number;
  /** Recent frame times in ms. */
  readonly frameTimes: SampleWindow;
}

/** One telemetry report. `samples` is the number of ack latencies behind the percentiles. */
export function buildTelemetry(
  fps: number,
  frameTimes: SampleWindow,
  latency: SampleWindow,
): TelemetryBody {
  return {
    type: 'telemetry',
    fps: round2(fps),
    frame_ms_p95: round2(frameTimes.percentile(95)),
    cmd_latency_ms_p50: round2(latency.percentile(50)),
    cmd_latency_ms_p95: round2(latency.percentile(95)),
    samples: latency.count,
  };
}

export interface TelemetryOptions {
  readonly frames: FrameSource;
  readonly latency: SampleWindow;
  readonly isOpen: () => boolean;
  readonly send: (body: TelemetryBody) => void;
  readonly now?: () => number;
  readonly intervalMs?: number;
}

/** Start the periodic report; returns a function that stops it. */
export function startTelemetry(options: TelemetryOptions): () => void {
  const now = options.now ?? (() => performance.now());
  let lastFrames = options.frames.frames;
  let lastAt = now();
  const timer = setInterval(() => {
    const at = now();
    const frames = options.frames.frames;
    const fps = at > lastAt ? ((frames - lastFrames) * 1000) / (at - lastAt) : 0;
    lastFrames = frames;
    lastAt = at;
    if (options.isOpen()) {
      options.send(buildTelemetry(fps, options.frames.frameTimes, options.latency));
    }
  }, options.intervalMs ?? TELEMETRY_INTERVAL_MS);
  return () => {
    clearInterval(timer);
  };
}

/** JSON has no NaN: empty windows report 0. */
function round2(value: number): number {
  return Number.isFinite(value) ? Math.round(value * 100) / 100 : 0;
}

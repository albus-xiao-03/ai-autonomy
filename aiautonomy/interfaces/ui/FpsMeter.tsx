// FPS meter with the 95th-percentile frame time (docs/engine-plan.md §7, M0 work item 6).
// REQ: VIS-01
import { useEffect, useState } from 'preact/hooks';
import { ratePerSecond, type FrameStats } from '../render/frameStats';
import { formatMs } from './format';

const REFRESH_MS = 500;

export function FpsMeter({ stats }: { stats: FrameStats }) {
  const [reading, setReading] = useState({ fps: 0, p95: Number.NaN });
  useEffect(() => {
    let frames = stats.frames;
    let at = performance.now();
    const timer = setInterval(() => {
      const now = performance.now();
      setReading({
        fps: ratePerSecond(stats.frames - frames, now - at),
        p95: stats.frameTimes.percentile(95),
      });
      frames = stats.frames;
      at = now;
    }, REFRESH_MS);
    return () => {
      clearInterval(timer);
    };
  }, [stats]);
  const fps = reading.fps.toFixed(0);
  return (
    <p class="meter" data-testid="fps" data-fps={fps}>
      <span class="readout-label">fps </span>
      <strong>{fps}</strong>
      <span class="readout-label"> · p95 </span>
      <strong>{formatMs(reading.p95)}</strong>
      <span class="readout-label"> ms</span>
    </p>
  );
}

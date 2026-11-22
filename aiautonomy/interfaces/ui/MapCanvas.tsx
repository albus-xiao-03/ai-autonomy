// Full-viewport WebGL canvas for the map.
// REQ: VIS-01
import { useEffect, useRef } from 'preact/hooks';
import type { Viewport } from '../render/viewport';
import { useObservable } from './hooks';

export function MapCanvas({ viewport }: { viewport: Viewport }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const webgl = useObservable(viewport, () => viewport.webgl);
  useEffect(() => {
    const canvas = canvasRef.current;
    return canvas === null ? undefined : viewport.attach(canvas);
  }, [viewport]);
  return (
    <div class="map">
      <canvas
        ref={canvasRef}
        data-testid="map"
        data-webgl={webgl}
        tabIndex={0}
        role="application"
        aria-label="Map. Drag or use the arrow keys to pan, scroll, pinch or press + and - to zoom, Home or 0 to reset the view, click a mover to inspect it."
      />
      {webgl === 'unavailable' ? (
        <p class="map-fallback">WebGL is unavailable, so the map cannot be drawn.</p>
      ) : null}
    </div>
  );
}

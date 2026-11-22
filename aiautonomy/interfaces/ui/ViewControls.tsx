// Camera buttons: zoom and reset view (also on the Home and 0 keys).
// REQ: VIS-01
import { KEY_ZOOM_FACTOR } from '../render/input';
import type { Viewport } from '../render/viewport';

export function ViewControls({ viewport }: { viewport: Viewport }) {
  return (
    <div class="view-controls" role="group" aria-label="Camera">
      <button
        type="button"
        class="btn btn-icon"
        aria-label="Zoom in (+)"
        title="Zoom in (+)"
        onClick={() => viewport.zoomBy(1 / KEY_ZOOM_FACTOR)}
      >
        +
      </button>
      <button
        type="button"
        class="btn btn-icon"
        aria-label="Zoom out (-)"
        title="Zoom out (-)"
        onClick={() => viewport.zoomBy(KEY_ZOOM_FACTOR)}
      >
        −
      </button>
      <button
        type="button"
        class="btn"
        data-testid="btn-reset-view"
        title="Reset view (Home or 0)"
        onClick={() => viewport.resetView()}
      >
        reset view
      </button>
    </div>
  );
}

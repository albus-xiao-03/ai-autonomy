// Pointer, wheel, pinch and keyboard control of the top-down camera, plus click-to-select.
// REQ: VIS-01
import {
  panByPixels,
  screenToWorld,
  wheelZoomFactor,
  zoomAround,
  type Point,
  type ViewLimits,
  type ViewState,
} from './view';

export interface CameraInputTarget {
  /** Current framing, or null before the world bounds are known. */
  readonly view: ViewState | null;
  readonly limits: ViewLimits | null;
  setView(view: ViewState): void;
  resetView(): void;
  /** A click (press and release without dragging) at a CSS-pixel point of the element. */
  select(x: number, y: number): void;
  clearSelection(): void;
}

/** Pointer travel (CSS px) after which a press is a drag rather than a click. */
export const DRAG_THRESHOLD_PX = 4;
/** Zoom step of the +/- keys and buttons. */
export const KEY_ZOOM_FACTOR = 1.25;
/** Arrow-key pan step as a fraction of the viewport. */
const KEY_PAN_FRACTION = 0.1;

export function attachCameraInput(element: HTMLElement, target: CameraInputTarget): () => void {
  const pointers = new Map<number, Point>();
  let pressX = 0;
  let pressY = 0;
  let dragging = false;

  const local = (event: MouseEvent): Point => {
    const rect = element.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };

  const pinch = (): { x: number; y: number; distance: number } | null => {
    if (pointers.size !== 2) return null;
    const [a, b] = [...pointers.values()];
    if (a === undefined || b === undefined) return null;
    return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, distance: Math.hypot(a.x - b.x, a.y - b.y) };
  };

  const onPointerDown = (event: PointerEvent): void => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    element.setPointerCapture(event.pointerId);
    const point = local(event);
    pointers.set(event.pointerId, point);
    if (pointers.size === 1) {
      pressX = point.x;
      pressY = point.y;
      dragging = false;
    } else {
      dragging = true;
    }
  };

  const onPointerMove = (event: PointerEvent): void => {
    const previous = pointers.get(event.pointerId);
    if (previous === undefined) return;
    const point = local(event);
    const { view, limits } = target;
    if (pointers.size === 1) {
      pointers.set(event.pointerId, point);
      if (!dragging && Math.hypot(point.x - pressX, point.y - pressY) > DRAG_THRESHOLD_PX) {
        dragging = true;
        element.classList.add('is-dragging');
      }
      if (dragging && view !== null && limits !== null) {
        const dx = point.x - previous.x;
        const dy = point.y - previous.y;
        target.setView(panByPixels(view, dx, dy, element.clientHeight, limits));
      }
      return;
    }
    const before = pinch();
    pointers.set(event.pointerId, point);
    const after = pinch();
    if (before === null || after === null || view === null || limits === null) return;
    const width = element.clientWidth;
    const height = element.clientHeight;
    let next = panByPixels(view, after.x - before.x, after.y - before.y, height, limits);
    if (before.distance > 0 && after.distance > 0) {
      const anchor = screenToWorld(next, after.x, after.y, width, height);
      next = zoomAround(next, before.distance / after.distance, anchor.x, anchor.y, limits);
    }
    target.setView(next);
  };

  const onPointerEnd = (event: PointerEvent): void => {
    if (!pointers.has(event.pointerId)) return;
    const click = pointers.size === 1 && !dragging && event.type === 'pointerup';
    pointers.delete(event.pointerId);
    if (element.hasPointerCapture(event.pointerId)) element.releasePointerCapture(event.pointerId);
    if (click) {
      const point = local(event);
      target.select(point.x, point.y);
    }
    if (pointers.size === 0) {
      dragging = false;
      element.classList.remove('is-dragging');
    }
  };

  const onWheel = (event: WheelEvent): void => {
    event.preventDefault();
    const { view, limits } = target;
    if (view === null || limits === null) return;
    const point = local(event);
    const anchor = screenToWorld(view, point.x, point.y, element.clientWidth, element.clientHeight);
    const factor = wheelZoomFactor(event.deltaY, event.deltaMode);
    target.setView(zoomAround(view, factor, anchor.x, anchor.y, limits));
  };

  const zoomCentered = (factor: number): void => {
    const { view, limits } = target;
    if (view !== null && limits !== null) {
      target.setView(zoomAround(view, factor, view.cx, view.cy, limits));
    }
  };

  const panKeys = (dxFraction: number, dyFraction: number): void => {
    const { view, limits } = target;
    if (view === null || limits === null) return;
    const height = element.clientHeight;
    const dx = dxFraction * element.clientWidth;
    const dy = dyFraction * height;
    target.setView(panByPixels(view, dx, dy, height, limits));
  };

  const onKeyDown = (event: KeyboardEvent): void => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
    if (isEditable(event.target)) return;
    switch (event.key) {
      case 'Home':
      case '0':
        target.resetView();
        break;
      case 'Escape':
        target.clearSelection();
        break;
      case '+':
      case '=':
        zoomCentered(1 / KEY_ZOOM_FACTOR);
        break;
      case '-':
      case '_':
        zoomCentered(KEY_ZOOM_FACTOR);
        break;
      case 'ArrowLeft':
        panKeys(KEY_PAN_FRACTION, 0);
        break;
      case 'ArrowRight':
        panKeys(-KEY_PAN_FRACTION, 0);
        break;
      case 'ArrowUp':
        panKeys(0, KEY_PAN_FRACTION);
        break;
      case 'ArrowDown':
        panKeys(0, -KEY_PAN_FRACTION);
        break;
      default:
        return;
    }
    event.preventDefault();
  };

  element.addEventListener('pointerdown', onPointerDown);
  element.addEventListener('pointermove', onPointerMove);
  element.addEventListener('pointerup', onPointerEnd);
  element.addEventListener('pointercancel', onPointerEnd);
  element.addEventListener('wheel', onWheel, { passive: false });
  window.addEventListener('keydown', onKeyDown);
  return () => {
    element.removeEventListener('pointerdown', onPointerDown);
    element.removeEventListener('pointermove', onPointerMove);
    element.removeEventListener('pointerup', onPointerEnd);
    element.removeEventListener('pointercancel', onPointerEnd);
    element.removeEventListener('wheel', onWheel);
    window.removeEventListener('keydown', onKeyDown);
  };
}

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.tagName === 'SELECT'
  );
}

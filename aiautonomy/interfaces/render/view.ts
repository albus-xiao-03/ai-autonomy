// Top-down orthographic camera math in world meters (x east, y north; north is up on
// screen). Pure functions, shared by pointer, wheel, pinch, keyboard and button controls.
// REQ: VIS-01
import type { Bounds } from '../net/protocol';

/** Camera framing: center in world meters and the visible world height in meters. */
export interface ViewState {
  readonly cx: number;
  readonly cy: number;
  readonly height: number;
}

export interface ViewLimits {
  readonly minHeight: number;
  readonly maxHeight: number;
  readonly bounds: Bounds;
}

export interface Point {
  readonly x: number;
  readonly y: number;
}

/** Margin around the world when it is framed by `fitView` (reset view); it keeps the world's
 * edges clear of the overlaid top bar. */
export const FIT_MARGIN = 1.2;
/** Closest zoom: ten meters of world across the viewport height. */
export const MIN_VIEW_HEIGHT_M = 10;
/** Farthest zoom, relative to the framed world. */
export const MAX_ZOOM_OUT = 2.5;

export function clamp(value: number, min: number, max: number): number {
  return value < min ? min : value > max ? max : value;
}

/** The view that frames the whole world (the reset view). */
export function fitView(bounds: Bounds, aspect: number): ViewState {
  const width = Math.max(bounds.max_x - bounds.min_x, 1);
  const height = Math.max(bounds.max_y - bounds.min_y, 1);
  const ratio = aspect > 0 && Number.isFinite(aspect) ? aspect : 1;
  return {
    cx: (bounds.min_x + bounds.max_x) / 2,
    cy: (bounds.min_y + bounds.max_y) / 2,
    height: Math.max(height, width / ratio) * FIT_MARGIN,
  };
}

export function viewLimits(bounds: Bounds, aspect: number): ViewLimits {
  const fit = fitView(bounds, aspect).height;
  return { minHeight: Math.min(MIN_VIEW_HEIGHT_M, fit), maxHeight: fit * MAX_ZOOM_OUT, bounds };
}

/** Keep the zoom within limits and the view center inside the world. */
export function clampView(view: ViewState, limits: ViewLimits): ViewState {
  const { bounds } = limits;
  return {
    cx: clamp(view.cx, bounds.min_x, bounds.max_x),
    cy: clamp(view.cy, bounds.min_y, bounds.max_y),
    height: clamp(view.height, limits.minHeight, limits.maxHeight),
  };
}

/** Drag by (dx, dy) CSS pixels: the world follows the pointer (screen y points down). */
export function panByPixels(
  view: ViewState,
  dx: number,
  dy: number,
  viewportHeightPx: number,
  limits: ViewLimits,
): ViewState {
  const metersPerPx = view.height / Math.max(1, viewportHeightPx);
  return clampView(
    { cx: view.cx - dx * metersPerPx, cy: view.cy + dy * metersPerPx, height: view.height },
    limits,
  );
}

/** Zoom by `factor` (> 1 zooms out) keeping the world point (ax, ay) fixed on screen. */
export function zoomAround(
  view: ViewState,
  factor: number,
  ax: number,
  ay: number,
  limits: ViewLimits,
): ViewState {
  const height = clamp(view.height * factor, limits.minHeight, limits.maxHeight);
  const k = height / view.height;
  return clampView({ cx: ax + (view.cx - ax) * k, cy: ay + (view.cy - ay) * k, height }, limits);
}

export function screenToWorld(
  view: ViewState,
  sx: number,
  sy: number,
  widthPx: number,
  heightPx: number,
): Point {
  const metersPerPx = view.height / Math.max(1, heightPx);
  return {
    x: view.cx + (sx - widthPx / 2) * metersPerPx,
    y: view.cy - (sy - heightPx / 2) * metersPerPx,
  };
}

export function worldToScreen(
  view: ViewState,
  x: number,
  y: number,
  widthPx: number,
  heightPx: number,
): Point {
  const metersPerPx = view.height / Math.max(1, heightPx);
  return {
    x: widthPx / 2 + (x - view.cx) / metersPerPx,
    y: heightPx / 2 - (y - view.cy) / metersPerPx,
  };
}

/** Wheel or trackpad-pinch delta to a zoom factor (> 1 zooms out). */
export function wheelZoomFactor(deltaY: number, deltaMode: number): number {
  const pixels = deltaMode === 1 ? deltaY * 16 : deltaMode === 2 ? deltaY * 400 : deltaY;
  return Math.exp(clamp(pixels, -240, 240) * 0.002);
}

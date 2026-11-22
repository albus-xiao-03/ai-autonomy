import { describe, expect, it } from 'vitest';
import { gridLines, niceStep } from '../../aiautonomy/interfaces/render/grid';
import {
  clampView,
  FIT_MARGIN,
  fitView,
  MAX_ZOOM_OUT,
  MIN_VIEW_HEIGHT_M,
  panByPixels,
  screenToWorld,
  viewLimits,
  wheelZoomFactor,
  worldToScreen,
  zoomAround,
} from '../../aiautonomy/interfaces/render/view';

const bounds = { min_x: -100, min_y: -50, max_x: 100, max_y: 50 };
const ASPECT = 2;
const W = 1080;
const H = 540;

// @req VIS-01
describe('top-down camera math (@req VIS-01)', () => {
  it('frames the whole world with a margin (reset view)', () => {
    expect(fitView(bounds, ASPECT)).toEqual({ cx: 0, cy: 0, height: 100 * FIT_MARGIN });
    // A tall viewport is limited by the world's width instead.
    expect(fitView(bounds, 1).height).toBeCloseTo(200 * FIT_MARGIN);
  });

  it('clamps zoom between the closest and farthest view', () => {
    const limits = viewLimits(bounds, ASPECT);
    expect(limits.minHeight).toBe(MIN_VIEW_HEIGHT_M);
    expect(limits.maxHeight).toBeCloseTo(100 * FIT_MARGIN * MAX_ZOOM_OUT);
    const view = fitView(bounds, ASPECT);
    expect(zoomAround(view, 1e6, 0, 0, limits).height).toBe(limits.maxHeight);
    expect(zoomAround(view, 1e-6, 0, 0, limits).height).toBe(limits.minHeight);
  });

  it('keeps the point under the cursor fixed while zooming', () => {
    const limits = viewLimits(bounds, ASPECT);
    const view = fitView(bounds, ASPECT);
    const anchor = screenToWorld(view, 800, 120, W, H);
    const zoomed = zoomAround(view, 0.5, anchor.x, anchor.y, limits);
    const after = worldToScreen(zoomed, anchor.x, anchor.y, W, H);
    expect(after.x).toBeCloseTo(800);
    expect(after.y).toBeCloseTo(120);
    expect(zoomed.height).toBeCloseTo(view.height / 2);
  });

  it('pans so the world follows the pointer, with north up', () => {
    const limits = viewLimits(bounds, ASPECT);
    const view = { cx: 0, cy: 0, height: 54 }; // 0.1 m per pixel at 540 px
    const moved = panByPixels(view, 100, 50, H, limits);
    expect(moved.cx).toBeCloseTo(-10); // drag right: the camera moves west
    expect(moved.cy).toBeCloseTo(5); // drag down: the camera moves north
    // The world point that was under the pointer is still under it.
    const grabbed = screenToWorld(view, 300, 200, W, H);
    const now = worldToScreen(moved, grabbed.x, grabbed.y, W, H);
    expect(now.x).toBeCloseTo(400);
    expect(now.y).toBeCloseTo(250);
  });

  it('keeps the view center inside the world', () => {
    const limits = viewLimits(bounds, ASPECT);
    expect(clampView({ cx: 500, cy: -500, height: 1 }, limits)).toEqual({
      cx: 100,
      cy: -50,
      height: MIN_VIEW_HEIGHT_M,
    });
    const far = panByPixels({ cx: 0, cy: 0, height: 54 }, -1e6, 1e6, H, limits);
    expect([far.cx, far.cy]).toEqual([100, 50]);
  });

  it('maps screen to world with north up and east right', () => {
    const view = { cx: 10, cy: 20, height: 54 };
    expect(screenToWorld(view, W / 2, H / 2, W, H)).toEqual({ x: 10, y: 20 });
    const topRight = screenToWorld(view, W, 0, W, H);
    expect(topRight.x).toBeCloseTo(10 + 54);
    expect(topRight.y).toBeCloseTo(20 + 27);
  });

  it('turns wheel deltas into zoom factors', () => {
    expect(wheelZoomFactor(100, 0)).toBeGreaterThan(1); // scroll down: zoom out
    expect(wheelZoomFactor(-100, 0)).toBeLessThan(1); // scroll up: zoom in
    expect(wheelZoomFactor(3, 1)).toBeCloseTo(wheelZoomFactor(48, 0)); // line mode
    expect(wheelZoomFactor(1e9, 0)).toBe(wheelZoomFactor(240, 0)); // one notch at most
  });

  it('spaces the ground grid at 1-2-5 steps with every fifth line major', () => {
    expect([niceStep(7), niceStep(0.3), niceStep(12), niceStep(40)]).toEqual([10, 0.5, 20, 50]);
    const grid = gridLines(bounds);
    expect(grid.step).toBe(10);
    // 21 vertical and 11 horizontal lines; x = -100, -50, 0, 50, 100 and y = -50, 0, 50 are major.
    expect(grid.minor.length / 4).toBe(21 + 11 - 8);
    expect(grid.major.length / 4).toBe(8 + 4);
  });
});

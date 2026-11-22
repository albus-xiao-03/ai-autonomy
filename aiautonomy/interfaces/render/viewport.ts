// Connects the session to the Three.js scene: render loop, resizing, input and picking.
// REQ: VIS-01
import type { Session } from '../net/session';
import { Observable } from '../state/observable';
import { FrameStats } from './frameStats';
import { attachCameraInput } from './input';
import { SceneView } from './scene';
import { worldToScreen, zoomAround, type Point, type ViewState } from './view';

export type WebGlStatus = 'pending' | 'ok' | 'unavailable';

export class Viewport extends Observable {
  readonly frameStats = new FrameStats();
  webgl: WebGlStatus = 'pending';
  readonly #session: Session;
  #scene: SceneView | null = null;

  constructor(session: Session) {
    super();
    this.#session = session;
  }

  /** Current camera framing, or null before the world is known. */
  get view(): ViewState | null {
    const scene = this.#scene;
    return scene?.hasWorld ? scene.view : null;
  }

  /** Start rendering into `canvas`; returns the teardown. */
  attach(canvas: HTMLCanvasElement): () => void {
    let scene: SceneView;
    try {
      scene = new SceneView(canvas, this.#session.store.movers);
    } catch {
      this.#setWebgl('unavailable');
      return () => {
        // Nothing was created.
      };
    }
    this.#scene = scene;
    this.#setWebgl('ok');
    const { store, selection } = this.#session;

    const resize = (): void => {
      scene.resize(canvas.clientWidth, canvas.clientHeight);
    };
    const syncWorld = (): void => {
      const bounds = store.world?.bounds;
      if (bounds !== undefined) scene.setBounds(bounds);
      scene.ensureCapacity(store.movers.count);
    };
    resize();
    syncWorld();
    const unsubscribe = store.subscribe(syncWorld);
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    const detachInput = attachCameraInput(canvas, {
      get view() {
        return scene.hasWorld ? scene.view : null;
      },
      get limits() {
        return scene.limits;
      },
      setView: (view) => {
        scene.setView(view);
      },
      resetView: () => {
        scene.resetView();
      },
      select: (x, y) => {
        this.#session.inspect(scene.pick(x, y, performance.now()));
      },
      clearSelection: () => {
        this.#session.inspect(null);
      },
    });

    let frame = 0;
    const loop = (now: number): void => {
      frame = requestAnimationFrame(loop);
      this.frameStats.record(now);
      scene.frame(now, selection.id);
    };
    frame = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      unsubscribe();
      detachInput();
      scene.dispose();
      this.#scene = null;
    };
  }

  resetView(): void {
    this.#scene?.resetView();
  }

  /** Zoom around the view center; `factor` > 1 zooms out. */
  zoomBy(factor: number): void {
    const scene = this.#scene;
    const limits = scene?.limits ?? null;
    if (scene === null || limits === null) return;
    const view = scene.view;
    scene.setView(zoomAround(view, factor, view.cx, view.cy, limits));
  }

  /** CSS-pixel position of the mover in slot `index` (debugging and e2e tests). */
  moverScreenPosition(index: number): Point | null {
    const scene = this.#scene;
    const tracks = this.#session.store.movers;
    if (scene === null || index < 0 || index >= tracks.count) return null;
    const alpha = tracks.alpha(performance.now());
    const x = tracks.x(index, alpha);
    const y = tracks.y(index, alpha);
    return worldToScreen(scene.view, x, y, scene.width, scene.height);
  }

  /** Center the view on the mover in slot `index` (debugging and e2e tests). */
  focusMover(index: number): boolean {
    const scene = this.#scene;
    const tracks = this.#session.store.movers;
    if (scene === null || index < 0 || index >= tracks.count) return false;
    const alpha = tracks.alpha(performance.now());
    scene.setView({
      cx: tracks.x(index, alpha),
      cy: tracks.y(index, alpha),
      height: scene.view.height,
    });
    return true;
  }

  #setWebgl(status: WebGlStatus): void {
    this.webgl = status;
    this.notify();
  }
}

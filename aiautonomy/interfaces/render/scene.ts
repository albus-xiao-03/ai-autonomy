// Three.js scene for the top-down map: ground and grid sized from `world.bounds`, movers as
// one InstancedMesh interpolated every frame, and the selection highlight.
// REQ: VIS-01
import {
  BufferGeometry,
  CircleGeometry,
  Color,
  DynamicDrawUsage,
  Float32BufferAttribute,
  InstancedMesh,
  LineBasicMaterial,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  OrthographicCamera,
  Plane,
  PlaneGeometry,
  Raycaster,
  RingGeometry,
  Scene,
  Vector2,
  Vector3,
  WebGLRenderer,
} from 'three';
import type { Bounds } from '../net/protocol';
import type { Tracks } from '../state/tracks';
import { gridLines } from './grid';
import { SCENE } from './theme';
import { clampView, fitView, viewLimits, type ViewLimits, type ViewState } from './view';

const CAMERA_HEIGHT = 1000;
/** Heights (three y) of the flat layers above the ground; the camera looks straight down. */
const LAYER_GRID = 0.05;
const LAYER_MOVERS = 0.5;
const LAYER_SELECTION = 0.6;
/** Mover disc radius in meters, and its minimum on screen in CSS pixels. */
const MOVER_RADIUS_M = 1.2;
const MOVER_MIN_RADIUS_PX = 3.5;
/** Click tolerance around a mover in CSS pixels. */
const PICK_RADIUS_PX = 10;
const MAX_PIXEL_RATIO = 2;
const INITIAL_CAPACITY = 256;

type WorldObject =
  Mesh<PlaneGeometry, MeshBasicMaterial> | LineSegments<BufferGeometry, LineBasicMaterial>;

export class SceneView {
  readonly renderer: WebGLRenderer;
  readonly camera = new OrthographicCamera(-1, 1, 1, -1, 1, CAMERA_HEIGHT * 4);
  readonly #scene = new Scene();
  readonly #tracks: Tracks;
  readonly #moverGeometry = new CircleGeometry(1, 18).rotateX(-Math.PI / 2);
  readonly #moverMaterial = new MeshBasicMaterial({ color: SCENE.mover });
  readonly #selectionRing: Mesh<RingGeometry, MeshBasicMaterial>;
  readonly #selectionDot: Mesh<CircleGeometry, MeshBasicMaterial>;
  #movers: InstancedMesh<CircleGeometry, MeshBasicMaterial>;
  #world: WorldObject[] = [];
  #bounds: Bounds | null = null;
  #limits: ViewLimits | null = null;
  #view: ViewState = { cx: 0, cy: 0, height: 100 };
  #width = 1;
  #height = 1;
  readonly #raycaster = new Raycaster();
  readonly #pointer = new Vector2();
  readonly #hit = new Vector3();
  readonly #groundPlane = new Plane(new Vector3(0, 1, 0), 0);

  constructor(canvas: HTMLCanvasElement, tracks: Tracks) {
    this.#tracks = tracks;
    this.renderer = new WebGLRenderer({
      canvas,
      antialias: true,
      powerPreference: 'high-performance',
    });
    this.renderer.setPixelRatio(pixelRatio());
    this.#scene.background = new Color(SCENE.background);
    // Look straight down (-y): screen up is north (three -z), screen right is east (+x).
    this.camera.rotation.set(-Math.PI / 2, 0, 0);
    this.#movers = this.#createMovers(INITIAL_CAPACITY);
    this.#selectionRing = new Mesh(
      new RingGeometry(1.6, 2.1, 40).rotateX(-Math.PI / 2),
      new MeshBasicMaterial({ color: SCENE.selection }),
    );
    this.#selectionDot = new Mesh(
      this.#moverGeometry,
      new MeshBasicMaterial({ color: SCENE.selection }),
    );
    for (const mesh of [this.#selectionRing, this.#selectionDot]) {
      mesh.visible = false;
      mesh.frustumCulled = false;
      this.#scene.add(mesh);
    }
  }

  get view(): ViewState {
    return this.#view;
  }

  get limits(): ViewLimits | null {
    return this.#limits;
  }

  get hasWorld(): boolean {
    return this.#bounds !== null;
  }

  /** Viewport size in CSS pixels. */
  get width(): number {
    return this.#width;
  }

  get height(): number {
    return this.#height;
  }

  /** Build the ground and grid for new bounds and frame the world; no-op if unchanged. */
  setBounds(bounds: Bounds): void {
    const current = this.#bounds;
    if (
      current?.min_x === bounds.min_x &&
      current.min_y === bounds.min_y &&
      current.max_x === bounds.max_x &&
      current.max_y === bounds.max_y
    ) {
      return;
    }
    this.#bounds = { ...bounds };
    this.#buildWorld(bounds);
    this.#limits = viewLimits(bounds, this.#aspect());
    this.resetView();
  }

  /** Match the canvas size in CSS pixels; device pixel ratio is capped at 2. */
  resize(width: number, height: number): void {
    this.#width = Math.max(1, Math.round(width));
    this.#height = Math.max(1, Math.round(height));
    this.renderer.setPixelRatio(pixelRatio());
    this.renderer.setSize(this.#width, this.#height, false);
    if (this.#bounds !== null) {
      this.#limits = viewLimits(this.#bounds, this.#aspect());
      this.#view = clampView(this.#view, this.#limits);
    }
    this.#applyCamera();
  }

  setView(view: ViewState): void {
    this.#view = this.#limits === null ? view : clampView(view, this.#limits);
    this.#applyCamera();
  }

  resetView(): void {
    if (this.#bounds !== null) this.setView(fitView(this.#bounds, this.#aspect()));
  }

  /** Mover disc radius in meters at the current zoom. */
  moverRadius(): number {
    return Math.max(MOVER_RADIUS_M, (MOVER_MIN_RADIUS_PX * this.#view.height) / this.#height);
  }

  /** Grow the instanced mesh to hold `count` movers (outside the render loop). */
  ensureCapacity(count: number): void {
    const capacity = this.#movers.instanceMatrix.count;
    if (count <= capacity) return;
    let next = capacity;
    while (next < count) next *= 2;
    this.#scene.remove(this.#movers);
    this.#movers.dispose();
    this.#movers = this.#createMovers(next);
  }

  /** Interpolate every mover to `now` and render. Allocation-free. */
  frame(now: number, selectedId: string | null): void {
    const tracks = this.#tracks;
    const count = tracks.count;
    if (count > this.#movers.instanceMatrix.count) this.ensureCapacity(count);
    const alpha = tracks.alpha(now);
    const radius = this.moverRadius();
    const matrices = this.#movers.instanceMatrix.array as Float32Array;
    for (let i = 0; i < count; i++) {
      const o = i * 16;
      matrices[o] = radius;
      matrices[o + 5] = radius;
      matrices[o + 10] = radius;
      matrices[o + 12] = tracks.x(i, alpha);
      matrices[o + 13] = LAYER_MOVERS;
      matrices[o + 14] = -tracks.y(i, alpha);
      matrices[o + 15] = 1;
    }
    this.#movers.count = count;
    this.#movers.instanceMatrix.needsUpdate = true;

    const slot = selectedId === null ? undefined : tracks.slotOf(selectedId);
    this.#selectionRing.visible = slot !== undefined;
    this.#selectionDot.visible = slot !== undefined;
    if (slot !== undefined) {
      const x = tracks.x(slot, alpha);
      const z = -tracks.y(slot, alpha);
      this.#selectionRing.position.set(x, LAYER_SELECTION, z);
      this.#selectionRing.scale.setScalar(radius);
      this.#selectionDot.position.set(x, LAYER_SELECTION, z);
      this.#selectionDot.scale.setScalar(radius);
    }
    this.renderer.render(this.#scene, this.camera);
  }

  /** Mover under the CSS-pixel point (sx, sy): a ray to the ground, then the nearest mover. */
  pick(sx: number, sy: number, now: number): string | null {
    this.#pointer.set((sx / this.#width) * 2 - 1, 1 - (sy / this.#height) * 2);
    this.camera.updateMatrixWorld();
    this.#raycaster.setFromCamera(this.#pointer, this.camera);
    const hit = this.#raycaster.ray.intersectPlane(this.#groundPlane, this.#hit);
    if (hit === null) return null;
    const tolerance = Math.max(
      this.moverRadius(),
      (PICK_RADIUS_PX * this.#view.height) / this.#height,
    );
    return this.#tracks.nearest(hit.x, -hit.z, tolerance, this.#tracks.alpha(now));
  }

  dispose(): void {
    this.#disposeWorld();
    this.#scene.remove(this.#movers);
    this.#movers.dispose();
    this.#moverGeometry.dispose();
    this.#moverMaterial.dispose();
    this.#selectionRing.geometry.dispose();
    this.#selectionRing.material.dispose();
    this.#selectionDot.material.dispose();
    this.renderer.dispose();
  }

  #createMovers(capacity: number): InstancedMesh<CircleGeometry, MeshBasicMaterial> {
    const mesh = new InstancedMesh(this.#moverGeometry, this.#moverMaterial, capacity);
    mesh.instanceMatrix.setUsage(DynamicDrawUsage);
    mesh.instanceMatrix.array.fill(0);
    mesh.count = 0;
    mesh.frustumCulled = false;
    this.#scene.add(mesh);
    return mesh;
  }

  #buildWorld(bounds: Bounds): void {
    this.#disposeWorld();
    const ground = new Mesh(
      new PlaneGeometry(bounds.max_x - bounds.min_x, bounds.max_y - bounds.min_y).rotateX(
        -Math.PI / 2,
      ),
      new MeshBasicMaterial({ color: SCENE.ground }),
    );
    ground.position.set((bounds.min_x + bounds.max_x) / 2, 0, -(bounds.min_y + bounds.max_y) / 2);
    const grid = gridLines(bounds);
    this.#world = [
      ground,
      lineSegments(grid.minor, SCENE.lineOpacity),
      lineSegments(grid.major, SCENE.lineStrongOpacity),
    ];
    for (const object of this.#world) this.#scene.add(object);
  }

  #disposeWorld(): void {
    for (const object of this.#world) {
      this.#scene.remove(object);
      object.geometry.dispose();
      object.material.dispose();
    }
    this.#world = [];
  }

  #applyCamera(): void {
    const halfHeight = this.#view.height / 2;
    const halfWidth = halfHeight * this.#aspect();
    this.camera.left = -halfWidth;
    this.camera.right = halfWidth;
    this.camera.top = halfHeight;
    this.camera.bottom = -halfHeight;
    this.camera.position.set(this.#view.cx, CAMERA_HEIGHT, -this.#view.cy);
    this.camera.updateProjectionMatrix();
  }

  #aspect(): number {
    return this.#width / this.#height;
  }
}

function pixelRatio(): number {
  return Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO);
}

/** Flat [x1, y1, x2, y2, ...] world segments as hairlines on the grid layer. */
function lineSegments(
  flat: readonly number[],
  opacity: number,
): LineSegments<BufferGeometry, LineBasicMaterial> {
  const positions = new Float32Array((flat.length / 2) * 3);
  for (let i = 0, j = 0; i + 1 < flat.length; i += 2, j += 3) {
    positions[j] = flat[i] ?? 0;
    positions[j + 1] = LAYER_GRID;
    positions[j + 2] = -(flat[i + 1] ?? 0);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
  const material = new LineBasicMaterial({
    color: SCENE.line,
    transparent: true,
    opacity,
    depthWrite: false,
  });
  return new LineSegments(geometry, material);
}

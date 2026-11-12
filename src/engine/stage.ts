import {
  ACESFilmicToneMapping,
  DirectionalLight,
  HemisphereLight,
  Mesh,
  MeshBasicMaterial,
  PerspectiveCamera,
  PlaneGeometry,
  PMREMGenerator,
  Scene,
  SRGBColorSpace,
  Spherical,
  Vector3,
  WebGLRenderer,
} from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { shadowTexture } from '../builders/materials';
import { Tweens, easeInOut } from './tween';

export interface Pose {
  position: Vector3;
  target: Vector3;
}

/**
 * Renderer, camera, controls and a render-on-demand loop.
 * Only one system owns the camera at a time: during a fly-to the controls are disabled.
 */
export class Stage {
  readonly renderer: WebGLRenderer;
  readonly scene = new Scene();
  readonly camera = new PerspectiveCamera(30, 1, 5, 5000);
  readonly controls: OrbitControls;
  readonly tweens = new Tweens();
  private dirty = true;
  private last = performance.now();
  private insets = { left: 0, right: 0, bottom: 0 };
  private size = { w: 1, h: 1 };
  private frameHooks: ((dt: number) => boolean)[] = [];
  onContextLost?: () => void;

  constructor(private host: HTMLElement) {
    this.renderer = new WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = SRGBColorSpace;
    this.renderer.toneMapping = ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    host.appendChild(this.renderer.domElement);
    this.renderer.domElement.addEventListener('webglcontextlost', (e) => {
      e.preventDefault();
      this.onContextLost?.();
    });

    const pmrem = new PMREMGenerator(this.renderer);
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    this.scene.environmentIntensity = 0.9;
    pmrem.dispose();

    const key = new DirectionalLight('#ffffff', 1.6);
    key.position.set(200, 300, 400);
    const rim = new DirectionalLight('#ffd9c2', 0.8);
    rim.position.set(-300, 100, -300);
    this.scene.add(key, rim, new HemisphereLight('#ffffff', '#30303a', 0.35));

    // Soft floor shadow under the floating phone.
    const shadow = new Mesh(
      new PlaneGeometry(180, 120),
      new MeshBasicMaterial({ map: shadowTexture(), transparent: true, depthWrite: false, opacity: 0.6 }),
    );
    shadow.rotation.x = -Math.PI / 2;
    shadow.position.y = -112;
    shadow.renderOrder = -1;
    this.scene.add(shadow);

    this.camera.position.set(230, 110, 330);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 60;
    this.controls.maxDistance = 900;
    this.controls.target.set(0, 0, 0);
    this.controls.addEventListener('change', () => this.invalidate());

    new ResizeObserver(() => this.resize()).observe(host);
    this.resize();
    this.renderer.setAnimationLoop(() => this.loop());
  }

  invalidate(): void {
    this.dirty = true;
  }

  /** Register a per-frame hook; return true from it to keep rendering continuously. */
  onFrame(fn: (dt: number) => boolean): void {
    this.frameHooks.push(fn);
  }

  /** Keep the subject centred in the part of the canvas not covered by panels. */
  setInsets(left: number, right: number, bottom: number): void {
    if (left === this.insets.left && right === this.insets.right && bottom === this.insets.bottom) return;
    this.insets = { left, right, bottom };
    this.applyViewOffset();
  }

  private resize(): void {
    const w = Math.max(1, this.host.clientWidth),
      h = Math.max(1, this.host.clientHeight);
    this.size = { w, h };
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.applyViewOffset();
  }

  private applyViewOffset(): void {
    const { w, h } = this.size;
    const { left, right, bottom } = this.insets;
    const visibleW = w - left - right,
      visibleH = h - bottom;
    this.camera.aspect = w / h;
    this.camera.setViewOffset(w, h, (right - left) / 2, bottom / 2, w, h);
    // Pull back a little on narrow viewports so the phone fits in the visible area.
    this.camera.zoom = Math.min(1, Math.max(0.55, Math.min(visibleW / 520, visibleH / 640)));
    this.camera.updateProjectionMatrix();
    this.invalidate();
  }

  private loop(): void {
    const now = performance.now();
    const dt = Math.min((now - this.last) / 1000, 0.05);
    this.last = now;
    this.tweens.tick(dt);
    const damping = this.controls.enabled ? this.controls.update() : false;
    let keep = false;
    for (const f of this.frameHooks) keep = f(dt) || keep;
    if (this.dirty || this.tweens.active || damping || keep) {
      this.renderer.render(this.scene, this.camera);
      this.dirty = false;
    }
  }

  pose(): Pose {
    return { position: this.camera.position.clone(), target: this.controls.target.clone() };
  }

  /** Fly the camera; the controls are disabled for the duration and resynced afterwards. */
  private flight = 0;

  async flyTo(pose: Pose, dur = 0.9): Promise<void> {
    const id = ++this.flight;
    // Flush residual orbit inertia so it cannot bend the flight or drift afterwards.
    if (this.controls.enabled) {
      this.controls.enableDamping = false;
      this.controls.update();
      this.controls.enableDamping = true;
    }
    this.controls.enabled = false;
    const t0 = this.controls.target.clone();
    // Interpolate around the target in spherical coordinates so front <-> back swings
    // around the phone instead of passing through it.
    const s0 = new Spherical().setFromVector3(this.camera.position.clone().sub(t0));
    const s1 = new Spherical().setFromVector3(pose.position.clone().sub(pose.target));
    let dTheta = s1.theta - s0.theta;
    if (dTheta > Math.PI) dTheta -= Math.PI * 2;
    if (dTheta < -Math.PI) dTheta += Math.PI * 2;
    const sph = new Spherical();
    const off = new Vector3();
    await this.tweens.run(
      dur,
      (k) => {
        this.controls.target.lerpVectors(t0, pose.target, k);
        sph.set(s0.radius + (s1.radius - s0.radius) * k, s0.phi + (s1.phi - s0.phi) * k, s0.theta + dTheta * k);
        this.camera.position.copy(this.controls.target).add(off.setFromSpherical(sph));
        this.camera.lookAt(this.controls.target);
      },
      { key: 'camera', ease: easeInOut },
    );
    if (id !== this.flight) return; // superseded by a newer flight
    this.controls.enabled = true;
    this.controls.update();
    this.invalidate();
  }
}

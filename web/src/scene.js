// Renderer, lights, orbit controls and the camera tween helper.
import * as THREE from 'three';
import { OrbitControls } from '../vendor/three/OrbitControls.js';

export const COLORS = {
  background: 0x0b1016,
  slab: 0x1c2b3d,
  accent: 0x4fd1c5,
  event: 0xf56565,
  forklift: 0xf6ad55,
  vehicle: 0xa0aec0,
  zones: { restricted: 0xf56565, walkway: 0x4fd1c5, dock: 0xa0aec0 },
};

export class Stage {
  constructor(canvas) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(COLORS.background);
    this.camera = new THREE.PerspectiveCamera(45, 1, 0.5, 2000);
    this.camera.position.set(0, 90, 130);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.02;
    this.scene.add(new THREE.HemisphereLight(0xcfe8ff, 0x101820, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.2);
    sun.position.set(60, 120, 40);
    this.scene.add(sun);
    this.tween = null;
    this.clock = new THREE.Clock();
    this.onFrame = [];
    addEventListener('resize', () => this.resize());
    this.resize();
    this.renderer.setAnimationLoop(() => this.frame());
  }

  resize() {
    this.renderer.setSize(innerWidth, innerHeight, false);
    this.camera.aspect = innerWidth / innerHeight;
    this.camera.updateProjectionMatrix();
  }

  // Fly the camera so it looks at `target` from `offset` away, over `ms` milliseconds.
  flyTo(target, offset, ms = 900) {
    this.tween = {
      start: performance.now(),
      ms,
      fromPosition: this.camera.position.clone(),
      fromTarget: this.controls.target.clone(),
      toPosition: target.clone().add(offset),
      toTarget: target.clone(),
    };
  }

  frame() {
    const dt = Math.min(this.clock.getDelta(), 0.1);
    if (this.tween) {
      const t = Math.min((performance.now() - this.tween.start) / this.tween.ms, 1);
      const k = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      this.camera.position.lerpVectors(this.tween.fromPosition, this.tween.toPosition, k);
      this.controls.target.lerpVectors(this.tween.fromTarget, this.tween.toTarget, k);
      if (t >= 1) this.tween = null;
    }
    this.controls.update();
    for (const update of this.onFrame) update(dt, performance.now());
    this.renderer.render(this.scene, this.camera);
  }
}

// Text that always faces the camera. `height` is in metres.
export function makeLabel(text, height, color = '#dbe4ee') {
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');
  const font = '600 64px system-ui, sans-serif';
  context.font = font;
  canvas.width = Math.ceil(context.measureText(text).width) + 16;
  canvas.height = 84;
  context.font = font;
  context.fillStyle = color;
  context.textBaseline = 'middle';
  context.fillText(text, 8, 44);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false }));
  sprite.scale.set(height * canvas.width / canvas.height, height, 1);
  return sprite;
}

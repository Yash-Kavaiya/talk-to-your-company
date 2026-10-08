// Live people and vehicles: instanced meshes per class on each floor, lerped between `state` messages.
import * as THREE from 'three';
import { COLORS } from './scene.js';

const CAPACITY = 64;
const STATE_INTERVAL_MS = 200;
const box = (x, y, z) => new THREE.BoxGeometry(x, y, z);

// Each class is a few parts. Offsets are in the track's own frame: +x is the direction of travel.
const SHAPES = {
  person: [
    { geometry: new THREE.CapsuleGeometry(0.26, 0.85, 4, 10), color: COLORS.accent, offset: [0, 0.72, 0] },
    { geometry: new THREE.SphereGeometry(0.2, 12, 10), color: 0xe8c4a0, offset: [0, 1.6, 0] },
  ],
  forklift: [
    { geometry: box(1.6, 0.8, 1.1), color: COLORS.forklift, offset: [-0.25, 0.6, 0] },
    { geometry: box(0.9, 0.9, 0.95), color: 0x2d3748, offset: [-0.35, 1.45, 0] },
    { geometry: box(0.16, 2.3, 0.9), color: 0x2d3748, offset: [0.65, 1.2, 0] },
    { geometry: box(1.0, 0.08, 0.75), color: 0xa0aec0, offset: [1.2, 0.14, 0] },
  ],
  vehicle: [
    { geometry: box(1.5, 1.7, 2.1), color: 0x4a6fa5, offset: [1.7, 1.05, 0] },
    { geometry: box(3.6, 2.3, 2.2), color: COLORS.vehicle, offset: [-0.9, 1.35, 0] },
    { geometry: box(5.0, 0.3, 1.9), color: 0x1f2733, offset: [-0.1, 0.25, 0] },
  ],
};

export class Tracks {
  constructor(stage, twin) {
    this.twin = twin;
    this.meshes = new Map(); // "P1/F1" -> {person: [mesh per part], forklift: [...], vehicle: [...]}
    this.tracks = new Map(); // "P1/F1" -> Map(id -> {cls, from, to, heading, at})
    this.base = new THREE.Object3D();
    this.part = new THREE.Matrix4();
    stage.onFrame.push((dt, now) => this.update(now));
  }

  // Call after the twin was (re)built.
  rebuild() {
    this.meshes.clear();
    this.tracks.clear();
    for (const [key, floor] of this.twin.floors) {
      const perClass = {};
      for (const [cls, parts] of Object.entries(SHAPES)) {
        perClass[cls] = parts.map((part) => {
          const mesh = new THREE.InstancedMesh(part.geometry, new THREE.MeshStandardMaterial({ color: part.color }), CAPACITY);
          mesh.count = 0;
          mesh.frustumCulled = false;
          floor.group.add(mesh);
          return mesh;
        });
      }
      this.meshes.set(key, perClass);
      this.tracks.set(key, new Map());
    }
  }

  onState(state) {
    const now = performance.now();
    for (const [key, list] of Object.entries(state.zones)) {
      const known = this.tracks.get(key);
      if (!known) continue;
      const next = new Map();
      for (const t of list) {
        const old = known.get(t.id);
        const from = old ? this.position(old, now) : { x: t.x, y: t.y };
        const moved = Math.hypot(t.x - from.x, t.y - from.y) > 0.02;
        const heading = moved ? Math.atan2(t.y - from.y, t.x - from.x) : (old ? old.heading : 0);
        next.set(t.id, { cls: t.cls, from, to: { x: t.x, y: t.y }, heading, at: now });
      }
      this.tracks.set(key, next);
    }
  }

  position(track, now) {
    const k = Math.min((now - track.at) / STATE_INTERVAL_MS, 1);
    return { x: track.from.x + (track.to.x - track.from.x) * k, y: track.from.y + (track.to.y - track.from.y) * k };
  }

  update(now) {
    for (const [key, known] of this.tracks) {
      const meshes = this.meshes.get(key);
      const counts = { person: 0, forklift: 0, vehicle: 0 };
      for (const track of known.values()) {
        const parts = meshes[track.cls];
        if (!parts || counts[track.cls] >= CAPACITY) continue;
        const p = this.position(track, now);
        this.base.position.copy(this.twin.toLocal(key, p.x, p.y));
        this.base.rotation.set(0, -track.heading, 0);
        this.base.updateMatrix();
        const index = counts[track.cls]++;
        parts.forEach((mesh, i) => {
          this.part.makeTranslation(...SHAPES[track.cls][i].offset).premultiply(this.base.matrix);
          mesh.setMatrixAt(index, this.part);
        });
      }
      for (const [cls, parts] of Object.entries(meshes)) {
        for (const mesh of parts) {
          mesh.count = counts[cls];
          mesh.instanceMatrix.needsUpdate = true;
        }
      }
    }
  }
}

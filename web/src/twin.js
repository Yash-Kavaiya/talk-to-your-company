// Builds plants and floors from the `site` message; explode and focus animations.
import * as THREE from 'three';
import { COLORS, makeLabel } from './scene.js';

const PLANT_GAP = 14; // metres between plants
const FLOOR_GAP = 5; // stacked
const FLOOR_RISE_OPEN = 8; // spread apart when the plant is selected: each floor steps up...
const FLOOR_SETBACK_OPEN = 4; // ...and back by its depth plus this, so no floor hides another
const SLAB = 0.3;
const WALL_HEIGHT = 2.4;
const GRID_M = 5;
const ZONE_NAMES = { restricted: 'RESTRICTED', walkway: 'WALKWAY', dock: 'LOADING DOCK' };

export const zoneKey = (plant, floor) => `${plant}/${floor}`;

export class Twin {
  constructor(stage, fixtures) {
    this.stage = stage;
    this.fixtures = fixtures;
    this.root = new THREE.Group();
    stage.scene.add(this.root);
    this.floors = new Map(); // "P1/F1" -> {group, slab, plant, floor, index, w, d, x}
    this.plants = new Map(); // "P1" -> {id, name, x, w, d, floors: [keys]}
    this.selected = null;
    this.extent = 100;
    stage.onFrame.push((dt) => this.update(dt));
  }

  build(site) {
    this.root.clear();
    this.fixtures.clear();
    this.floors.clear();
    this.plants.clear();
    const widths = site.plants.map((p) => Math.max(...p.floors.map((f) => f.size_m[0])));
    this.extent = widths.reduce((a, b) => a + b, 0) + PLANT_GAP * (site.plants.length - 1);
    let left = -this.extent / 2;
    site.plants.forEach((plant, i) => {
      const x = left + widths[i] / 2;
      left += widths[i] + PLANT_GAP;
      const depth = Math.max(...plant.floors.map((f) => f.size_m[1]));
      const label = makeLabel(plant.name, 4);
      const entry = { id: plant.id, name: plant.name, x, w: widths[i], d: depth, floors: [], label };
      this.plants.set(plant.id, entry);
      label.position.set(x, -4, depth / 2 + 5);
      this.root.add(label);
      plant.floors.forEach((floor, index) => {
        const key = zoneKey(plant.id, floor.id);
        entry.floors.push(key);
        this.floors.set(key, this.buildFloor(plant, floor, index, x));
      });
    });
  }

  buildFloor(plant, floor, index, x) {
    const [w, d] = floor.size_m;
    const group = new THREE.Group();
    group.position.set(x, index * FLOOR_GAP, 0);
    const slab = new THREE.Mesh(
      new THREE.BoxGeometry(w, SLAB, d),
      new THREE.MeshStandardMaterial({ color: COLORS.slab, transparent: true, opacity: 0.72, depthWrite: false }),
    );
    slab.position.y = -SLAB / 2;
    slab.userData = { plant: plant.id, floor: floor.id };
    group.add(slab);
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(slab.geometry),
      new THREE.LineBasicMaterial({ color: COLORS.accent, transparent: true, opacity: 0.55 }),
    );
    edges.position.copy(slab.position);
    group.add(edges);
    group.add(floorGrid(w, d), walls(w, d));
    for (const zone of floor.zones) {
      const points = zone.polygon.map(([px, py]) => new THREE.Vector2(px - w / 2, -(py - d / 2)));
      const color = COLORS.zones[zone.type];
      const fill = new THREE.Mesh(
        new THREE.ShapeGeometry(new THREE.Shape(points)),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.2, depthWrite: false, side: THREE.DoubleSide }),
      );
      fill.rotation.x = -Math.PI / 2;
      fill.position.y = 0.03;
      const outline = new THREE.LineLoop(
        new THREE.BufferGeometry().setFromPoints(zone.polygon.map(([px, py]) => new THREE.Vector3(px - w / 2, 0.05, py - d / 2))),
        new THREE.LineBasicMaterial({ color }),
      );
      group.add(fill, outline, zoneLabel(zone, w, d, color));
    }
    this.fixtures.build(group, floor, zoneKey(plant.id, floor.id));
    const label = makeLabel(floor.id, 2.2, '#7d8da1');
    label.position.set(-w / 2 - 3, 0.5, d / 2);
    group.add(label);
    this.root.add(group);
    return { group, slab, plant: plant.id, floor: floor.id, camera: floor.camera.id, index, w, d, x };
  }

  // Where a floor rests: stacked, or stepped up and back when its plant is selected.
  restingPlace(f) {
    if (this.selected !== f.plant) return { y: f.index * FLOOR_GAP, z: 0 };
    const depth = this.plants.get(f.plant).d;
    return { y: f.index * FLOOR_RISE_OPEN, z: -f.index * (depth + FLOOR_SETBACK_OPEN) };
  }

  // Floor metres -> position inside the floor's group.
  toLocal(key, x, y, height = 0) {
    const f = this.floors.get(key);
    return new THREE.Vector3(x - f.w / 2, height, y - f.d / 2);
  }

  // Selecting a plant spreads its floors apart (AC1.3). null closes everything.
  select(plantId) {
    this.selected = this.plants.has(plantId) ? plantId : null;
  }

  update(dt) {
    const k = 1 - Math.exp(-dt * 6);
    for (const p of this.plants.values()) p.label.visible = this.selected === null; // big names only in the overview
    for (const f of this.floors.values()) {
      const place = this.restingPlace(f);
      f.group.position.y += (place.y - f.group.position.y) * k;
      f.group.position.z += (place.z - f.group.position.z) * k;
    }
  }

  // Camera moves: where to look and from where. They use the floors' resting places, not the animated ones.
  focusFloor(plantId, floorId) {
    const f = this.floors.get(zoneKey(plantId, floorId));
    if (!f) return;
    this.select(plantId);
    const size = Math.max(f.w, f.d);
    const place = this.restingPlace(f);
    this.stage.flyTo(new THREE.Vector3(f.x, place.y, place.z), new THREE.Vector3(0, size * 0.85, size * 1.0));
  }

  focusPlant(plantId) {
    const p = this.plants.get(plantId);
    if (!p) return;
    this.select(plantId);
    const steps = p.floors.length - 1;
    const back = steps * (p.d + FLOOR_SETBACK_OPEN);
    const size = Math.max(p.w, p.d + back);
    this.stage.flyTo(new THREE.Vector3(p.x, steps * FLOOR_RISE_OPEN / 2, -back / 2), new THREE.Vector3(0, size * 1.0, size * 0.95));
  }

  overview() {
    this.select(null);
    this.stage.flyTo(new THREE.Vector3(0, 5, 0), new THREE.Vector3(0, this.extent * 0.55, this.extent * 0.95));
  }

  slabs() {
    return [...this.floors.values()].map((f) => f.slab);
  }
}

// Faint lines every GRID_M metres, like painted bay markings.
function floorGrid(w, d) {
  const points = [];
  for (let x = GRID_M; x < w; x += GRID_M) points.push(x - w / 2, 0.02, -d / 2, x - w / 2, 0.02, d / 2);
  for (let y = GRID_M; y < d; y += GRID_M) points.push(-w / 2, 0.02, y - d / 2, w / 2, 0.02, y - d / 2);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
  return new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color: 0x8aa0b8, transparent: true, opacity: 0.14 }));
}

// See-through outer walls, so a floor reads as a room without hiding what is inside.
function walls(w, d) {
  const group = new THREE.Group();
  const material = new THREE.MeshStandardMaterial({ color: 0x8fb3d9, transparent: true, opacity: 0.07, depthWrite: false, side: THREE.DoubleSide });
  for (const [sx, sz, px, pz] of [[w, 0.15, 0, -d / 2], [w, 0.15, 0, d / 2], [0.15, d, -w / 2, 0], [0.15, d, w / 2, 0]]) {
    const wall = new THREE.Mesh(new THREE.BoxGeometry(sx, WALL_HEIGHT, sz), material);
    wall.position.set(px, WALL_HEIGHT / 2, pz);
    group.add(wall);
  }
  return group;
}

// The zone's name painted flat on the floor, sized to fit its bounding box.
function zoneLabel(zone, w, d, color) {
  const xs = zone.polygon.map((p) => p[0]);
  const ys = zone.polygon.map((p) => p[1]);
  const width = Math.max(...xs) - Math.min(...xs);
  const depth = Math.max(...ys) - Math.min(...ys);
  const text = ZONE_NAMES[zone.type] || zone.type.toUpperCase();
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 96;
  const context = canvas.getContext('2d');
  context.font = '700 64px system-ui, sans-serif';
  context.fillStyle = `#${new THREE.Color(color).getHexString()}`;
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(text, 256, 50, 500);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const length = Math.min(width * 0.85, depth * 0.6 * (512 / 96), 9);
  const label = new THREE.Mesh(
    new THREE.PlaneGeometry(length, length * (96 / 512)),
    new THREE.MeshBasicMaterial({ map: texture, transparent: true, opacity: 0.75, depthWrite: false }),
  );
  label.rotation.x = -Math.PI / 2;
  label.position.set((Math.min(...xs) + Math.max(...xs)) / 2 - w / 2, 0.06, Math.max(...ys) - d / 2 - Math.min(depth * 0.2, 1.2));
  return label;
}

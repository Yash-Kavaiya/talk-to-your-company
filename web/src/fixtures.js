// Fixed equipment on a floor (conveyors, racks, machines, pallet stacks, offices), built from the
// `objects` of the `site` message. Everything is boxes; each floor draws them as a few instanced meshes.
import * as THREE from 'three';

const UNIT_BOX = new THREE.BoxGeometry(1, 1, 1);
const STEEL = 0x596579;
const DARK = 0x1f2733;
const BELT = 0x11161d;
const RACK_POST = 0x3b6ea5;
const RACK_BEAM = 0xdd6b20;
const WOOD = 0x8b6b43;
const CARDBOARD = [0xb08d5b, 0xa37e4e, 0xc19a6b, 0x8f7a5a];
const WRAPPED = 0x7fa6c9;
const MACHINE = [0x4a6078, 0x55707a, 0x5a5f7d];
const SAFETY_YELLOW = 0xecc94b;
const GLASS = 0x9fd8ff;
const LIGHT_OK = 0x68d391;
const SCREEN = 0x90cdf4;
const PARCEL_SPEED = 0.8; // metres per second along a conveyor

// Deterministic pseudo-random numbers from a string, so a rack looks the same on every load.
function seeded(text) {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return () => {
    h ^= h << 13; h ^= h >>> 17; h ^= h << 5;
    return ((h >>> 0) % 10000) / 10000;
  };
}

// Collects boxes in a fixture's own frame: u runs along its long side, v across, from its centre.
class Builder {
  constructor(centreX, centreZ, alongX) {
    this.centreX = centreX;
    this.centreZ = centreZ;
    this.alongX = alongX;
  }

  place(u, y, v, su, sy, sv) {
    return this.alongX
      ? { position: [this.centreX + u, y, this.centreZ + v], size: [su, sy, sv] }
      : { position: [this.centreX + v, y, this.centreZ + u], size: [sv, sy, su] };
  }
}

function conveyor(b, length, width, out) {
  out.solid.push({ ...b.place(0, 0.72, 0, length, 0.22, width), color: STEEL });
  out.solid.push({ ...b.place(0, 0.86, 0, length - 0.1, 0.08, width - 0.36), color: BELT });
  for (const side of [-1, 1]) {
    out.solid.push({ ...b.place(0, 0.95, side * (width / 2 - 0.07), length, 0.18, 0.08), color: SAFETY_YELLOW });
  }
  const legs = Math.max(2, Math.round(length / 3));
  for (let i = 0; i < legs; i++) {
    const u = -length / 2 + 0.3 + (i * (length - 0.6)) / (legs - 1);
    for (const side of [-1, 1]) out.solid.push({ ...b.place(u, 0.31, side * (width / 2 - 0.15), 0.12, 0.62, 0.12), color: DARK });
  }
  const parcels = Math.max(2, Math.floor(length / 3.5));
  for (let i = 0; i < parcels; i++) {
    out.parcels.push({ builder: b, length, offset: (i / parcels) * length, color: CARDBOARD[i % CARDBOARD.length], size: 0.45 + (i % 3) * 0.12 });
  }
}

function rack(b, length, width, out, random) {
  const height = 4;
  const bays = Math.max(1, Math.round(length / 2.7));
  const bay = length / bays;
  for (let i = 0; i <= bays; i++) {
    for (const side of [-1, 1]) {
      out.solid.push({ ...b.place(-length / 2 + i * bay, height / 2, side * (width / 2 - 0.05), 0.1, height, 0.1), color: RACK_POST });
    }
  }
  for (const level of [0.25, 1.55, 2.85]) {
    for (const side of [-1, 1]) out.solid.push({ ...b.place(0, level, side * (width / 2 - 0.05), length, 0.12, 0.08), color: RACK_BEAM });
    for (let i = 0; i < bays; i++) {
      let u = -length / 2 + i * bay + 0.25;
      const end = -length / 2 + (i + 1) * bay - 0.2;
      while (u < end - 0.6 && random() < 0.8) {
        const su = Math.min(0.7 + random() * 0.7, end - u);
        const sy = 0.5 + random() * 0.6;
        const color = random() < 0.2 ? WRAPPED : CARDBOARD[Math.floor(random() * CARDBOARD.length)];
        out.solid.push({ ...b.place(u + su / 2, level + 0.07 + sy / 2, 0, su, sy, width * 0.8), color });
        u += su + 0.12;
      }
    }
  }
}

function machine(b, length, width, out, random) {
  const color = MACHINE[Math.floor(random() * MACHINE.length)];
  out.solid.push({ ...b.place(0, 0.02, 0, length + 0.5, 0.04, width + 0.5), color: SAFETY_YELLOW });
  out.solid.push({ ...b.place(0, 0.85, 0, length, 1.6, width), color });
  out.solid.push({ ...b.place(-length * 0.12, 2.0, 0, length * 0.55, 0.7, width * 0.6), color: DARK });
  out.solid.push({ ...b.place(length * 0.3, 2.1, 0, 0.3, 0.9, 0.3), color: STEEL });
  out.solid.push({ ...b.place(length / 2 - 0.35, 1.25, width / 2 + 0.06, 0.6, 0.9, 0.12), color: DARK });
  out.glow.push({ ...b.place(length / 2 - 0.35, 1.4, width / 2 + 0.13, 0.4, 0.3, 0.02), color: SCREEN });
  out.glow.push({ ...b.place(length * 0.3, 2.65, 0, 0.22, 0.22, 0.22), color: LIGHT_OK });
}

function pallets(b, length, width, out, random) {
  const columns = Math.max(1, Math.floor(length / 1.5));
  const rows = Math.max(1, Math.floor(width / 1.3));
  for (let i = 0; i < columns; i++) {
    for (let j = 0; j < rows; j++) {
      const u = -length / 2 + (i + 0.5) * (length / columns);
      const v = -width / 2 + (j + 0.5) * (width / rows);
      out.solid.push({ ...b.place(u, 0.08, v, 1.2, 0.15, 1.0), color: WOOD });
      const layers = Math.floor(random() * 4); // some pallets are empty
      const color = random() < 0.3 ? WRAPPED : CARDBOARD[Math.floor(random() * CARDBOARD.length)];
      for (let k = 0; k < layers; k++) out.solid.push({ ...b.place(u, 0.45 + k * 0.6, v, 1.1, 0.58, 0.9), color });
    }
  }
}

function office(b, length, width, out) {
  const height = 2.6;
  out.solid.push({ ...b.place(0, 0.03, 0, length, 0.05, width), color: 0x2a3648 });
  for (const su of [-1, 1]) {
    for (const sv of [-1, 1]) out.solid.push({ ...b.place(su * length / 2, height / 2, sv * width / 2, 0.12, height, 0.12), color: STEEL });
    out.glass.push(b.place(su * length / 2, height / 2, 0, 0.06, height, width));
    out.glass.push(b.place(0, height / 2, su * width / 2, length, height, 0.06));
    out.solid.push({ ...b.place(0, height, su * width / 2, length, 0.1, 0.12), color: STEEL });
  }
  const desks = Math.max(1, Math.floor(length / 3));
  for (let i = 0; i < desks; i++) {
    const u = -length / 2 + (i + 0.5) * (length / desks);
    out.solid.push({ ...b.place(u, 0.72, -width / 4, 1.6, 0.08, 0.8), color: 0xa0aec0 });
    out.solid.push({ ...b.place(u, 0.36, -width / 4, 1.4, 0.7, 0.06), color: DARK });
    out.glow.push({ ...b.place(u, 1.05, -width / 4 - 0.2, 0.6, 0.38, 0.04), color: SCREEN });
  }
}

const BUILDERS = { conveyor, rack, machine, pallets, office };

function instanced(boxes, material) {
  const mesh = new THREE.InstancedMesh(UNIT_BOX, material, Math.max(boxes.length, 1));
  const helper = new THREE.Object3D();
  const color = new THREE.Color();
  boxes.forEach((box, i) => {
    helper.position.set(...box.position);
    helper.scale.set(...box.size);
    helper.updateMatrix();
    mesh.setMatrixAt(i, helper.matrix);
    if (box.color !== undefined) mesh.setColorAt(i, color.setHex(box.color));
  });
  mesh.count = boxes.length;
  mesh.frustumCulled = false;
  return mesh;
}

export class Fixtures {
  constructor(stage) {
    this.conveyors = []; // {mesh, parcels} per floor that has conveyors
    this.helper = new THREE.Object3D();
    stage.onFrame.push((dt, now) => this.update(now));
  }

  clear() {
    this.conveyors = [];
  }

  // Adds a floor's equipment to its group. `w`, `d` are the floor size in metres.
  build(group, floor, key) {
    const [w, d] = floor.size_m;
    const out = { solid: [], glow: [], glass: [], parcels: [] };
    for (const object of floor.objects || []) {
      const [x, y, ow, od] = object.rect;
      const alongX = ow >= od;
      const builder = new Builder(x + ow / 2 - w / 2, y + od / 2 - d / 2, alongX);
      const build = BUILDERS[object.type];
      if (build) build(builder, alongX ? ow : od, alongX ? od : ow, out, seeded(`${key}/${object.id}`));
    }
    if (out.solid.length) group.add(instanced(out.solid, new THREE.MeshStandardMaterial({ roughness: 0.8 })));
    if (out.glow.length) group.add(instanced(out.glow, new THREE.MeshBasicMaterial()));
    if (out.glass.length) {
      group.add(instanced(out.glass, new THREE.MeshStandardMaterial({ color: GLASS, transparent: true, opacity: 0.16, depthWrite: false })));
    }
    if (out.parcels.length) {
      const mesh = instanced(out.parcels.map((p) => ({ position: [0, 0, 0], size: [1, 1, 1], color: p.color })),
        new THREE.MeshStandardMaterial({ roughness: 0.9 }));
      group.add(mesh);
      this.conveyors.push({ mesh, parcels: out.parcels });
    }
  }

  // Parcels ride along their conveyor and wrap around.
  update(now) {
    const travelled = (now / 1000) * PARCEL_SPEED;
    for (const { mesh, parcels } of this.conveyors) {
      parcels.forEach((p, i) => {
        const span = p.length - 1;
        const u = -span / 2 + ((p.offset + travelled) % span);
        const box = p.builder.place(u, 0.9 + p.size / 2, 0, p.size * 1.3, p.size, p.size);
        this.helper.position.set(...box.position);
        this.helper.scale.set(...box.size);
        this.helper.updateMatrix();
        mesh.setMatrixAt(i, this.helper.matrix);
      });
      mesh.instanceMatrix.needsUpdate = true;
    }
  }
}

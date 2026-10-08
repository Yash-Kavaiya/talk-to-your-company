// Entry point: wires the WebSocket messages to the twin, tracks, events, HUD and voice.
import * as THREE from 'three';
import { Stage } from './scene.js';
import { Twin } from './twin.js';
import { Fixtures } from './fixtures.js';
import { Tracks } from './tracks.js';
import { Events } from './events.js';
import { Voice } from './voice.js';
import { Link } from './ws.js';
import { onLinkStatus, onMetrics } from './hud.js';
import { CameraView } from './camera.js';

const canvas = document.getElementById('scene');
const stage = new Stage(canvas);
const twin = new Twin(stage, new Fixtures(stage));
const tracks = new Tracks(stage, twin);
const events = new Events(stage, twin);
const link = new Link(onLinkStatus);
const voice = new Voice(link);
const camera = new CameraView(twin);
const navItems = document.getElementById('nav-items');

function markActive(plant, floor) {
  for (const button of navItems.querySelectorAll('button')) {
    button.classList.toggle('active', button.dataset.plant === (plant || '') && button.dataset.floor === (floor || ''));
  }
}

function focus(plant, floor) {
  if (plant && floor) twin.focusFloor(plant, floor);
  else if (plant) twin.focusPlant(plant);
  else twin.overview();
  camera.show(plant, floor);
  markActive(plant, floor);
}

function navButton(label, plant, floor) {
  const button = document.createElement('button');
  button.textContent = label;
  button.dataset.plant = plant || '';
  button.dataset.floor = floor || '';
  button.addEventListener('click', () => focus(plant, floor));
  return button;
}

function buildNav(site) {
  const rows = [navButton('Overview')];
  for (const plant of site.plants) {
    const row = document.createElement('div');
    row.className = 'row';
    row.append(navButton(plant.name, plant.id), ...plant.floors.map((f) => navButton(f.id, plant.id, f.id)));
    rows.push(row);
  }
  navItems.replaceChildren(...rows);
}

link.on('site', ({ site }) => {
  events.clear();
  twin.build(site);
  tracks.rebuild();
  buildNav(site);
  focus();
});
link.on('state', (state) => tracks.onState(state));
link.on('event', ({ event }) => events.add(event));
link.on('metrics', onMetrics);
link.on('transcript', (m) => voice.onTranscript(m));
link.on('answer', (m) => voice.onAnswer(m));
link.on('audio', (m) => voice.onAudio(m));
link.on('ui', (ui) => {
  if (ui.action === 'focus') focus(ui.plant, ui.floor);
  if (ui.action === 'highlight') events.highlight(ui.event_ids);
  if (ui.action === 'panel' && ui.content) {
    if (ui.plant && ui.floor) focus(ui.plant, ui.floor);
    if (ui.content.kind === 'report') events.showReport(ui.content.report, ui.content.event);
    else if (ui.content.kind === 'person') events.showPerson(ui.content.person, ui.content.event);
    else events.showEvent(ui.content.event);
  }
});

// Click picking: an event marker opens its panel; a floor selects its plant, then flies to the floor.
const raycaster = new THREE.Raycaster();
let down = null;
canvas.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY }; });
canvas.addEventListener('pointerup', (e) => {
  if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return; // it was a drag
  const point = new THREE.Vector2((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  raycaster.setFromCamera(point, stage.camera);
  const marker = raycaster.intersectObjects(events.hitTargets())[0];
  if (marker) {
    link.send({ type: 'select_event', event_id: marker.object.userData.eventId });
    return;
  }
  const slab = raycaster.intersectObjects(twin.slabs())[0];
  if (!slab) return;
  const { plant, floor } = slab.object.userData;
  if (twin.selected === plant) focus(plant, floor);
  else focus(plant);
});
addEventListener('keydown', (e) => { if (e.code === 'Escape') focus(); });

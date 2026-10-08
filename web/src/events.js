// Event markers (pulsing, clickable) and the side panel for event details and incident reports.
import * as THREE from 'three';
import { COLORS } from './scene.js';
import { zoneKey } from './twin.js';

const KEEP_MS = 10 * 60 * 1000; // markers stay as long as an event counts as open
const NEW_MS = 12 * 1000; // fast pulse while the event is new
const HIGHLIGHT_MS = 12 * 1000;
const TYPE_NAMES = { near_miss: 'Near miss', restricted_zone: 'Restricted zone', no_helmet: 'No helmet', crowding: 'Crowding' };
const SEVERITY = { 1: 'low', 2: 'medium', 3: 'high' };

const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const clock = (ts) => new Date(ts * 1000).toLocaleTimeString();

export class Events {
  constructor(stage, twin) {
    this.twin = twin;
    this.markers = new Map(); // event id -> {event, group, ring, ball, hit, born, highlightUntil}
    this.panel = document.getElementById('panel');
    this.body = document.getElementById('panel-body');
    document.getElementById('panel-close').addEventListener('click', () => { this.panel.hidden = true; });
    stage.onFrame.push((dt, now) => this.update(now));
  }

  clear() {
    for (const marker of this.markers.values()) marker.group.removeFromParent();
    this.markers.clear();
  }

  add(event) {
    const key = zoneKey(event.plant, event.floor);
    const floor = this.twin.floors.get(key);
    if (!floor || this.markers.has(event.id)) return;
    const age = Date.now() - event.ts * 1000;
    if (age > KEEP_MS) return;
    const group = new THREE.Group();
    group.position.copy(this.twin.toLocal(key, event.x, event.y));
    const ball = new THREE.Mesh(
      new THREE.SphereGeometry(0.55, 16, 12),
      new THREE.MeshBasicMaterial({ color: COLORS.event, depthTest: false, transparent: true }),
    );
    ball.position.y = 3;
    ball.renderOrder = 2;
    const stem = new THREE.Mesh(
      new THREE.CylinderGeometry(0.06, 0.06, 3, 6),
      new THREE.MeshBasicMaterial({ color: COLORS.event, depthTest: false, transparent: true }),
    );
    stem.position.y = 1.5;
    stem.renderOrder = 2;
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.9, 1.15, 32),
      new THREE.MeshBasicMaterial({ color: COLORS.event, transparent: true, side: THREE.DoubleSide, depthTest: false }),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.06;
    ring.renderOrder = 2;
    const hit = new THREE.Mesh(new THREE.SphereGeometry(1.6, 8, 6), new THREE.MeshBasicMaterial({ visible: false }));
    hit.position.y = 2.4;
    hit.userData = { eventId: event.id };
    group.add(ball, stem, ring, hit);
    floor.group.add(group);
    this.markers.set(event.id, { event, group, ring, ball, hit, born: performance.now() - age, highlightUntil: 0 });
  }

  highlight(ids) {
    const until = performance.now() + HIGHLIGHT_MS;
    for (const marker of this.markers.values()) marker.highlightUntil = 0;
    for (const id of ids) {
      const marker = this.markers.get(id);
      if (marker) marker.highlightUntil = until;
    }
  }

  hitTargets() {
    return [...this.markers.values()].map((m) => m.hit);
  }

  update(now) {
    for (const [id, m] of this.markers) {
      const age = now - m.born;
      if (age > KEEP_MS) {
        m.group.removeFromParent();
        this.markers.delete(id);
        continue;
      }
      const highlighted = now < m.highlightUntil;
      const period = age < NEW_MS || highlighted ? 700 : 2400;
      const phase = (now % period) / period;
      m.ring.scale.setScalar(1 + phase * (highlighted ? 3.2 : 1.8));
      m.ring.material.opacity = 1 - phase;
      m.ball.scale.setScalar(highlighted ? 1.9 : 1);
      m.ball.material.color.setHex(highlighted ? 0xffffff : COLORS.event);
    }
  }

  // ---- side panel ----

  where(event) {
    const plant = this.twin.plants.get(event.plant);
    return `${plant ? plant.name : event.plant}, floor ${event.floor} · ${event.camera_id}`;
  }

  showEvent(event) {
    const snapshot = event.snapshot_path
      ? `<img src="${escapeHtml(event.snapshot_path)}" alt="Camera snapshot at the time of the event">` : '';
    this.body.innerHTML = `
      <h3>${TYPE_NAMES[event.type] || escapeHtml(event.type)}</h3>
      <span class="badge">event ${event.id} · ${SEVERITY[event.severity]} severity</span>
      ${snapshot}
      <dl>
        <dt>Time</dt><dd>${clock(event.ts)}</dd>
        <dt>Location</dt><dd>${escapeHtml(this.where(event))}<br>${event.x.toFixed(1)} m, ${event.y.toFixed(1)} m</dd>
      </dl>
      <p class="summary">${escapeHtml(event.summary)}</p>`;
    this.panel.hidden = false;
  }

  // Who someone is (badge feed), with the timing of the incident and their recent history.
  showPerson(person, event) {
    const e = person.employee;
    const incident = person.incident;
    const row = (label, value) => (value ? `<dt>${label}</dt><dd>${escapeHtml(value)}</dd>` : '');
    const snapshot = event && event.snapshot_path
      ? `<img src="${escapeHtml(event.snapshot_path)}" alt="Camera snapshot at the time of the event">` : '';
    let timing = '';
    if (incident) {
      const stay = incident.seconds_in_zone === null ? '' : `${incident.seconds_in_zone} s${incident.still_inside ? ' so far' : ''}`;
      timing = `
        <h4>${TYPE_NAMES[incident.type] || escapeHtml(incident.type)} · event ${incident.id}</h4>
        <dl>
          ${row('Where', `${incident.plant_name}, floor ${incident.floor}${incident.zone ? `, zone ${incident.zone}` : ''}`)}
          ${row('Authorised', incident.authorised === null ? '' : (incident.authorised ? 'Yes' : 'No, not for this zone'))}
          ${row('Entered zone', incident.entered_at)}
          ${row('Alert raised', incident.time)}
          ${row('Left zone', incident.still_inside ? 'Still inside' : incident.left_at)}
          ${row('Time in zone', stay)}
        </dl>`;
    }
    const now = person.now ? `${person.now.plant_name}, floor ${person.now.floor} (${person.now.x} m, ${person.now.y} m)` : 'Not on any camera';
    const history = person.recent_incidents
      .map((i) => `<li>${escapeHtml(i.time)} · ${TYPE_NAMES[i.type] || escapeHtml(i.type)} · ${escapeHtml(i.plant_name)}, ${escapeHtml(i.floor)}</li>`).join('');
    this.body.innerHTML = `
      <h3>${escapeHtml(e.name)}</h3>
      <span class="badge">${escapeHtml(e.id)} · ${escapeHtml(e.role)}</span>
      ${snapshot}
      <dl>
        ${row('Department', e.department)}
        ${row('Shift', e.shift)}
        ${row('Supervisor', e.supervisor)}
        ${row('Training', e.certifications.join(', '))}
        ${row('May enter', e.authorised_zones.join(', ') || 'No restricted zones')}
        ${row('Now', now)}
        ${row('On camera since', person.on_camera_since)}
      </dl>
      ${timing}
      <h4>Other incidents, last 24 h: ${person.other_incidents_24h}</h4>
      ${history ? `<ul>${history}</ul>` : ''}
      <p class="note">${escapeHtml(person.source)}</p>`;
    this.panel.hidden = false;
  }

  showReport(report, event) {
    const rows = ['what', 'where', 'when', 'who', 'severity', 'action']
      .map((k) => `<dt>${k[0].toUpperCase() + k.slice(1)}</dt><dd>${escapeHtml(report[k])}</dd>`).join('');
    const snapshot = event && event.snapshot_path
      ? `<img src="${escapeHtml(event.snapshot_path)}" alt="Camera snapshot at the time of the event">` : '';
    this.body.innerHTML = `
      <h3>Incident report</h3>
      <span class="badge">event ${report.event_id}</span>
      ${snapshot}
      <dl>${rows}</dl>`;
    this.panel.hidden = false;
  }
}

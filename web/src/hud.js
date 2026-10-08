// HUD: per-stream fps, last voice latency, GPU and memory. The "nothing leaves the device" line is in index.html.

const fpsBox = document.getElementById('hud-fps');
const latency = document.getElementById('hud-latency');
const gpu = document.getElementById('hud-gpu');
const memory = document.getElementById('hud-mem');
const link = document.getElementById('link');

const value = (v, format) => (v === null || v === undefined ? 'n/a' : format(v));

export function onMetrics(metrics) {
  fpsBox.replaceChildren(...Object.entries(metrics.fps).map(([camera, fps]) => {
    const row = document.createElement('div');
    const name = document.createElement('span');
    const number = document.createElement('span');
    name.textContent = camera.replace(/^cam_/, '');
    number.textContent = `${fps.toFixed(1)} fps`;
    row.append(name, number);
    return row;
  }));
  latency.textContent = value(metrics.voice_latency_ms, (v) => `${(v / 1000).toFixed(2)} s`);
  gpu.textContent = value(metrics.gpu_pct, (v) => `${v.toFixed(0)} %`);
  memory.textContent = value(metrics.mem_gb, (v) => `${v.toFixed(1)} GB`);
}

export function onLinkStatus(connected) {
  link.classList.toggle('on', connected);
  link.title = connected ? 'connected' : 'reconnecting';
}

// Flowing waveform in the voice bar. Its height follows the live audio level (microphone or spoken answer).

const canvas = document.getElementById('wave');
const ctx = canvas.getContext('2d');
const css = getComputedStyle(document.documentElement);
const COLOURS = { idle: '--muted', listening: '--event', thinking: '--accent', speaking: '--accent' };
const LAYERS = [
  { cycles: 1.6, speed: 2.4, gain: 1.0, alpha: 1.0, width: 2 },
  { cycles: 2.3, speed: -1.8, gain: 0.7, alpha: 0.45, width: 1.5 },
  { cycles: 3.1, speed: 3.3, gain: 0.45, alpha: 0.25, width: 1 },
];
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');

export class Wave {
  constructor() {
    this.analyser = null; // set by Voice once the AudioContext exists
    this.samples = null;
    this.state = 'idle';
    this.level = 0; // 0..1, smoothed
    this.frame = 0;
    this.tick = this.tick.bind(this);
    addEventListener('resize', () => this.set(this.state));
    this.set('idle');
  }

  set(state) {
    this.state = state in COLOURS ? state : 'idle';
    if (!this.frame) this.frame = requestAnimationFrame(this.tick);
  }

  // Loudness of what the analyser hears right now, 0..1.
  loudness() {
    if (!this.analyser) return 0;
    if (!this.samples) this.samples = new Float32Array(this.analyser.fftSize);
    this.analyser.getFloatTimeDomainData(this.samples);
    let sum = 0;
    for (const s of this.samples) sum += s * s;
    return Math.min(1, Math.sqrt(sum / this.samples.length) * 8);
  }

  target(seconds) {
    if (reducedMotion.matches || this.state === 'idle') return 0;
    if (this.state === 'thinking') return 0.55 + 0.2 * Math.sin(seconds * 3);
    return Math.min(1, 0.15 + this.loudness());
  }

  tick(now) {
    const seconds = now / 1000;
    this.level += (this.target(seconds) - this.level) * 0.18;
    this.draw(seconds);
    // Keep running until the wave has settled back to a flat line.
    this.frame = this.state !== 'idle' && !reducedMotion.matches || this.level > 0.005
      ? requestAnimationFrame(this.tick) : 0;
  }

  draw(seconds) {
    const ratio = devicePixelRatio || 1;
    const width = Math.round(canvas.clientWidth * ratio);
    const height = Math.round(canvas.clientHeight * ratio);
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = ctx.shadowColor = css.getPropertyValue(COLOURS[this.state]).trim();
    ctx.shadowBlur = 8 * ratio * this.level; // soft glow that grows with the level
    const mid = height / 2;
    const peak = (mid - 2 * ratio) * this.level;
    for (const layer of LAYERS) {
      ctx.globalAlpha = layer.alpha;
      ctx.lineWidth = layer.width * ratio;
      ctx.beginPath();
      for (let x = 0; x <= width; x += 2) {
        const u = x / width;
        const taper = (1 - (2 * u - 1) ** 2) ** 2; // pinned at both ends
        const y = mid + peak * layer.gain * taper * Math.sin(u * layer.cycles * 2 * Math.PI + seconds * layer.speed);
        if (x) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      }
      ctx.stroke();
    }
  }
}

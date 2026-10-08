// Push-to-talk capture (button or space bar), the text box, and queued playback of spoken answers.

import { Wave } from './wave.js';

const TARGET_RATE = 16000;
const talk = document.getElementById('talk');
const talkLabel = document.getElementById('talk-label');
const orb = document.getElementById('orb');
const form = document.getElementById('ask');
const input = document.getElementById('text');
const transcript = document.getElementById('transcript');
const answer = document.getElementById('answer');

export class Voice {
  constructor(link) {
    this.link = link;
    this.audio = null; // AudioContext, created on the first user gesture
    this.wave = new Wave();
    this.recorder = null;
    this.chunks = [];
    this.playQueue = Promise.resolve();
    this.playAt = 0;
    this.answerOpen = false;

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      this.ensureAudio();
      if (this.link.send({ type: 'text_query', text })) {
        input.value = '';
        this.setOrb('thinking');
      }
    });

    if (!navigator.mediaDevices || !window.MediaRecorder) {
      talk.disabled = true;
      talk.title = 'Microphone unavailable here (needs HTTPS or localhost). Use the text box.';
      talkLabel.textContent = 'No microphone';
      return;
    }
    talk.addEventListener('pointerdown', (e) => { e.preventDefault(); this.start(); });
    for (const type of ['pointerup', 'pointerleave', 'pointercancel']) talk.addEventListener(type, () => this.stop());
    addEventListener('keydown', (e) => {
      if (e.code === 'Space' && !e.repeat && document.activeElement !== input) { e.preventDefault(); this.start(); }
    });
    addEventListener('keyup', (e) => {
      if (e.code === 'Space' && document.activeElement !== input) { e.preventDefault(); this.stop(); }
    });
  }

  ensureAudio() {
    if (!this.audio) {
      this.audio = new AudioContext();
      this.wave.analyser = this.audio.createAnalyser(); // hears the microphone and the spoken answer
    }
    if (this.audio.state === 'suspended') this.audio.resume();
  }

  setOrb(state) {
    orb.className = state;
    this.wave.set(state);
    talkLabel.textContent = { listening: 'Listening…', thinking: 'Thinking…', speaking: 'Speaking…' }[state] || 'Hold to talk';
  }

  async start() {
    if (this.recorder) return;
    this.ensureAudio();
    this.recorder = 'starting';
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      this.recorder = null;
      talkLabel.textContent = 'Microphone blocked';
      return;
    }
    const recorder = new MediaRecorder(stream);
    const mic = this.audio.createMediaStreamSource(stream);
    mic.connect(this.wave.analyser);
    this.chunks = [];
    recorder.ondataavailable = (e) => this.chunks.push(e.data);
    recorder.onstop = () => {
      mic.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      this.sendRecording(new Blob(this.chunks, { type: recorder.mimeType }));
    };
    recorder.start();
    this.setOrb('listening');
    if (this.recorder === 'stopping') { this.recorder = recorder; this.stop(); } else this.recorder = recorder;
  }

  stop() {
    if (!this.recorder) return;
    if (typeof this.recorder === 'string') { this.recorder = 'stopping'; return; } // released before the mic opened
    this.recorder.stop();
    this.recorder = null;
    this.setOrb('thinking');
  }

  async sendRecording(blob) {
    try {
      const decoded = await this.audio.decodeAudioData(await blob.arrayBuffer());
      if (decoded.duration < 0.25) { this.setOrb('idle'); return; }
      const wav = encodeWav(await resample(decoded));
      if (!this.link.send({ type: 'audio_query', wav_b64: toBase64(wav) })) this.setOrb('idle');
    } catch (error) {
      console.error('could not encode the recording', error);
      this.setOrb('idle');
    }
  }

  // ---- server messages ----

  onTranscript(message) {
    transcript.textContent = message.text;
    answer.textContent = '';
    this.answerOpen = true;
  }

  onAnswer(message) {
    if (!this.answerOpen) answer.textContent = '';
    this.answerOpen = !message.done;
    answer.textContent += (answer.textContent ? ' ' : '') + message.text;
    if (message.done && orb.className === 'thinking') this.setOrb('idle');
  }

  // Chunks arrive in `seq` order; each is scheduled right after the previous one ends.
  onAudio(message) {
    if (!this.audio || !message.wav_b64) {
      if (message.last) this.setOrb('idle');
      return;
    }
    this.playQueue = this.playQueue.then(async () => {
      const buffer = await this.audio.decodeAudioData(fromBase64(message.wav_b64));
      const source = this.audio.createBufferSource();
      source.buffer = buffer;
      source.connect(this.audio.destination);
      source.connect(this.wave.analyser);
      const at = Math.max(this.audio.currentTime, this.playAt);
      this.playAt = at + buffer.duration;
      source.start(at);
      this.setOrb('speaking');
      if (message.last) source.onended = () => this.setOrb('idle');
    }).catch((error) => {
      console.error('audio playback failed', error);
      this.setOrb('idle');
    });
  }
}

async function resample(buffer) {
  const frames = Math.ceil(buffer.duration * TARGET_RATE);
  const offline = new OfflineAudioContext(1, frames, TARGET_RATE);
  const source = offline.createBufferSource();
  source.buffer = buffer;
  source.connect(offline.destination);
  source.start();
  return (await offline.startRendering()).getChannelData(0);
}

// Mono 16-bit PCM WAV.
function encodeWav(samples) {
  const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
  const text = (offset, s) => { for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i)); };
  text(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, 'WAVEfmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, TARGET_RATE, true);
  view.setUint32(28, TARGET_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Uint8Array(view.buffer);
}

function toBase64(bytes) {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

function fromBase64(text) {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

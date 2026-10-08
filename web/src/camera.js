// Live camera view of the focused floor: polls /api/camera and swaps the picture once it has loaded.
// This browser can also feed the floor's camera, from its webcam or from a recording (a video file):
// frames are sent to the server, which detects and tracks on them like on any other camera.
import { zoneKey } from './twin.js';

const REFRESH_MS = 250;
const SEND_MS = 120; // pause between shared frames; the server's detector sets the real pace
const figure = document.getElementById('camera');
const image = document.getElementById('camera-image');
const title = document.getElementById('camera-title');
const shareWebcam = document.getElementById('camera-share');
const shareRecording = document.getElementById('camera-record');
const stop = document.getElementById('camera-stop');
const filePicker = document.getElementById('camera-file');

export class CameraView {
  constructor(twin) {
    this.twin = twin;
    this.url = null; // null while no floor is focused
    this.timer = null;
    this.sharing = null; // {url, video, canvas, release} while this browser feeds a camera
    shareWebcam.hidden = !navigator.mediaDevices;
    shareWebcam.addEventListener('click', () => this.shareWebcam());
    shareRecording.addEventListener('click', () => filePicker.click());
    filePicker.addEventListener('change', () => {
      if (filePicker.files.length) this.shareRecording(filePicker.files[0]);
      filePicker.value = '';
    });
    stop.addEventListener('click', () => this.stopSharing());
  }

  // Show the camera of one floor; anything else (a plant, the overview) hides the view.
  show(plant, floor) {
    const entry = plant && floor ? this.twin.floors.get(zoneKey(plant, floor)) : null;
    clearTimeout(this.timer);
    this.url = entry ? `/api/camera/${encodeURIComponent(plant)}/${encodeURIComponent(floor)}` : null;
    figure.hidden = !entry;
    document.body.classList.toggle('has-camera', Boolean(entry));
    if (!entry) return;
    title.textContent = `${entry.camera} · ${floor}`;
    title.title = `${entry.camera} · ${this.twin.plants.get(plant).name}, floor ${floor}`;
    this.refresh(this.url);
  }

  refresh(url) {
    if (this.url !== url) return; // the focus moved on
    const next = new Image();
    const again = () => { this.timer = setTimeout(() => this.refresh(url), REFRESH_MS); };
    next.onload = () => {
      if (this.url === url) {
        image.src = next.src;
        figure.classList.remove('empty');
      }
      again();
    };
    next.onerror = () => {
      if (this.url === url) figure.classList.add('empty'); // no picture: nothing feeds this camera yet
      again();
    };
    next.src = `${url}?t=${Date.now()}`;
  }

  // ---- feeding the focused floor's camera from this browser ----

  async shareWebcam() {
    const url = this.url;
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 }, audio: false });
    } catch (error) {
      shareWebcam.textContent = 'Webcam blocked';
      return;
    }
    const video = document.createElement('video');
    video.srcObject = stream;
    this.startSharing(url, video, () => stream.getTracks().forEach((track) => track.stop()));
  }

  shareRecording(file) {
    const video = document.createElement('video');
    const source = URL.createObjectURL(file);
    video.src = source;
    video.loop = true;
    this.startSharing(this.url, video, () => {
      video.pause();
      URL.revokeObjectURL(source);
    });
  }

  async startSharing(url, video, release) {
    this.stopSharing();
    video.muted = true;
    video.playsInline = true;
    try {
      await video.play();
    } catch (error) {
      release();
      shareRecording.textContent = 'Cannot play that file';
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = 1280;
    canvas.height = 720;
    this.sharing = { url: `${url}/frame`, video, canvas, release };
    shareWebcam.hidden = true;
    shareRecording.hidden = true;
    stop.hidden = false;
    this.sendFrame(this.sharing);
  }

  stopSharing() {
    if (!this.sharing) return;
    this.sharing.release();
    this.sharing = null;
    shareWebcam.hidden = !navigator.mediaDevices;
    shareRecording.hidden = false;
    shareRecording.textContent = 'Share recording';
    stop.hidden = true;
  }

  // One frame at a time: the next is taken only after the server accepted the last.
  sendFrame(session) {
    if (this.sharing !== session) return;
    session.canvas.getContext('2d').drawImage(session.video, 0, 0, 1280, 720);
    session.canvas.toBlob(async (blob) => {
      try {
        if (blob) await fetch(session.url, { method: 'POST', body: blob, headers: { 'Content-Type': 'image/jpeg' } });
      } catch (error) {
        // the server is restarting; keep trying
      }
      setTimeout(() => this.sendFrame(session), SEND_MS);
    }, 'image/jpeg', 0.75);
  }
}

"""Real perception: ingest threads -> one batched detector -> tracker and mapper per stream."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from app.config import Site, zone_key
from app.perception.base import Track
from app.perception.detector import Detector
from app.perception.ingest import PushStream, Source, open_source
from app.perception.mapper import FloorMapper
from app.perception.tracker import ByteTracker

log = logging.getLogger(__name__)

TARGET_FPS = 10.0
HELMET_CHECK_EVERY_S = 3.0
MIN_CROP_HEIGHT_PX = 80
VELOCITY_SMOOTHING = 0.5
BOX_BGR = {"person": (197, 209, 79), "forklift": (85, 173, 246), "vehicle": (192, 174, 160)}
ID_BLOCK = 100_000  # track ids are unique across streams: stream index * ID_BLOCK + local id


class RealPerception:
    def __init__(self, site: Site, models_dir: Path, videos_dir: Path, detector: Optional[Any] = None) -> None:
        self.site = site
        self._keys: list[str] = []
        self._streams: dict[str, Source] = {}
        self._shared: dict[str, PushStream] = {}
        self._trackers: dict[str, ByteTracker] = {}
        self._mappers: dict[str, FloorMapper] = {}
        for plant, floor in site.floors():
            key = zone_key(plant.id, floor.id)
            if floor.camera.homography is None:
                raise ValueError(f"camera {floor.camera.id} has no homography (run scripts/calibrate.py)")
            self._keys.append(key)
            self._streams[key] = open_source(floor.camera, videos_dir)
            # frames shared from a browser (webcam or a recording) take over the camera while they are fresh
            stream = self._streams[key]
            self._shared[key] = stream if isinstance(stream, PushStream) else PushStream(floor.camera.id)
            self._trackers[key] = ByteTracker()
            self._mappers[key] = FloorMapper(floor.camera.homography, floor.size_m)
        self._detector = detector or Detector(models_dir)
        self._lock = threading.Lock()
        self._tracks: dict[str, list[Track]] = {key: [] for key in self._keys}
        self._stamps: dict[str, list[float]] = {key: [] for key in self._keys}
        self._helmet: dict[int, bool] = {}
        self._running = False
        self._threads: list[threading.Thread] = []
        # set by app.backends when a vision model is loaded: JPEG of a person crop -> wearing a helmet?
        self.helmet_check: Optional[Callable[[bytes], Optional[bool]]] = None

    # ---- Perception interface ----

    def start(self) -> None:
        self._running = True
        for stream in self._streams.values():
            stream.start()
        self._threads = [threading.Thread(target=self._detect_loop, daemon=True, name="detect"),
                         threading.Thread(target=self._helmet_loop, daemon=True, name="helmet")]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self._running = False
        for stream in self._streams.values():
            stream.stop()

    def tracks(self) -> dict[str, list[Track]]:
        with self._lock:
            return {key: list(tracks) for key, tracks in self._tracks.items()}

    def fps(self) -> dict[str, float]:
        now = time.monotonic()
        with self._lock:
            return {self._streams[key].camera_id: round(sum(now - t <= 2.0 for t in stamps) / 2.0, 1)
                    for key, stamps in self._stamps.items()}

    def push_frame(self, zone: str, jpeg: bytes) -> bool:
        shared = self._shared.get(zone)
        return shared is not None and shared.push(jpeg)

    def _latest(self, zone: str) -> Optional[Any]:
        """The frame to use for a floor: a freshly shared one if there is one, else the camera's own."""
        shared = self._shared.get(zone)
        frame = shared.latest() if shared else None
        if frame is None and zone in self._streams:
            frame = self._streams[zone].latest()
        return frame

    def frame_jpeg(self, zone: str) -> Optional[bytes]:
        frame = self._latest(zone)
        return _jpeg(frame) if frame is not None else None

    def view(self, zone: str) -> Optional[tuple[bytes, str]]:
        return self._annotated(zone, None, 70)

    def snapshot(self, zone: str, track_ids: list[int]) -> Optional[tuple[bytes, str]]:
        return self._annotated(zone, set(track_ids), 85)

    def _annotated(self, zone: str, marked: Optional[set[int]], quality: int) -> Optional[tuple[bytes, str]]:
        """The latest frame with boxes: every track in its class colour, or only `marked` ones in red."""
        import cv2

        frame = self._latest(zone)
        if frame is None:
            return None
        frame = frame.copy()
        with self._lock:
            tracks = [t for t in self._tracks.get(zone, []) if t.bbox and (marked is None or t.id in marked)]
        for t in tracks:
            x1, y1, x2, y2 = (int(v) for v in t.bbox)
            colour = (60, 60, 240) if marked is not None else BOX_BGR[t.cls]
            cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 3 if marked is not None else 2)
            if marked is None:
                cv2.putText(frame, f"{t.cls} {t.id % ID_BLOCK}", (x1, max(y1 - 6, 14)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, colour, 2)
        return _jpeg(frame, quality), "jpg"

    # ---- threads ----

    def _detect_loop(self) -> None:
        interval = 1.0 / TARGET_FPS
        previous: dict[int, tuple[float, float, float, float, float]] = {}  # id -> x, y, vx, vy, time
        while self._running:
            started = time.monotonic()
            ready = [(key, frame) for key in self._keys if (frame := self._latest(key)) is not None]
            live = {key for key, _ in ready}
            with self._lock:
                for key in self._keys:
                    if key not in live:
                        self._tracks[key] = []  # a camera without a picture has nothing to report
            if ready:
                try:
                    batches = self._detector.detect([frame for _, frame in ready])
                except Exception:
                    log.exception("detector failed on a batch")
                    batches = [[] for _ in ready]
                now = time.time()
                for (key, _), detections in zip(ready, batches):
                    tracks = self._to_tracks(key, detections, now, previous)
                    with self._lock:
                        self._tracks[key] = tracks
                        self._stamps[key] = [t for t in self._stamps[key] if started - t <= 2.0] + [started]
                previous = {i: p for i, p in previous.items() if now - p[4] < 5.0}
            delay = interval - (time.monotonic() - started)
            if delay > 0:
                time.sleep(delay)

    def _to_tracks(self, key: str, detections: list, now: float,
                   previous: dict[int, tuple[float, float, float, float, float]]) -> list[Track]:
        offset = self._keys.index(key) * ID_BLOCK
        tracks = []
        for tracklet in self._trackers[key].update(detections):
            track_id = offset + tracklet.id
            x, y = self._mappers[key].to_floor(tracklet.bbox)
            vx = vy = 0.0
            if track_id in previous:
                px, py, pvx, pvy, pt = previous[track_id]
                dt = max(now - pt, 1e-3)
                vx = VELOCITY_SMOOTHING * pvx + (1 - VELOCITY_SMOOTHING) * (x - px) / dt
                vy = VELOCITY_SMOOTHING * pvy + (1 - VELOCITY_SMOOTHING) * (y - py) / dt
            previous[track_id] = (x, y, vx, vy, now)
            tracks.append(Track(id=track_id, zone=key, cls=tracklet.cls, x=x, y=y, vx=vx, vy=vy,
                                bbox=tracklet.bbox, last_seen=now, helmet=self._helmet.get(track_id)))
        return tracks

    def _helmet_loop(self) -> None:
        """Every few seconds ask the vision model about one person who has not been checked yet (spec Q2)."""
        while self._running:
            time.sleep(HELMET_CHECK_EVERY_S)
            if self.helmet_check is None:
                continue
            target = self._unchecked_person()
            if target is None:
                continue
            key, track = target
            frame = self._latest(key)
            if frame is None:
                continue
            x1, y1, x2, y2 = (int(max(v, 0)) for v in track.bbox)
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            try:
                wearing = self.helmet_check(_jpeg(crop))
            except Exception:
                log.exception("helmet check failed")
                continue
            if wearing is not None:
                self._helmet[track.id] = wearing

    def _unchecked_person(self) -> Optional[tuple[str, Track]]:
        with self._lock:
            live = {t.id for tracks in self._tracks.values() for t in tracks}
            self._helmet = {i: v for i, v in self._helmet.items() if i in live}
            for key, tracks in self._tracks.items():
                for t in tracks:
                    if (t.cls == "person" and t.id not in self._helmet and t.bbox
                            and t.bbox[3] - t.bbox[1] >= MIN_CROP_HEIGHT_PX):
                        return key, t
        return None


def _jpeg(frame: Any, quality: int = 85) -> bytes:
    import cv2

    ok, data = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return data.tobytes()

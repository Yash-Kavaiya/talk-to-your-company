"""Camera sources (plan section 7): looping video files, a webcam on this machine, or frames pushed
from a browser's webcam. All of them expose `latest()`, `start()` and `stop()`."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional, Union

from app.config import Camera, resolve_video

log = logging.getLogger(__name__)

SIZE = (1280, 720)
STALE_AFTER_S = 2.0  # a pushed frame older than this is not "live" any more
GST_PIPELINE = (
    "filesrc location={path} ! qtdemux ! h264parse ! nvv4l2decoder ! nvvidconv ! "
    "video/x-raw,format=BGRx,width=1280,height=720 ! videoconvert ! video/x-raw,format=BGR ! "
    "appsink drop=true max-buffers=1 sync=false"
)


def _fit(frame: Any) -> Any:
    import cv2

    return frame if (frame.shape[1], frame.shape[0]) == SIZE else cv2.resize(frame, SIZE)


class VideoStream(threading.Thread):
    """Reads one video file in a loop at its own frame rate and keeps only the latest frame."""

    def __init__(self, camera_id: str, path: str) -> None:
        super().__init__(daemon=True, name=f"ingest-{camera_id}")
        if not Path(path).is_file():
            raise FileNotFoundError(f"video for {camera_id} not found: {path}")
        self.camera_id = camera_id
        self.path = path
        self._lock = threading.Lock()
        self._frame: Optional[Any] = None
        self._running = True
        self._hardware = True  # cleared the first time the GStreamer pipeline fails to open
        self._capture = self._open()

    def _open(self) -> Any:
        import cv2

        if self._hardware:
            capture = cv2.VideoCapture(GST_PIPELINE.format(path=self.path), cv2.CAP_GSTREAMER)
            if capture.isOpened():
                return capture
            self._hardware = False
            log.warning("%s: GStreamer hardware decode unavailable, using OpenCV software decode", self.camera_id)
        capture = cv2.VideoCapture(self.path)
        if not capture.isOpened():
            raise RuntimeError(f"cannot open video {self.path}")
        return capture

    def run(self) -> None:
        import cv2

        fps = self._capture.get(cv2.CAP_PROP_FPS)
        interval = 1.0 / fps if 1 <= fps <= 120 else 1.0 / 25
        next_at = time.monotonic()
        while self._running:
            ok, frame = self._capture.read()
            if not ok:  # end of file: loop
                self._capture.release()
                self._capture = self._open()
                continue
            frame = _fit(frame)
            with self._lock:
                self._frame = frame
            next_at += interval
            delay = next_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_at = time.monotonic()
        self._capture.release()

    def latest(self) -> Optional[Any]:
        """Latest frame (BGR, 1280x720), or None before the first one."""
        with self._lock:
            return self._frame

    def stop(self) -> None:
        self._running = False


class DeviceStream(threading.Thread):
    """A webcam attached to this machine. Keeps retrying, so a camera plugged in late still shows up."""

    def __init__(self, camera_id: str, device: Union[int, str]) -> None:
        super().__init__(daemon=True, name=f"ingest-{camera_id}")
        self.camera_id = camera_id
        self.device = device
        self._lock = threading.Lock()
        self._frame: Optional[Any] = None
        self._running = True

    def run(self) -> None:
        import cv2

        warned = False
        while self._running:
            capture = cv2.VideoCapture(self.device)
            if not capture.isOpened():
                if not warned:
                    log.warning("%s: webcam %s is not available, retrying", self.camera_id, self.device)
                    warned = True
                capture.release()
                time.sleep(2.0)
                continue
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, SIZE[0])
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, SIZE[1])
            while self._running:
                ok, frame = capture.read()
                if not ok:
                    break
                frame = _fit(frame)
                with self._lock:
                    self._frame = frame
            capture.release()
            with self._lock:
                self._frame = None

    def latest(self) -> Optional[Any]:
        with self._lock:
            return self._frame

    def stop(self) -> None:
        self._running = False


class PushStream:
    """Frames sent by a browser that shares its webcam (POST /api/camera/{plant}/{floor}/frame)."""

    def __init__(self, camera_id: str) -> None:
        self.camera_id = camera_id
        self._lock = threading.Lock()
        self._frame: Optional[Any] = None
        self._at = 0.0

    def push(self, jpeg: bytes) -> bool:
        """Store one JPEG frame. False when the bytes are not an image."""
        import cv2
        import numpy as np

        frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return False
        frame = _fit(frame)
        with self._lock:
            self._frame, self._at = frame, time.monotonic()
        return True

    def latest(self) -> Optional[Any]:
        """Latest frame, or None when the browser stopped sending."""
        with self._lock:
            return self._frame if time.monotonic() - self._at <= STALE_AFTER_S else None

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


Source = Union[VideoStream, DeviceStream, PushStream]


def open_source(camera: Camera, videos_dir: Path) -> Source:
    kind = camera.source_kind()
    if kind == "browser":
        return PushStream(camera.id)
    if kind == "webcam":
        device = camera.video.split(":", 1)[1]
        return DeviceStream(camera.id, int(device) if device.isdigit() else device)
    return VideoStream(camera.id, str(resolve_video(camera.video, videos_dir)))

"""ByteTrack-style tracker, one per stream: two-stage IoU association (high then low scores).

Pure Python and no Kalman filter: boxes are predicted with the last frame-to-frame shift, which is
enough at 10 fps with a fixed camera.
"""
from __future__ import annotations

from dataclasses import dataclass

BBox = tuple[float, float, float, float]  # x1, y1, x2, y2 in pixels


@dataclass
class Detection:
    bbox: BBox
    score: float
    cls: str


@dataclass
class Tracklet:
    id: int
    bbox: BBox
    cls: str
    shift: tuple[float, float] = (0.0, 0.0)
    hits: int = 1
    misses: int = 0

    def predicted(self) -> BBox:
        dx, dy = self.shift
        x1, y1, x2, y2 = self.bbox
        return x1 + dx, y1 + dy, x2 + dx, y2 + dy


def iou(a: BBox, b: BBox) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


class ByteTracker:
    def __init__(self, high: float = 0.5, low: float = 0.1, min_iou: float = 0.25,
                 max_misses: int = 15, min_hits: int = 2) -> None:
        self.high, self.low, self.min_iou = high, low, min_iou
        self.max_misses, self.min_hits = max_misses, min_hits
        self._tracklets: list[Tracklet] = []
        self._next_id = 1

    def update(self, detections: list[Detection]) -> list[Tracklet]:
        """Feed one frame of detections; returns the confirmed tracks seen in this frame."""
        strong = [d for d in detections if d.score >= self.high]
        weak = [d for d in detections if self.low <= d.score < self.high]
        unmatched = list(self._tracklets)
        seen: list[Tracklet] = []
        leftover_strong = self._associate(unmatched, strong, seen)
        self._associate(unmatched, weak, seen)
        for tracklet in unmatched:
            tracklet.misses += 1
            tracklet.bbox = tracklet.predicted()
        for det in leftover_strong:
            self._tracklets.append(Tracklet(id=self._next_id, bbox=det.bbox, cls=det.cls))
            self._next_id += 1
        self._tracklets = [t for t in self._tracklets if t.misses <= self.max_misses]
        return [t for t in seen if t.hits >= self.min_hits]

    def _associate(self, tracklets: list[Tracklet], detections: list[Detection], seen: list[Tracklet]) -> list[Detection]:
        """Greedy best-IoU matching. Removes matched tracklets from `tracklets`; returns unmatched detections."""
        pairs = sorted(
            ((iou(t.predicted(), d.bbox), ti, di) for ti, t in enumerate(tracklets) for di, d in enumerate(detections)),
            reverse=True,
        )
        used_t: set[int] = set()
        used_d: set[int] = set()
        for score, ti, di in pairs:
            if score < self.min_iou:
                break
            if ti in used_t or di in used_d:
                continue
            used_t.add(ti)
            used_d.add(di)
            tracklet, det = tracklets[ti], detections[di]
            tracklet.shift = (det.bbox[0] - tracklet.bbox[0], det.bbox[1] - tracklet.bbox[1]) if tracklet.misses == 0 else (0.0, 0.0)
            tracklet.bbox, tracklet.hits, tracklet.misses = det.bbox, tracklet.hits + 1, 0
            seen.append(tracklet)
        tracklets[:] = [t for i, t in enumerate(tracklets) if i not in used_t]
        return [d for i, d in enumerate(detections) if i not in used_d]

"""The in-memory track and the interface both perception backends implement."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class Track:
    id: int
    zone: str  # global floor key, e.g. "P1/F1"
    cls: str  # person | forklift | vehicle
    x: float  # floor metres
    y: float
    vx: float = 0.0  # metres per second
    vy: float = 0.0
    bbox: Optional[tuple[float, float, float, float]] = None  # image pixels x1, y1, x2, y2
    last_seen: float = 0.0
    helmet: Optional[bool] = None  # None = not checked


class Perception(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def tracks(self) -> dict[str, list[Track]]:
        """Current tracks per floor key."""

    def fps(self) -> dict[str, float]:
        """Detection frames per second per camera id."""

    def frame_jpeg(self, zone: str) -> Optional[bytes]:
        """Latest camera frame of a floor, or None when there is no real video."""

    def push_frame(self, zone: str, jpeg: bytes) -> bool:
        """Accept one JPEG frame shared from a browser for this floor. False when it cannot be used."""

    def view(self, zone: str) -> Optional[tuple[bytes, str]]:
        """Live camera view of a floor with every track marked: (data, file extension)."""

    def snapshot(self, zone: str, track_ids: list[int]) -> Optional[tuple[bytes, str]]:
        """Image of the floor right now with the given tracks marked: (data, file extension)."""

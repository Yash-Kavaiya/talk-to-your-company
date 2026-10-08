"""Mock perception: waypoint-walking tracks per floor plus scripted scenarios on a timer.

A scenario steers tracks into a situation (walk into a restricted zone, head at a forklift,
gather, take a helmet off) so that the real rules engine raises the event. Runs anywhere,
needs no GPU and no video.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, replace
from typing import Optional

from app.config import Floor, Site, zone_key
from app.events.rules import CROWD_MAX_PEOPLE, point_in_polygon
from app.perception.base import Track

MARGIN_M = 0.5
GIVE_WAY_M = 4.0
OBJECT_CLEARANCE_M = 0.5
SCENARIOS = ("restricted_zone", "near_miss", "no_helmet", "crowding")
COLOURS = {"person": "#4fd1c5", "forklift": "#f6ad55", "vehicle": "#a0aec0"}


@dataclass
class _Actor:
    track: Track
    target: tuple[float, float]
    speed: float
    cruise: float  # normal speed, restored after a scenario
    pause: float = 0.0  # seconds left standing still
    hold: float = 0.0  # scripted: stand this long on arrival
    scripted: bool = False
    area: Optional[list[tuple[float, float]]] = None  # stay inside this polygon (dock vehicles)


class MockPerception:
    def __init__(
        self,
        site: Site,
        seed: int = 7,
        people_per_floor: int = CROWD_MAX_PEOPLE + 1,
        event_period: float = 30.0,
        first_event_at: float = 4.0,
    ) -> None:
        self.site = site
        self.rng = random.Random(seed)
        self.event_period = event_period
        self.sim_time = 0.0
        self._next_scenario_at = first_event_at
        self._scenario_index = 0
        self._helmet_restore: list[tuple[float, _Actor]] = []
        self._floors: dict[str, Floor] = {zone_key(p.id, f.id): f for p, f in site.floors()}
        self._actors: dict[str, list[_Actor]] = {}
        self._last_wall: Optional[float] = None
        self._calls: list[float] = []
        self._pushed: dict[str, tuple[bytes, float]] = {}
        self.launched: list[tuple[float, str, str]] = []  # (sim time, floor key, scenario)
        next_id = 1
        for key, floor in self._floors.items():
            actors = []
            classes = ["person"] * people_per_floor + ["forklift"]
            dock = next((z for z in floor.zones if z.type == "dock"), None)
            if dock:
                classes.append("vehicle")
            for cls in classes:
                area = dock.polygon if cls == "vehicle" and dock else None
                x, y = self._random_point(floor, area)
                cruise = {"person": self.rng.uniform(0.8, 1.5), "forklift": self.rng.uniform(1.8, 2.6), "vehicle": 0.6}[cls]
                track = Track(id=next_id, zone=key, cls=cls, x=x, y=y, helmet=True if cls == "person" else None)
                actors.append(_Actor(track=track, target=(x, y), speed=cruise, cruise=cruise, area=area))
                next_id += 1
            self._actors[key] = actors

    # ---- Perception interface ----

    def start(self) -> None:
        self._last_wall = time.monotonic()

    def stop(self) -> None:
        pass

    def tracks(self) -> dict[str, list[Track]]:
        """Advance the simulation by the wall-clock time since the last call."""
        now = time.monotonic()
        elapsed = min(now - self._last_wall, 1.0) if self._last_wall is not None else 0.0
        self._last_wall = now
        self._calls = [t for t in self._calls if now - t < 3.0] + [now]
        while elapsed > 1e-6:
            step = min(elapsed, 0.2)
            self.advance(step)
            elapsed -= step
        return self.current()

    def fps(self) -> dict[str, float]:
        rate = max(len(self._calls) - 1, 0) / (self._calls[-1] - self._calls[0]) if len(self._calls) > 1 else 0.0
        return {floor.camera.id: round(rate, 1) for floor in self._floors.values()}

    def push_frame(self, zone: str, jpeg: bytes) -> bool:
        """Mock perception detects nothing, but a shared webcam is still shown in the camera view."""
        if zone not in self._floors or not jpeg.startswith(b"\xff\xd8"):
            return False
        self._pushed[zone] = (jpeg, time.monotonic())
        return True

    def frame_jpeg(self, zone: str) -> Optional[bytes]:
        jpeg, at = self._pushed.get(zone, (None, 0.0))
        return jpeg if jpeg and time.monotonic() - at <= 2.0 else None

    def view(self, zone: str) -> Optional[tuple[bytes, str]]:
        jpeg = self.frame_jpeg(zone)
        return (jpeg, "jpg") if jpeg else self.snapshot(zone, [])

    def snapshot(self, zone: str, track_ids: list[int]) -> Optional[tuple[bytes, str]]:
        floor = self._floors.get(zone)
        if floor is None:
            return None
        return _render_svg(floor, [a.track for a in self._actors[zone]], set(track_ids)).encode("utf-8"), "svg"

    # ---- simulation ----

    def current(self) -> dict[str, list[Track]]:
        now = time.time()
        return {key: [replace(a.track, last_seen=now) for a in actors] for key, actors in self._actors.items()}

    def advance(self, dt: float) -> None:
        self.sim_time += dt
        if self.sim_time >= self._next_scenario_at:
            self._next_scenario_at += self.event_period
            self._launch_scenario()
        for when, actor in list(self._helmet_restore):
            if self.sim_time >= when:
                actor.track.helmet = True
                self._helmet_restore.remove((when, actor))
        for key, actors in self._actors.items():
            self._give_way(self._floors[key], actors)
            for actor in actors:
                self._move(self._floors[key], actor, dt)

    def _give_way(self, floor: Floor, actors: list[_Actor]) -> None:
        """Outside scenarios, forklifts stop for nearby people and people step away, so near misses stay rare."""
        w, d = floor.size_m
        for forklift in (a for a in actors if a.track.cls == "forklift" and not a.scripted):
            for person in (a for a in actors if a.track.cls == "person" and not a.scripted):
                dx, dy = person.track.x - forklift.track.x, person.track.y - forklift.track.y
                gap = math.hypot(dx, dy)
                if gap > GIVE_WAY_M:
                    continue
                forklift.pause = max(forklift.pause, 1.0)
                if gap > 1e-6:
                    person.pause = 0.0
                    person.target = (min(max(person.track.x + dx / gap * 5, MARGIN_M), w - MARGIN_M),
                                     min(max(person.track.y + dy / gap * 5, MARGIN_M), d - MARGIN_M))

    def _move(self, floor: Floor, actor: _Actor, dt: float) -> None:
        t = actor.track
        if actor.pause > 0:
            actor.pause -= dt
            t.vx = t.vy = 0.0
            if actor.pause <= 0:
                actor.scripted = False
                actor.speed = actor.cruise
                actor.target = self._free_waypoint(floor, actor)
            return
        dx, dy = actor.target[0] - t.x, actor.target[1] - t.y
        gap = math.hypot(dx, dy)
        step = actor.speed * dt
        if gap <= step:
            t.x, t.y = actor.target
            t.vx = t.vy = 0.0
            actor.pause = actor.hold if actor.scripted else self.rng.uniform(0.5, 3.0)
            actor.hold = 0.0
            return
        t.vx, t.vy = dx / gap * actor.speed, dy / gap * actor.speed
        t.x += t.vx * dt
        t.y += t.vy * dt

    def _random_point(self, floor: Floor, area: Optional[list[tuple[float, float]]] = None) -> tuple[float, float]:
        w, d = floor.size_m
        blocked = _no_go(floor, OBJECT_CLEARANCE_M + 0.3)
        for _ in range(80):
            if area:
                xs, ys = [p[0] for p in area], [p[1] for p in area]
                x = self.rng.uniform(max(min(xs), MARGIN_M), min(max(xs), w - MARGIN_M))
                y = self.rng.uniform(max(min(ys), MARGIN_M), min(max(ys), d - MARGIN_M))
            else:
                x = self.rng.uniform(MARGIN_M, w - MARGIN_M)
                y = self.rng.uniform(MARGIN_M, d - MARGIN_M)
            if not any(point_in_polygon(x, y, poly) for poly in blocked):
                return x, y
        return w / 2, d / 2

    def _free_waypoint(self, floor: Floor, actor: _Actor) -> tuple[float, float]:
        """A waypoint whose straight path crosses neither a restricted zone nor a piece of equipment."""
        blocked = _no_go(floor, OBJECT_CLEARANCE_M)
        point = (actor.track.x, actor.track.y)
        for _ in range(40):
            point = self._random_point(floor, actor.area)
            if not _path_crosses(actor.track.x, actor.track.y, point[0], point[1], blocked):
                return point
        return point

    def _send(self, actor: _Actor, target: tuple[float, float], speed: float, hold: float) -> None:
        actor.target, actor.speed, actor.hold = target, speed, hold
        actor.pause, actor.scripted = 0.0, True

    def _launch_scenario(self) -> None:
        kind = SCENARIOS[self._scenario_index % len(SCENARIOS)]
        self._scenario_index += 1
        key = self.rng.choice(list(self._floors))
        if kind == "restricted_zone" and self.site.demo_restricted_floor in self._floors:
            key = self.site.demo_restricted_floor
        floor, actors = self._floors[key], self._actors[key]
        people = [a for a in actors if a.track.cls == "person"]
        forklifts = [a for a in actors if a.track.cls == "forklift"]
        restricted = [z for z in floor.zones if z.type == "restricted"]
        if kind == "restricted_zone" and not restricted:
            kind = "near_miss"
        if kind == "restricted_zone":
            poly = restricted[0].polygon
            centre = (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))
            actor = min(people, key=lambda a: math.hypot(a.track.x - centre[0], a.track.y - centre[1]))
            self._send(actor, centre, 1.6, 6.0)
        elif kind == "near_miss":
            forklift = forklifts[0]
            person = min(people, key=lambda a: math.hypot(a.track.x - forklift.track.x, a.track.y - forklift.track.y))
            person_pos, forklift_pos = (person.track.x, person.track.y), (forklift.track.x, forklift.track.y)
            self._send(person, forklift_pos, 1.4, 1.0)
            self._send(forklift, person_pos, 2.4, 1.0)
        elif kind == "no_helmet":
            actor = self.rng.choice(people)
            actor.track.helmet = False
            self._helmet_restore.append((self.sim_time + 40.0, actor))
        else:  # crowding
            cx, cy = self._random_point(floor)
            w, d = floor.size_m
            for actor in people:
                x = min(max(cx + self.rng.uniform(-1, 1), MARGIN_M), w - MARGIN_M)
                y = min(max(cy + self.rng.uniform(-1, 1), MARGIN_M), d - MARGIN_M)
                self._send(actor, (x, y), 1.6, 8.0)
        self.launched.append((self.sim_time, key, kind))


def _no_go(floor: Floor, clearance: float) -> list[list[tuple[float, float]]]:
    """Where nobody walks unless a scenario sends them: restricted zones and equipment footprints."""
    return ([z.polygon for z in floor.zones if z.type == "restricted"]
            + [o.polygon(clearance) for o in floor.objects])


def _path_crosses(x1: float, y1: float, x2: float, y2: float, polygons: list[list[tuple[float, float]]]) -> bool:
    if not polygons:
        return False
    steps = max(int(math.hypot(x2 - x1, y2 - y1) / 0.5), 1)
    for i in range(steps + 1):
        x, y = x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps
        if any(point_in_polygon(x, y, poly) for poly in polygons):
            return True
    return False


def _render_svg(floor: Floor, tracks: list[Track], marked: set[int]) -> str:
    """Top-down synthetic view of a floor, used as the event snapshot in mock mode."""
    w, d = floor.size_m
    zone_fill = {"restricted": "#e53e3e", "walkway": "#4fd1c5", "dock": "#a0aec0"}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 -1 {w + 2} {d + 4}" font-family="sans-serif">',
        f'<rect x="-1" y="-1" width="{w + 2}" height="{d + 4}" fill="#0b1016"/>',
        f'<rect width="{w}" height="{d}" fill="#141c26" stroke="#2d3b4d" stroke-width="0.15"/>',
    ]
    for zone in floor.zones:
        points = " ".join(f"{x},{y}" for x, y in zone.polygon)
        parts.append(f'<polygon points="{points}" fill="{zone_fill[zone.type]}" fill-opacity="0.18" '
                     f'stroke="{zone_fill[zone.type]}" stroke-width="0.1"/>')
    for obj in floor.objects:
        x, y, ow, od = obj.rect
        parts.append(f'<rect x="{x}" y="{y}" width="{ow}" height="{od}" fill="#2d3b4d" stroke="#4a5d75" stroke-width="0.08"/>')
    for t in tracks:
        if t.cls == "person":
            parts.append(f'<circle cx="{t.x:.2f}" cy="{t.y:.2f}" r="0.45" fill="{COLOURS[t.cls]}"/>')
        else:
            parts.append(f'<rect x="{t.x - 0.9:.2f}" y="{t.y - 0.6:.2f}" width="1.8" height="1.2" rx="0.2" fill="{COLOURS[t.cls]}"/>')
        if t.id in marked:
            parts.append(f'<circle cx="{t.x:.2f}" cy="{t.y:.2f}" r="1.6" fill="none" stroke="#f56565" stroke-width="0.25"/>')
    stamp = time.strftime("%H:%M:%S")
    parts.append(f'<text x="0" y="{d + 2}" font-size="1.4" fill="#718096">'
                 f'SYNTHETIC VIEW (mock perception) · {floor.camera.id} · {stamp}</text>')
    parts.append("</svg>")
    return "".join(parts)

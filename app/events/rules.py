"""Safety rules over tracks (plan section 7).

The geometric checks are pure functions. `RulesEngine` adds the little state they need:
dwell time in restricted zones and the debounce.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

from app.config import Site, Zone, split_zone_key
from app.perception.base import Track

NEAR_MISS_DISTANCE_M = 2.0
NEAR_MISS_CLOSING_MPS = 0.5
RESTRICTED_DWELL_S = 2.0
CROWD_RADIUS_M = 3.0
CROWD_MAX_PEOPLE = 4  # more than this many people in the radius is crowding
DEBOUNCE_S = 30.0

SEVERITY = {"near_miss": 3, "restricted_zone": 2, "no_helmet": 2, "crowding": 1}


@dataclass
class Finding:
    type: str
    severity: int
    track_ids: list[int]
    x: float
    y: float
    summary: str
    zone_id: Optional[str] = None  # the restricted zone, for restricted_zone findings


def point_in_polygon(x: float, y: float, polygon: Sequence[tuple[float, float]]) -> bool:
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def distance(a: Track, b: Track) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def closing_speed(a: Track, b: Track) -> float:
    """Rate at which the gap between two tracks shrinks, in m/s. Negative when moving apart."""
    dx, dy = b.x - a.x, b.y - a.y
    gap = math.hypot(dx, dy)
    if gap < 1e-6:
        return math.hypot(b.vx - a.vx, b.vy - a.vy)
    return -((b.vx - a.vx) * dx + (b.vy - a.vy) * dy) / gap


def find_near_misses(
    tracks: Sequence[Track],
    max_distance: float = NEAR_MISS_DISTANCE_M,
    min_closing: float = NEAR_MISS_CLOSING_MPS,
) -> list[Finding]:
    people = [t for t in tracks if t.cls == "person"]
    forklifts = [t for t in tracks if t.cls == "forklift"]
    found = []
    for person in people:
        for forklift in forklifts:
            gap = distance(person, forklift)
            if gap <= max_distance and closing_speed(person, forklift) > min_closing:
                found.append(Finding(
                    type="near_miss",
                    severity=SEVERITY["near_miss"],
                    track_ids=[person.id, forklift.id],
                    x=(person.x + forklift.x) / 2,
                    y=(person.y + forklift.y) / 2,
                    summary=f"Person {person.id} came within {gap:.1f} m of moving forklift {forklift.id}.",
                ))
    return found


def people_in_restricted(tracks: Sequence[Track], zones: Sequence[Zone]) -> list[tuple[Track, Zone]]:
    restricted = [z for z in zones if z.type == "restricted"]
    return [
        (t, z)
        for t in tracks if t.cls == "person"
        for z in restricted if point_in_polygon(t.x, t.y, z.polygon)
    ]


def find_crowding(
    tracks: Sequence[Track],
    max_people: int = CROWD_MAX_PEOPLE,
    radius: float = CROWD_RADIUS_M,
) -> list[Finding]:
    """At most one finding: the largest group of people inside `radius` of one of them."""
    people = [t for t in tracks if t.cls == "person"]
    best: list[Track] = []
    for centre in people:
        group = [t for t in people if distance(centre, t) <= radius]
        if len(group) > len(best):
            best = group
    if len(best) <= max_people:
        return []
    return [Finding(
        type="crowding",
        severity=SEVERITY["crowding"],
        track_ids=sorted(t.id for t in best),
        x=sum(t.x for t in best) / len(best),
        y=sum(t.y for t in best) / len(best),
        summary=f"{len(best)} people gathered within {radius:.0f} m.",
    )]


def people_without_helmet(tracks: Sequence[Track]) -> list[Track]:
    return [t for t in tracks if t.cls == "person" and t.helmet is False]


class RulesEngine:
    def __init__(
        self,
        site: Site,
        debounce_s: float = DEBOUNCE_S,
        dwell_s: float = RESTRICTED_DWELL_S,
        crowd_max_people: int = CROWD_MAX_PEOPLE,
    ) -> None:
        self.site = site
        self.debounce_s = debounce_s
        self.dwell_s = dwell_s
        self.crowd_max_people = crowd_max_people
        # (floor key, track id, zone id) -> [time entered, already fired]
        self._dwell: dict[tuple[str, int, str], list] = {}
        self._helmet_fired: set[tuple[str, int]] = set()
        # recent firings per (floor key, type): (time, track ids)
        self._fired: dict[tuple[str, str], list[tuple[float, frozenset[int]]]] = {}

    def evaluate(self, zone_key: str, tracks: Sequence[Track], now: float) -> list[Finding]:
        """Findings for one floor at time `now` (seconds), after dwell and debounce."""
        floor = self.site.floor(*split_zone_key(zone_key))
        zones = floor.zones if floor else []
        candidates = find_near_misses(tracks)
        candidates += self._restricted(zone_key, tracks, zones, now)
        candidates += find_crowding(tracks, self.crowd_max_people)
        candidates += self._no_helmet(zone_key, tracks)
        return [f for f in candidates if self._debounce(zone_key, f, now)]

    def entered_at(self, zone_key: str, track_id: int, zone_id: str) -> Optional[float]:
        """When a person entered a restricted zone, or None if they are not inside it now."""
        entry = self._dwell.get((zone_key, track_id, zone_id))
        return entry[0] if entry else None

    def _restricted(self, zone_key: str, tracks: Sequence[Track], zones: Sequence[Zone], now: float) -> list[Finding]:
        inside = {(zone_key, t.id, z.id): (t, z) for t, z in people_in_restricted(tracks, zones)}
        for key in [k for k in self._dwell if k[0] == zone_key and k not in inside]:
            del self._dwell[key]
        found = []
        for key, (track, zone) in inside.items():
            entry = self._dwell.setdefault(key, [now, False])
            if not entry[1] and now - entry[0] > self.dwell_s:
                entry[1] = True
                found.append(Finding(
                    type="restricted_zone",
                    severity=SEVERITY["restricted_zone"],
                    track_ids=[track.id],
                    x=track.x,
                    y=track.y,
                    summary=f"Person {track.id} has been inside restricted zone {zone.id} for over {self.dwell_s:.0f} s.",
                    zone_id=zone.id,
                ))
        return found

    def _no_helmet(self, zone_key: str, tracks: Sequence[Track]) -> list[Finding]:
        bare = {(zone_key, t.id): t for t in people_without_helmet(tracks)}
        self._helmet_fired = {k for k in self._helmet_fired if k[0] != zone_key or k in bare}
        found = []
        for key, track in bare.items():
            if key not in self._helmet_fired:
                self._helmet_fired.add(key)
                found.append(Finding(
                    type="no_helmet",
                    severity=SEVERITY["no_helmet"],
                    track_ids=[track.id],
                    x=track.x,
                    y=track.y,
                    summary=f"Person {track.id} is not wearing a helmet.",
                ))
        return found

    def _debounce(self, zone_key: str, finding: Finding, now: float) -> bool:
        """Same type and overlapping tracks cannot re-fire within the debounce window."""
        ids = frozenset(finding.track_ids)
        recent = [(t, s) for t, s in self._fired.get((zone_key, finding.type), []) if now - t < self.debounce_s]
        if any(ids & seen for _, seen in recent):
            self._fired[(zone_key, finding.type)] = recent
            return False
        recent.append((now, ids))
        self._fired[(zone_key, finding.type)] = recent
        return True

"""Who is who: a synthetic employee directory plus a simulated badge feed.

Nobody is recognised from their face or appearance. The badge feed stands in for an access-control
or location system: it says which employee a tracked person is, using the fictional people in
config/employees.yaml. Swap `BadgeFeed` for a real badge system to use this with real staff.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import ConfigError
from app.events.rules import RulesEngine
from app.perception.base import Track

SOURCE = "simulated badge feed (synthetic employee data, no face recognition)"
REMEMBER_LOST_S = 10.0  # a track that vanished keeps its badge this long
INHERIT_WITHIN_M = 4.0  # a new track this close to a vanished one is the same person


class Employee(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    role: str
    department: str
    shift: str
    supervisor: str
    home: str  # floor key, e.g. "P1/F2"
    authorised_zones: list[str] = []  # "plant/floor/zone"
    certifications: list[str] = []


class Directory:
    def __init__(self, employees: list[Employee]) -> None:
        self.employees = employees
        self._by_id = {e.id: e for e in employees}
        if len(self._by_id) != len(employees):
            raise ConfigError("duplicate employee id")

    def get(self, employee_id: Optional[str]) -> Optional[Employee]:
        return self._by_id.get(employee_id) if employee_id else None

    def find(self, text: str) -> Optional[Employee]:
        """Employee whose id, full name or (unambiguous) first name appears in `text`."""
        text = text.lower()
        for e in self.employees:
            if e.id.lower() in text or e.name.lower() in text:
                return e
        words = set(text.replace("?", " ").replace(",", " ").replace(".", " ").replace("'s", " ").split())
        first = [e for e in self.employees if e.name.split()[0].lower() in words]
        return first[0] if len(first) == 1 else None


def load_directory(path: str | Path) -> Directory:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return Directory([Employee.model_validate(e) for e in raw["employees"]])
    except (OSError, yaml.YAMLError, KeyError, TypeError, ValidationError) as exc:
        raise ConfigError(f"cannot load employee directory {path}: {exc}") from exc


class BadgeFeed:
    """Simulated badge system: gives every tracked person on a floor one of that floor's employees."""

    def __init__(self, directory: Directory) -> None:
        self.directory = directory
        self._active: dict[int, str] = {}  # track id -> employee id
        self._place: dict[int, tuple[str, float, float, float]] = {}  # track id -> zone, x, y, last seen
        self._released: dict[str, float] = {}  # employee id -> when their last track was given up
        self.first_seen: dict[str, float] = {}  # employee id -> first time on camera

    def update(self, tracks: dict[str, list[Track]], now: float) -> None:
        present = {t.id for ts in tracks.values() for t in ts if t.cls == "person"}
        for track_id in [i for i in self._active if i not in present and now - self._place[i][3] > REMEMBER_LOST_S]:
            self._released[self._active.pop(track_id)] = now
            del self._place[track_id]
        for zone, on_floor in tracks.items():
            for track in on_floor:
                if track.cls != "person":
                    continue
                if track.id not in self._active:
                    employee_id = self._inherit(zone, track, present) or self._free_employee(zone)
                    if employee_id is None:
                        continue
                    self._active[track.id] = employee_id
                    self.first_seen.setdefault(employee_id, now)
                self._place[track.id] = (zone, track.x, track.y, now)

    def _inherit(self, zone: str, track: Track, present: set[int]) -> Optional[str]:
        """Take over the badge of a track that just vanished nearby (the tracker lost and re-found them)."""
        best, best_gap = None, INHERIT_WITHIN_M
        for lost_id, (lost_zone, x, y, _) in self._place.items():
            if lost_id in present or lost_zone != zone:
                continue
            gap = math.hypot(track.x - x, track.y - y)
            if gap <= best_gap:
                best, best_gap = lost_id, gap
        if best is None:
            return None
        del self._place[best]
        return self._active.pop(best)

    def _free_employee(self, zone: str) -> Optional[str]:
        taken = set(self._active.values())
        free = [e for e in self.directory.employees if e.id not in taken]
        home = [e for e in free if e.home == zone]
        if home:  # prefer whoever was here most recently: probably the same person coming back
            return max(home, key=lambda e: self._released.get(e.id, 0.0)).id
        return free[0].id if free else None

    def employee_for(self, track_id: int) -> Optional[Employee]:
        return self.directory.get(self._active.get(track_id))

    def locate(self, employee_id: str, tracks: dict[str, list[Track]]) -> Optional[tuple[str, float, float]]:
        """Where an employee is right now: (floor key, x, y), or None when on no camera."""
        wanted = {i for i, e in self._active.items() if e == employee_id}
        for zone, on_floor in tracks.items():
            for track in on_floor:
                if track.id in wanted:
                    return zone, track.x, track.y
        return None


@dataclass
class Visit:
    """One stay in a restricted zone that raised an event."""

    zone_key: str
    track_id: int
    zone_id: str
    entered: float
    left: Optional[float] = None


class People:
    """Directory, badge feed and restricted-zone visit timing, as used by the hub and the agent tools."""

    def __init__(self, directory: Directory) -> None:
        self.directory = directory
        self.badges = BadgeFeed(directory)
        self.visits: dict[int, Visit] = {}  # event id -> visit

    def open_visit(self, event_id: int, zone_key: str, track_id: int, zone_id: str, entered: float) -> None:
        self.visits[event_id] = Visit(zone_key, track_id, zone_id, entered)

    def close_visits(self, rules: RulesEngine, now: float) -> None:
        """Mark visits as ended once the rules engine no longer sees the person inside the zone."""
        for visit in self.visits.values():
            if visit.left is None and rules.entered_at(visit.zone_key, visit.track_id, visit.zone_id) is None:
                visit.left = now

"""The agent's tools over the event store and the live state (plan section 6)."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.config import Site, split_zone_key, zone_key
from app.events.store import EventStore
from app.identity import SOURCE, People
from app.perception.base import Perception, Track
from app.protocol import Event, UiMsg

OPEN_EVENT_MINUTES = 10  # an event counts as open for this long

RECOMMENDED_ACTION = {
    "near_miss": "Review the forklift route with the driver and the worker; check floor markings and mirrors at this spot.",
    "restricted_zone": "Confirm whether the person was authorised; if not, brief the team and check the zone barrier and signage.",
    "no_helmet": "Remind the worker of the PPE rule and check helmet availability at the floor entrance.",
    "crowding": "Disperse the group and check whether a blocked route or a stopped line caused the gathering.",
}
SEVERITY_NAME = {1: "low", 2: "medium", 3: "high"}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"name": "query_events", "description": "List safety events that were recorded, newest first.",
     "parameters": {"type": "object", "properties": {
         "plant": {"type": "string", "description": "Plant id such as P1. Omit for all plants."},
         "floor": {"type": "string", "description": "Floor id such as F3. Omit for all floors."},
         "type": {"type": "string", "enum": ["near_miss", "restricted_zone", "no_helmet", "crowding"]},
         "minutes_back": {"type": "number", "description": "How far back to look. Default 10."}}}},
    {"name": "live_state", "description": "Count people, vehicles and open events right now, per floor and per plant.",
     "parameters": {"type": "object", "properties": {
         "plant": {"type": "string"}, "floor": {"type": "string"}}}},
    {"name": "look", "description": "Ask the vision model a question about the current camera frame of one floor.",
     "parameters": {"type": "object", "required": ["plant", "floor", "question"], "properties": {
         "plant": {"type": "string"}, "floor": {"type": "string"}, "question": {"type": "string"}}}},
    {"name": "focus_view", "description": "Move the 3D twin's camera to a plant, or to one floor of it.",
     "parameters": {"type": "object", "required": ["plant"], "properties": {
         "plant": {"type": "string"}, "floor": {"type": "string"}}}},
    {"name": "show_event", "description": "Open one event in the side panel and highlight its marker.",
     "parameters": {"type": "object", "required": ["event_id"], "properties": {"event_id": {"type": "integer"}}}},
    {"name": "identify_person",
     "description": "Who a person is, from the badge system: employee details, when they entered a restricted "
                    "zone and for how long, where they are now and their other incidents. Give the event the "
                    "person was involved in (default: the last event), or a name to look someone up.",
     "parameters": {"type": "object", "properties": {
         "event_id": {"type": "integer"}, "name": {"type": "string", "description": "Employee name or id."}}}},
    {"name": "write_report", "description": "Write the structured incident report for one event into the side panel.",
     "parameters": {"type": "object", "required": ["event_id"], "properties": {"event_id": {"type": "integer"}}}},
]


@dataclass
class Session:
    """Conversation state of one browser connection."""

    focus_plant: Optional[str] = None
    focus_floor: Optional[str] = None
    last_event_id: Optional[int] = None
    history: list[dict[str, str]] = field(default_factory=list)


class Tools:
    def __init__(
        self,
        site: Site,
        store: EventStore,
        perception: Perception,
        live_tracks: Callable[[], dict[str, list[Track]]],
        vision: Callable[[Optional[bytes], str, str], str],
        session: Session,
        clock: Callable[[], float] = time.time,
        people: Optional[People] = None,
    ) -> None:
        self.site = site
        self.store = store
        self.perception = perception
        self.live_tracks = live_tracks
        self.vision = vision
        self.session = session
        self.clock = clock
        self.people = people
        self.pending_ui: list[UiMsg] = []  # the agent loop sends and clears these

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Run one tool by name. Bad names and arguments come back as `{"error": ...}`."""
        tool = {
            "query_events": self.query_events, "live_state": self.live_state, "look": self.look,
            "focus_view": self.focus_view, "show_event": self.show_event, "write_report": self.write_report,
            "identify_person": self.identify_person,
        }.get(name)
        if tool is None:
            return {"error": f"unknown tool {name}"}
        try:
            return tool(**arguments)
        except (TypeError, ValueError) as exc:
            return {"error": f"bad arguments for {name}: {exc}"}

    # ---- tools ----

    def query_events(self, plant: Optional[str] = None, floor: Optional[str] = None,
                     type: Optional[str] = None, minutes_back: float = 10) -> dict[str, Any]:
        plant_id, floor_id, error = self._resolve(plant, floor)
        if error:
            return {"error": error}
        minutes_back = float(minutes_back)
        events = self.store.query(plant=plant_id, floor=floor_id, type=type, since=self.clock() - minutes_back * 60)
        by_type: dict[str, int] = {}
        for e in events:
            by_type[e.type] = by_type.get(e.type, 0) + 1
        if events:
            self.session.last_event_id = events[0].id
            self.pending_ui.append(UiMsg(action="highlight", event_ids=[e.id for e in events[:50]]))
        return {"count": len(events), "minutes_back": minutes_back, "plant": plant_id, "floor": floor_id, "type": type,
                "by_type": by_type, "events": [self._brief(e) for e in events[:10]]}

    def live_state(self, plant: Optional[str] = None, floor: Optional[str] = None) -> dict[str, Any]:
        plant_id, floor_id, error = self._resolve(plant, floor)
        if error:
            return {"error": error}
        tracks = self.live_tracks()
        since = self.clock() - OPEN_EVENT_MINUTES * 60
        floors, totals = [], {}
        for p, f in self.site.floors():
            if (plant_id and p.id != plant_id) or (floor_id and f.id != floor_id):
                continue
            on_floor = tracks.get(zone_key(p.id, f.id), [])
            row = {
                "plant": p.id, "plant_name": p.name, "floor": f.id,
                "people": sum(t.cls == "person" for t in on_floor),
                "vehicles": sum(t.cls != "person" for t in on_floor),
                "open_events": len(self.store.query(plant=p.id, floor=f.id, since=since)),
            }
            floors.append(row)
            total = totals.setdefault(p.id, {"plant_name": p.name, "people": 0, "vehicles": 0, "open_events": 0})
            for k in ("people", "vehicles", "open_events"):
                total[k] += row[k]
        return {"floors": floors, "totals": totals}

    def look(self, plant: str, floor: str, question: str) -> dict[str, Any]:
        plant_id, floor_id, error = self._resolve(plant, floor)
        if error or not plant_id or not floor_id:
            return {"error": error or "look needs a plant and a floor"}
        key = zone_key(plant_id, floor_id)
        on_floor = self.live_tracks().get(key, [])
        people = sum(t.cls == "person" for t in on_floor)
        forklifts = sum(t.cls == "forklift" for t in on_floor)
        vehicles = sum(t.cls == "vehicle" for t in on_floor)
        context = f"{people} people, {forklifts} forklifts and {vehicles} other vehicles tracked on {key}"
        self._focus(plant_id, floor_id)
        answer = self.vision(self.perception.frame_jpeg(key), question, context)
        return {"plant": plant_id, "floor": floor_id, "answer": answer}

    def focus_view(self, plant: str, floor: Optional[str] = None) -> dict[str, Any]:
        plant_id, floor_id, error = self._resolve(plant, floor)
        if error or not plant_id:
            return {"error": error or "focus_view needs a plant"}
        self._focus(plant_id, floor_id)
        return {"ok": True, "plant": plant_id, "plant_name": self.site.plant(plant_id).name, "floor": floor_id}

    def show_event(self, event_id: int) -> dict[str, Any]:
        event = self.store.get(int(event_id))
        if event is None:
            return {"error": f"no event with id {event_id}"}
        self.session.last_event_id = event.id
        self.session.focus_plant, self.session.focus_floor = event.plant, event.floor
        self.pending_ui.append(UiMsg(action="panel", plant=event.plant, floor=event.floor, event_ids=[event.id],
                                     content={"kind": "event", "event": event.model_dump()}))
        self.pending_ui.append(UiMsg(action="highlight", event_ids=[event.id]))
        return self._brief(event)

    def write_report(self, event_id: int) -> dict[str, Any]:
        event = self.store.get(int(event_id))
        if event is None:
            return {"error": f"no event with id {event_id}"}
        plant = self.site.plant(event.plant)
        report = {
            "event_id": event.id,
            "what": f"{event.type.replace('_', ' ').capitalize()}. {event.summary}",
            "where": f"{plant.name if plant else event.plant}, floor {event.floor}, camera {event.camera_id}, "
                     f"position {event.x:.1f} m, {event.y:.1f} m",
            "when": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(event.ts)),
            "who": self._who(event),
            "severity": SEVERITY_NAME[event.severity],
            "action": RECOMMENDED_ACTION[event.type],
        }
        self.session.last_event_id = event.id
        self.pending_ui.append(UiMsg(action="panel", plant=event.plant, floor=event.floor, event_ids=[event.id],
                                     content={"kind": "report", "report": report, "event": event.model_dump()}))
        return report

    def identify_person(self, event_id: Optional[int] = None, name: Optional[str] = None) -> dict[str, Any]:
        if self.people is None:
            return {"error": "there is no employee directory on this system"}
        now = self.clock()
        if name:
            employee = self.people.directory.find(str(name))
            if employee is None:
                return {"error": f"no employee called {name}"}
            latest = self.store.query(person_id=employee.id, limit=1)
            event = latest[0] if latest else None
        else:
            wanted = event_id if event_id is not None else self.session.last_event_id
            event = self.store.get(int(wanted)) if wanted is not None else self._latest_identified_event()
            if event is None:
                return {"error": "there is no recent event with an identified person"}
            employee = self.people.directory.get(event.person_id)
            if employee is None:
                return {"error": f"event {event.id} does not involve one identified person"}

        clock_time = lambda ts: time.strftime("%H:%M:%S", time.localtime(ts))  # noqa: E731
        incident = None
        if event:
            incident = {**self._brief(event), "zone": None, "authorised": None, "entered_at": None, "left_at": None,
                        "seconds_in_zone": None, "still_inside": None}
            visit = self.people.visits.get(event.id)
            if visit:
                incident.update(
                    zone=visit.zone_id, authorised=f"{visit.zone_key}/{visit.zone_id}" in employee.authorised_zones,
                    entered_at=clock_time(visit.entered), left_at=clock_time(visit.left) if visit.left else None,
                    seconds_in_zone=round((visit.left or now) - visit.entered), still_inside=visit.left is None)
        others = [e for e in self.store.query(person_id=employee.id, since=now - 24 * 3600)
                  if event is None or e.id != event.id]
        place = self.people.badges.locate(employee.id, self.live_tracks())
        location = None
        if place:
            plant_id, floor_id = split_zone_key(place[0])
            location = {"plant": plant_id, "plant_name": self.site.plant(plant_id).name, "floor": floor_id,
                        "x": round(place[1], 1), "y": round(place[2], 1)}
        first_seen = self.people.badges.first_seen.get(employee.id)
        result = {
            "employee": employee.model_dump(),
            "incident": incident,
            "now": location,
            "on_camera_since": clock_time(first_seen) if first_seen else None,
            "other_incidents_24h": len(others),
            "recent_incidents": [self._brief(e) for e in others[:5]],
            "source": SOURCE,
        }
        if event:
            self.session.last_event_id = event.id
        plant_id, floor_id = (location["plant"], location["floor"]) if location else (
            (event.plant, event.floor) if event else (None, None))
        if plant_id:
            self._focus(plant_id, floor_id)
        self.pending_ui.append(UiMsg(action="panel", event_ids=[event.id] if event else [],
                                     content={"kind": "person", "person": result,
                                              "event": event.model_dump() if event else None}))
        if event:
            self.pending_ui.append(UiMsg(action="highlight", event_ids=[event.id]))
        return result

    # ---- helpers ----

    def _latest_identified_event(self) -> Optional[Event]:
        """Newest event of the last 10 minutes that names a person, preferring the floor in view."""
        recent = [e for e in self.store.query(since=self.clock() - OPEN_EVENT_MINUTES * 60) if e.person_id]
        in_view = [e for e in recent if e.plant == self.session.focus_plant
                   and self.session.focus_floor in (None, e.floor)]
        return (in_view or recent or [None])[0]

    def _who(self, event: Event) -> str:
        employee = self.people.directory.get(event.person_id) if self.people else None
        if employee is None:
            return ", ".join(f"track {i}" for i in event.track_ids) + " (anonymous track ids, no identification)"
        return (f"{employee.name} ({employee.id}), {employee.role}, {employee.department}, {employee.shift} shift; "
                f"supervisor {employee.supervisor}. Identified by {SOURCE}.")

    def _focus(self, plant_id: str, floor_id: Optional[str]) -> None:
        self.session.focus_plant, self.session.focus_floor = plant_id, floor_id
        self.pending_ui.append(UiMsg(action="focus", plant=plant_id, floor=floor_id))

    def _brief(self, e: Event) -> dict[str, Any]:
        plant = self.site.plant(e.plant)
        return {"id": e.id, "time": time.strftime("%H:%M:%S", time.localtime(e.ts)), "plant": e.plant,
                "plant_name": plant.name if plant else e.plant, "floor": e.floor, "type": e.type,
                "severity": e.severity, "summary": e.summary}

    def _resolve(self, plant: Optional[str], floor: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Normalise what a model passes ("Plant 2", "p2", "3") to ids: (plant id, floor id, error)."""
        plant_id = floor_id = None
        if plant and "/" in str(plant) and not floor:
            plant, floor = split_zone_key(str(plant))
        if plant:
            wanted = str(plant).strip().lower()
            digits = re.sub(r"\D", "", wanted)
            for p in self.site.plants:
                if wanted in (p.id.lower(), p.name.lower()) or (digits and digits == re.sub(r"\D", "", p.id)):
                    plant_id = p.id
                    break
            if plant_id is None:
                return None, None, f"unknown plant {plant}"
        if floor:
            wanted = str(floor).strip().lower()
            digits = re.sub(r"\D", "", wanted)
            floors = self.site.plant(plant_id).floors if plant_id else [f for _, f in self.site.floors()]
            for f in floors:
                if wanted == f.id.lower() or (digits and digits == re.sub(r"\D", "", f.id)):
                    floor_id = f.id
                    break
            if floor_id is None:
                return None, None, f"unknown floor {floor}"
        return plant_id, floor_id, None

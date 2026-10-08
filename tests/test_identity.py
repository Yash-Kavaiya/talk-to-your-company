"""The "who is this person" use case: synthetic directory, simulated badge feed, identify_person, timing."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.agent.llm import MockLLM
from app.agent.loop import Agent
from app.agent.tools import Session, Tools
from app.config import DEFAULT_EMPLOYEES_PATH, ConfigError
from app.events.rules import RulesEngine
from app.identity import BadgeFeed, People, load_directory
from app.main import create_app
from app.perception.base import Track
from app.perception.mock import MockPerception
from app.protocol import parse_server_message

NOW = 1_000_000.0


@pytest.fixture
def directory():
    return load_directory(DEFAULT_EMPLOYEES_PATH)


def person(i, zone, x, y):
    return Track(id=i, zone=zone, cls="person", x=x, y=y)


def test_directory_is_synthetic_and_covers_every_floor(site, directory):
    assert "SYNTHETIC" in DEFAULT_EMPLOYEES_PATH.read_text(encoding="utf-8")
    for key in site.zone_keys():
        assert sum(e.home == key for e in directory.employees) >= 5, key
    zones = {f"{p.id}/{f.id}/{z.id}" for p, f in site.floors() for z in f.zones if z.type == "restricted"}
    assert {z for e in directory.employees for z in e.authorised_zones} <= zones
    assert directory.get("E1006").name == "Arjun Mehta" and directory.get("nope") is None
    assert directory.find("where is arjun mehta now").id == "E1006"
    assert directory.find("tell me about Chloe").id == "E1007"
    assert directory.find("what about e1010?").id == "E1010"
    assert directory.find("who is this person") is None


def test_bad_directory_is_rejected(tmp_path):
    path = tmp_path / "employees.yaml"
    path.write_text("employees: [{id: E1, name: A}]")
    with pytest.raises(ConfigError):
        load_directory(path)
    with pytest.raises(ConfigError):
        load_directory(tmp_path / "missing.yaml")


def test_badge_feed_assigns_home_employees_and_survives_tracker_id_changes(directory):
    badges = BadgeFeed(directory)
    badges.update({"P1/F2": [person(8, "P1/F2", 10, 19), person(9, "P1/F2", 30, 5), Track(10, "P1/F2", "forklift", 1, 1)]}, 0.0)
    assert badges.employee_for(8).id == "E1006" and badges.employee_for(9).id == "E1007"
    assert badges.employee_for(10) is None  # vehicles carry no badge
    assert badges.locate("E1006", {"P1/F2": [person(8, "P1/F2", 10, 19)]}) == ("P1/F2", 10, 19)
    # the tracker loses track 8 and finds the same person again as track 55, two metres away
    badges.update({"P1/F2": [person(9, "P1/F2", 30, 5)]}, 1.0)
    badges.update({"P1/F2": [person(9, "P1/F2", 30, 5), person(55, "P1/F2", 12, 19)]}, 2.0)
    assert badges.employee_for(55).id == "E1006" and badges.employee_for(8) is None
    # everybody leaves; after a while the next person on the floor is most likely the last one back
    badges.update({"P1/F2": []}, 3.0)
    badges.update({"P1/F2": []}, 30.0)
    badges.update({"P1/F2": [person(70, "P1/F2", 35, 20)]}, 31.0)
    assert badges.employee_for(70).id in ("E1006", "E1007")
    assert badges.first_seen["E1006"] == 0.0
    assert badges.locate("E1010", {"P1/F2": []}) is None


# ---- hub: events name the person, authorised people raise nothing, visits are timed

@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def enter_zone(hub, track_id, now, x=12.0, y=20.0):
    """Put one person into P1/F2's restricted zone and evaluate the rules past the dwell time."""
    hub.latest_tracks = {"P1/F2": [person(track_id, "P1/F2", x, y)]}
    hub.people.badges.update(hub.latest_tracks, now)
    events = []
    for t in (now, now + 2.5):
        for finding in hub.rules.evaluate("P1/F2", hub.latest_tracks["P1/F2"], t):
            events.append(hub._record("P1/F2", finding, t))
    return events


def test_restricted_zone_event_names_the_person_and_times_the_visit(client):
    hub = client.app.state.hub
    hub.people = People(hub.people.directory)
    hub.rules = RulesEngine(hub.site)
    (event,) = enter_zone(hub, 901, NOW)
    assert event.person_id == "E1006" and event.type == "restricted_zone"
    assert event.summary == "Arjun Mehta (E1006) has been inside restricted zone z2 for over 2 s, without authorisation."
    assert hub.store.get(event.id).person_id == "E1006"
    visit = hub.people.visits[event.id]
    assert visit.entered == NOW and visit.left is None
    hub.rules.evaluate("P1/F2", [person(901, "P1/F2", 30, 5)], NOW + 40)  # walked out
    hub.people.close_visits(hub.rules, NOW + 40)
    assert visit.left == NOW + 40


def test_authorised_person_raises_no_event(client):
    hub = client.app.state.hub
    hub.people = People(hub.people.directory)
    hub.rules = RulesEngine(hub.site)
    hub.people.badges._active[902] = "E1010"  # Mateo Alvarez, maintenance, authorised for P1/F2/z2
    hub.people.badges._place[902] = ("P1/F2", 12.0, 20.0, NOW)
    assert enter_zone(hub, 902, NOW) == [None]
    assert hub.people.visits == {}


# ---- the tool

@pytest.fixture
def tools(site, store, directory):
    people = People(directory)
    live = {key: [] for key in site.zone_keys()}
    live["P1/F2"] = [person(8, "P1/F2", 30.0, 5.0)]
    people.badges.update(live, NOW - 300)
    event = store.add(ts=NOW - 60, plant="P1", floor="F2", camera_id="cam_p1f2", type="restricted_zone", severity=2,
                      track_ids=[8], x=12.0, y=20.0, summary="Arjun Mehta (E1006) has been inside restricted zone z2.",
                      person_id="E1006")
    people.open_visit(event.id, "P1/F2", 8, "z2", entered=NOW - 62)
    people.visits[event.id].left = NOW - 20
    store.add(ts=NOW - 7200, plant="P1", floor="F2", camera_id="cam_p1f2", type="no_helmet", severity=2,
              track_ids=[8], x=1.0, y=1.0, summary="Arjun Mehta (E1006) is not wearing a helmet.", person_id="E1006")
    store.add(ts=NOW - 30, plant="P2", floor="F1", camera_id="cam_p2f1", type="crowding", severity=1,
              track_ids=[1, 2, 3, 4, 5], x=1.0, y=1.0, summary="5 people gathered within 3 m.")
    return Tools(site, store, MockPerception(site), lambda: live, lambda *a: "", Session(), clock=lambda: NOW,
                 people=people)


def test_identify_person_from_the_last_event(tools):
    tools.session.last_event_id = 1
    r = tools.identify_person()
    assert r["employee"]["name"] == "Arjun Mehta" and r["employee"]["supervisor"] == "Sofia Marchetti"
    assert r["incident"]["zone"] == "z2" and r["incident"]["authorised"] is False
    assert r["incident"]["seconds_in_zone"] == 42 and r["incident"]["still_inside"] is False
    assert r["incident"]["entered_at"] and r["incident"]["left_at"]
    assert r["now"] == {"plant": "P1", "plant_name": "Plant 1", "floor": "F2", "x": 30.0, "y": 5.0}
    assert r["other_incidents_24h"] == 1 and r["recent_incidents"][0]["type"] == "no_helmet"
    assert "no face recognition" in r["source"] and r["on_camera_since"]
    focus, panel, highlight = tools.pending_ui
    assert (focus.action, focus.plant, focus.floor) == ("focus", "P1", "F2")
    assert panel.content["kind"] == "person" and panel.content["event"]["id"] == 1 and highlight.event_ids == [1]


def test_identify_person_without_context_by_name_and_errors(tools):
    assert tools.identify_person()["incident"]["id"] == 1  # newest event that names somebody, not the crowding one
    by_name = tools.identify_person(name="chloe")
    assert by_name["employee"]["id"] == "E1007" and by_name["incident"] is None and by_name["now"] is None
    assert "error" in tools.identify_person(event_id=3)  # crowding involves no single person
    assert "error" in tools.identify_person(name="Zaphod")
    assert "error" in tools.identify_person(event_id=99)
    tools.people = None
    assert "error" in tools.identify_person()


def test_report_names_the_person(tools):
    assert tools.write_report(1)["who"].startswith("Arjun Mehta (E1006), Line operator, Assembly")
    assert "anonymous track ids" in tools.write_report(3)["who"]


# ---- the conversation

def ask(agent, text):
    sent = []

    async def send_ui(ui):
        sent.append(ui)

    return asyncio.run(agent.ask(text, send_ui)), sent


def test_the_whole_story_in_conversation(site, tools, directory):
    agent = Agent(MockLLM(site, directory), tools, site)
    answer, _ = ask(agent, "Any safety issues on Plant 1 in the last ten minutes?")
    assert "Arjun Mehta" in answer
    answer, ui = ask(agent, "Who is this person?")
    assert answer == ("That is Arjun Mehta, line operator in Assembly on the day shift, badge E1006. Arjun Mehta entered "
                      "restricted zone z2 on Plant 1, floor 2 at " + time.strftime("%H:%M", time.localtime(NOW - 62))
                      + " without authorisation and stayed 42 seconds.")
    assert any(u.action == "panel" and u.content["kind"] == "person" for u in ui)
    assert ask(agent, "How long was he in there?")[0].endswith("stayed 42 seconds.")
    assert ask(agent, "Has this person done this before?")[0].startswith("Arjun Mehta has 1 other incident in the last 24 hours.")
    assert ask(agent, "Is she authorised, and who is the supervisor?")[0] == (
        "Arjun Mehta reports to Sofia Marchetti and is authorised for no restricted zones.")
    assert ask(agent, "Where is Arjun Mehta now?")[0].startswith("Arjun Mehta is on Plant 1, floor 2 right now.")
    assert ask(agent, "Where is Chloe?")[0] == "I can't see Chloe Dubois on any camera right now."
    answer, ui = ask(agent, "Write the incident report")
    assert "event 1" in answer and ui[-1].content["report"]["who"].startswith("Arjun Mehta")
    assert ask(agent, "What is the worker near the conveyor doing right now?")[1][0].action == "focus"  # still vision


def test_mock_scenario_on_the_demo_floor_ends_with_a_name_over_the_socket(client):
    """Mock mode stages the restricted-zone scenario on the configured floor; asking "who" names the person."""
    hub = client.app.state.hub
    assert hub.site.demo_restricted_floor == "P1/F2"
    with client.websocket_connect("/ws") as ws:
        for _ in range(2000):
            message = parse_server_message(ws.receive_text())
            if message.type == "event" and message.event.type == "restricted_zone":
                break
        event = message.event
        assert (event.plant, event.floor) == ("P1", "F2") and event.person_id
        name = hub.people.directory.get(event.person_id).name
        assert name in event.summary
        ws.send_json({"type": "select_event", "event_id": event.id})
        ws.send_json({"type": "text_query", "text": "Who is this person?"})
        panel = answer = None
        while not (panel and answer):
            message = parse_server_message(ws.receive_text())
            if message.type == "ui" and message.action == "panel" and message.content["kind"] == "person":
                panel = message.content["person"]
            if message.type == "answer" and answer is None:
                answer = message.text
        assert panel["employee"]["name"] == name and panel["incident"]["entered_at"]
        assert answer.startswith(f"That is {name},")

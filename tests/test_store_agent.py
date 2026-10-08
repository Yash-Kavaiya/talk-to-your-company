"""T11 store, T12 tools, T13 agent loop with MockLLM, T24 report."""
import asyncio
import json

import pytest

from app.agent.llm import LLMReply, MockLLM, ToolCall, _to_chat, parse_tool_calls
from app.agent.loop import Agent, split_sentences
from app.agent.tools import TOOL_SCHEMAS, Session, Tools
from app.backends import helmet_answer
from app.events.store import EventStore
from app.perception.base import Track
from app.perception.mock import MockPerception

NOW = 1_000_000.0


def add(store, minutes_ago, plant="P1", floor="F1", type="near_miss", **extra):
    values = dict(ts=NOW - minutes_ago * 60, plant=plant, floor=floor, camera_id=f"cam_{plant}{floor}".lower(),
                  type=type, severity=3, track_ids=[1, 2], x=3.0, y=4.0, summary="Person 1 came close to forklift 2.")
    return store.add(**{**values, **extra})


# ---- T11 ----

def test_store_persists_and_queries(tmp_path):
    path = tmp_path / "db" / "events.db"
    store = EventStore(path)
    a = add(store, 30, plant="P1", floor="F1", type="near_miss")
    b = add(store, 5, plant="P1", floor="F2", type="crowding")
    c = add(store, 1, plant="P2", floor="F2", type="near_miss", snapshot_path="/snapshots/x.svg")
    assert [a.id, b.id, c.id] == [1, 2, 3]
    assert [e.id for e in store.query()] == [3, 2, 1]  # newest first
    assert [e.id for e in store.query(plant="P1")] == [2, 1]
    assert [e.id for e in store.query(floor="F2")] == [3, 2]
    assert [e.id for e in store.query(type="near_miss")] == [3, 1]
    assert [e.id for e in store.query(since=NOW - 600)] == [3, 2]
    assert [e.id for e in store.query(since=NOW - 3600, until=NOW - 240)] == [2, 1]
    assert [e.id for e in store.query(plant="P1", type="near_miss", since=NOW - 600)] == []
    assert [e.id for e in store.query(limit=1)] == [3]
    store.set_snapshot(1, "/snapshots/evt_1.svg")
    store.close()
    reopened = EventStore(path)
    assert reopened.get(1) == a.model_copy(update={"snapshot_path": "/snapshots/evt_1.svg"})
    assert reopened.get(3).track_ids == [1, 2] and reopened.get(99) is None


# ---- T12 ----

@pytest.fixture
def tools(site, store):
    live = {key: [] for key in site.zone_keys()}
    live["P2/F3"] = [Track(1, "P2/F3", "person", 1, 1), Track(2, "P2/F3", "person", 2, 2), Track(3, "P2/F3", "forklift", 5, 5)]
    live["P1/F1"] = [Track(4, "P1/F1", "person", 1, 1), Track(5, "P1/F1", "vehicle", 2, 2)]
    seen = []

    def vision(image, question, context):
        seen.append((image, question, context))
        return "A worker is stacking boxes."

    t = Tools(site, store, MockPerception(site), lambda: live, vision, Session(), clock=lambda: NOW)
    t.vision_calls = seen
    return t


def test_query_events_filters_and_highlights(tools, store):
    add(store, 30)
    add(store, 5, floor="F2", type="crowding")
    newest = add(store, 1, plant="P2")
    r = tools.query_events()
    assert r["count"] == 2 and r["by_type"] == {"near_miss": 1, "crowding": 1}
    assert r["events"][0]["id"] == newest.id and r["events"][0]["plant_name"] == "Plant 2"
    assert tools.session.last_event_id == newest.id
    assert tools.pending_ui[-1].action == "highlight" and tools.pending_ui[-1].event_ids == [3, 2]
    assert tools.query_events(plant="Plant 1", minutes_back=60)["count"] == 2
    assert tools.query_events(plant="p1", floor="2")["events"][0]["type"] == "crowding"
    assert tools.query_events(type="no_helmet")["count"] == 0
    assert "error" in tools.query_events(plant="P9")


def test_live_state_counts(tools, store):
    add(store, 2, plant="P2", floor="F3")
    add(store, 20, plant="P2", floor="F3")  # too old to be open
    r = tools.live_state()
    assert len(r["floors"]) == 6
    assert r["totals"]["P2"] == {"plant_name": "Plant 2", "people": 2, "vehicles": 1, "open_events": 1}
    assert r["totals"]["P1"]["people"] == 1 and r["totals"]["P1"]["vehicles"] == 1
    one = tools.live_state(plant="P2", floor="F3")["floors"]
    assert len(one) == 1 and one[0]["people"] == 2
    assert len(tools.live_state(floor="F1")["floors"]) == 2


def test_look_asks_vision_on_that_floor_and_focuses(tools):
    r = tools.look("Plant 2", "floor 3", "What is the worker doing?")
    assert r == {"plant": "P2", "floor": "F3", "answer": "A worker is stacking boxes."}
    image, question, context = tools.vision_calls[0]
    assert image is None and question == "What is the worker doing?" and "2 people, 1 forklifts" in context
    assert tools.pending_ui[0].model_dump(include={"action", "plant", "floor"}) == {"action": "focus", "plant": "P2", "floor": "F3"}
    assert "error" in tools.look("P2", "F9", "x")


def test_focus_view(tools):
    assert tools.focus_view("2", "3")["floor"] == "F3"
    assert tools.focus_view("P1")["floor"] is None
    assert [(u.plant, u.floor) for u in tools.pending_ui] == [("P2", "F3"), ("P1", None)]
    assert (tools.session.focus_plant, tools.session.focus_floor) == ("P1", None)
    assert "error" in tools.focus_view("Plant 7")


def test_show_event_and_write_report(tools, store):
    event = add(store, 3, plant="P2", floor="F1")
    assert tools.show_event(event.id)["id"] == event.id
    panel, highlight = tools.pending_ui
    assert panel.action == "panel" and panel.content["kind"] == "event" and panel.content["event"]["id"] == event.id
    assert highlight.event_ids == [event.id] and tools.session.focus_floor == "F1"
    report = tools.write_report(event.id)
    assert set(report) == {"event_id", "what", "where", "when", "who", "severity", "action"}
    assert report["severity"] == "high" and "Plant 2" in report["where"] and "track 1" in report["who"]
    assert tools.pending_ui[-1].content["kind"] == "report"
    assert "error" in tools.show_event(99) and "error" in tools.write_report(99)


def test_call_dispatch_and_bad_arguments(tools):
    assert {s["name"] for s in TOOL_SCHEMAS} == {"query_events", "live_state", "look", "focus_view", "show_event", "write_report",
                                                "identify_person"}
    assert "floors" in tools.call("live_state", {})
    assert "error" in tools.call("nope", {})
    assert "error" in tools.call("focus_view", {"colour": "red"})
    assert "error" in tools.call("show_event", {"event_id": "abc"})


# ---- T13 ----

def ask(agent, text):
    sent = []

    async def send_ui(ui):
        sent.append(ui)

    return asyncio.run(agent.ask(text, send_ui)), sent


@pytest.fixture
def agent(site, tools):
    tools.vision = MockLLM(site).look
    return Agent(MockLLM(site), tools, site)


def test_navigation_focuses_and_answers(agent):
    answer, ui = ask(agent, "Show me Plant 2, floor 3.")
    assert [(u.action, u.plant, u.floor) for u in ui] == [("focus", "P2", "F3")]
    assert answer == "Here is Plant 2, floor 3. It has 2 people, 1 vehicle and no open events."
    assert ask(agent, "take me to the second floor of plant one")[1][0].floor == "F2"


def test_status_of_both_plants(agent):
    answer, ui = ask(agent, "Give me a status of both plants")
    assert answer == ("Plant 1 has 1 person, 1 vehicle and no open events. "
                      "Plant 2 has 2 people, 1 vehicle and no open events.")
    assert ui == []


def test_history_question_highlights_events(agent, store):
    add(store, 4, plant="P1", floor="F2", type="restricted_zone", summary="Person 9 is in zone z2.")
    add(store, 40, plant="P1")
    answer, ui = ask(agent, "Any safety issues on Plant 1 in the last ten minutes?")
    assert answer.startswith("I found 1 safety event on Plant 1 in the last 10 minutes: 1 restricted zone entry.")
    assert "Person 9 is in zone z2." in answer
    assert [u.action for u in ui] == ["focus", "highlight"] and ui[1].event_ids == [1]
    assert ask(agent, "any near misses in the last hour?")[0].startswith(
        "I found 1 safety event in the last 60 minutes: 1 near miss.")
    assert ask(agent, "any helmet violations on plant 2 today?")[0] == "I can't see any safety events on Plant 2 in the last 24 hours."


def test_that_resolves_to_last_event_and_report(agent, store):
    assert "don't have an event selected" in ask(agent, "Write the incident report for that")[0]
    add(store, 2, plant="P2", floor="F1")
    ask(agent, "any safety issues?")
    answer, ui = ask(agent, "Write the incident report for that")
    assert answer == "The incident report for event 1 is in the side panel. Severity is high."
    assert ui[-1].action == "panel" and ui[-1].content["report"]["event_id"] == 1
    answer, ui = ask(agent, "show me event 1")
    assert answer.startswith("Event 1 is a near miss on Plant 2, floor 1") and ui[0].action == "panel"


def test_live_vision_uses_current_view(agent):
    assert ask(agent, "What is the worker near the conveyor doing right now?")[0] == "Which plant and floor should I look at?"
    ask(agent, "show me plant 2 floor 3")
    answer, ui = ask(agent, "What is the worker near the conveyor doing right now?")
    assert "2 people, 1 forklifts" in answer and "mocked" in answer
    assert (ui[0].plant, ui[0].floor) == ("P2", "F3")
    assert "P1/F1" in ask(agent, "what is the person on plant 1 floor 1 wearing?")[0]


@pytest.mark.parametrize("question", ["What is the weather in Paris?", "Who won the match yesterday?", "Tell me a joke"])
def test_out_of_scope_is_honest(agent, question):
    answer, ui = ask(agent, question)
    assert answer.startswith("I can't see that") and ui == []


def test_history_is_capped_at_six_turns(agent):
    for i in range(9):
        ask(agent, f"status please {i}")
    history = agent.tools.session.history
    assert len(history) == 12 and history[0]["content"] == "status please 3"


def test_loop_stops_after_three_tool_rounds(site, tools):
    class Stubborn:
        name = "stub"
        tool_lists = []

        def chat(self, messages, tool_schemas):
            self.tool_lists.append(len(tool_schemas))
            if tool_schemas:
                return LLMReply(tool_calls=[ToolCall("live_state", {})])
            return LLMReply(text="Done.")

    llm = Stubborn()
    assert ask(Agent(llm, tools, site), "loop forever")[0] == "Done."
    assert llm.tool_lists == [7, 7, 7, 0]


# ---- helpers used by the local backends ----

def test_parse_tool_calls_and_chat_conversion():
    text = 'ok <tool_call>{"name": "focus_view", "arguments": {"plant": "P2"}}</tool_call>\n<tool_call>broken</tool_call>'
    calls, rest = parse_tool_calls(text)
    assert calls == [ToolCall("focus_view", {"plant": "P2"})] and rest == "ok"
    assert parse_tool_calls("Plant 1 is quiet.") == ([], "Plant 1 is quiet.")
    chat = _to_chat([
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "status"},
        {"role": "assistant", "content": "", "tool_calls": [{"name": "live_state", "arguments": {}}]},
        {"role": "tool", "name": "live_state", "content": json.dumps({"floors": []})},
        {"role": "tool", "name": "focus_view", "content": "{}"},
    ], TOOL_SCHEMAS)
    assert [m["role"] for m in chat] == ["system", "user", "assistant", "user"]
    assert "write_report" in chat[0]["content"][0]["text"]
    assert parse_tool_calls(chat[2]["content"][0]["text"])[0] == [ToolCall("live_state", {})]
    assert chat[3]["content"][0]["text"].count("<tool_response") == 2


def test_split_sentences_and_helmet_answer():
    assert split_sentences("Plant 1 has 2.5 people. It is fine! Ok?") == ["Plant 1 has 2.5 people.", "It is fine!", "Ok?"]
    assert split_sentences("  ") == []
    assert (helmet_answer("Yes."), helmet_answer(" no"), helmet_answer("maybe"), helmet_answer(None)) == (True, False, None, None)


def test_mock_llm_passes_the_tool_calling_set(site):
    """T19's 15 questions: the fallback router must clear the same bar as the real model."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("eval_tool_calling", Path(__file__).parent.parent / "scripts" / "eval_tool_calling.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = module.score(MockLLM(site), site)
    assert len(rows) == 15
    assert [q for q, _, _, correct in rows if not correct] == []

"""T04 and T14 integration over /ws in mock mode, T21-T23 audio path, T26 metrics, T27 fallback."""
import base64
import time

import pytest
from fastapi.testclient import TestClient

from app.backends import build_backends
from app.config import Settings
from app.main import create_app
from app.metrics import Metrics
from app.protocol import parse_server_message
from app.voice.asr import MockASR, wav_duration
from app.voice.tts import MockTTS


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def read_until(ws, wanted, limit=200):
    """Messages up to and including the first of type `wanted` (state and metrics keep flowing in between)."""
    seen = []
    for _ in range(limit):
        seen.append(parse_server_message(ws.receive_text()))
        if seen[-1].type == wanted:
            return seen
    raise AssertionError(f"no {wanted} message in {[m.type for m in seen]}")


def query(ws, text):
    """Send a text query; returns (ui messages, answer text, audio messages)."""
    ws.send_json({"type": "text_query", "text": text})
    messages = []
    while not (messages and messages[-1].type == "audio" and messages[-1].last):
        messages.append(parse_server_message(ws.receive_text()))
    assert [m.text for m in messages if m.type == "transcript"] == [text]
    answers = [m for m in messages if m.type == "answer"]
    assert answers[-1].done and not any(a.done for a in answers[:-1])
    return ([m for m in messages if m.type == "ui"], " ".join(a.text for a in answers),
            [m for m in messages if m.type == "audio"])


def test_ws_sends_site_then_state_at_5hz_and_metrics(client):
    with client.websocket_connect("/ws") as ws:
        first = parse_server_message(ws.receive_text())
        assert first.type == "site" and len(first.site.plants) == 2
        state = read_until(ws, "state")[-1]
        assert set(state.zones) == {"P1/F1", "P1/F2", "P1/F3", "P2/F1", "P2/F2", "P2/F3"}
        assert all(tracks for tracks in state.zones.values())
        started = time.monotonic()
        states = [m for m in (parse_server_message(ws.receive_text()) for _ in range(14)) if m.type == "state"]
        elapsed = time.monotonic() - started
        assert len(states) / elapsed >= 4.0  # AC1.2: at least 5 updates per second, with timing slack
        metrics = read_until(ws, "metrics")[-1]
        assert set(metrics.fps) == {f"cam_p{p}f{f}" for p in (1, 2) for f in (1, 2, 3)}
        assert metrics.mem_gb is None or metrics.mem_gb > 0


def test_text_query_show_me_plant_2_floor_3(client):
    with client.websocket_connect("/ws") as ws:
        read_until(ws, "state")
        ui, answer, audio = query(ws, "show me plant 2 floor 3")
        assert [(u.action, u.plant, u.floor) for u in ui] == [("focus", "P2", "F3")]
        assert answer.startswith("Here is Plant 2, floor 3.")
        assert [a.seq for a in audio] == list(range(len(audio)))
        assert all(wav_duration(base64.b64decode(a.wav_b64)) > 0 for a in audio)
        latencies = [read_until(ws, "metrics")[-1].voice_latency_ms for _ in range(3)]
        assert latencies[-1] is not None and latencies[-1] < 5000  # AC3.3 hard limit


def test_golden_path_questions_each_yield_an_answer(client):
    hub = client.app.state.hub
    event = hub.store.add(ts=time.time() - 60, plant="P1", floor="F2", camera_id="cam_p1f2", type="near_miss",
                          severity=3, track_ids=[1, 6], x=5.0, y=6.0, summary="Person 1 came within 1.2 m of forklift 6.")
    with client.websocket_connect("/ws") as ws:
        read_until(ws, "state")
        _, answer, _ = query(ws, "Give me a status of both plants.")
        assert "Plant 1 has" in answer and "Plant 2 has" in answer
        ui, _, _ = query(ws, "Show me Plant 2, floor 3.")
        assert ui[0].action == "focus"
        ui, answer, _ = query(ws, "Any safety issues in the last ten minutes?")
        assert "safety event" in answer and any(u.action == "highlight" and event.id in u.event_ids for u in ui)

        ws.send_json({"type": "select_event", "event_id": event.id})  # click a marker
        panel = read_until(ws, "ui")[-1]
        assert panel.action == "panel" and panel.content["event"]["summary"] == event.summary
        assert read_until(ws, "ui")[-1].action == "highlight"

        ui, answer, _ = query(ws, "What is the worker near the conveyor doing right now?")
        assert (ui[0].plant, ui[0].floor) == ("P1", "F2") and "P1/F2" in answer
        ui, answer, _ = query(ws, "Write the incident report.")
        assert ui[-1].content["kind"] == "report" and ui[-1].content["report"]["event_id"] == event.id
        _, answer, _ = query(ws, "What is the share price today?")
        assert answer.startswith("I can't see that")


def test_recent_events_are_replayed_on_connect_and_bad_messages_ignored(client):
    hub = client.app.state.hub
    hub.store.add(ts=time.time() - 30, plant="P2", floor="F1", camera_id="cam_p2f1", type="crowding", severity=1,
                  track_ids=[3], x=1.0, y=1.0, summary="5 people gathered.")
    hub.store.add(ts=time.time() - 3600, plant="P2", floor="F1", camera_id="cam_p2f1", type="crowding", severity=1,
                  track_ids=[3], x=1.0, y=1.0, summary="old")
    with client.websocket_connect("/ws") as ws:
        ws.send_text("garbage")
        ws.send_json({"type": "launch_rockets"})
        replayed = [m.event.summary for m in read_until(ws, "event")[-1:]]
        assert replayed == ["5 people gathered."]
        assert query(ws, "status")[1]  # still alive


def test_audio_query_is_transcribed_and_answered(client):
    wav = base64.b64encode(MockTTS().synthesize("x")).decode()
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "audio_query", "wav_b64": wav})
        transcript = read_until(ws, "transcript")[-1]
        assert transcript.text == "Give me a status of both plants." and transcript.final
        assert "Plant 1 has" in read_until(ws, "answer")[-1].text
        while not read_until(ws, "audio")[-1].last:
            pass
        ws.send_json({"type": "audio_query", "wav_b64": base64.b64encode(b"not a wav").decode()})
        assert "didn't catch that" in read_until(ws, "answer")[-1].text


def test_events_reach_the_browser_with_a_snapshot(client):
    """AC2.2: a scripted mock scenario becomes an `event` message, stored, with a snapshot that is served."""
    with client.websocket_connect("/ws") as ws:
        event = read_until(ws, "event", limit=1500)[-1].event
    assert client.app.state.hub.store.get(event.id).snapshot_path == event.snapshot_path
    response = client.get(event.snapshot_path)
    assert response.status_code == 200 and response.text.startswith("<svg")


def test_camera_view_of_a_floor(client):
    response = client.get("/api/camera/P2/F3")
    assert response.status_code == 200 and response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["cache-control"] == "no-store" and "cam_p2f3" in response.text
    assert client.get("/api/camera/P2/F9").status_code == 404


def test_browser_webcam_frames_are_shown_in_the_camera_view(client):
    jpeg = b"\xff\xd8\xff\xe0 fake jpeg body \xff\xd9"
    assert client.post("/api/camera/P1/F1/frame", content=jpeg).status_code == 204
    shown = client.get("/api/camera/P1/F1")
    assert shown.headers["content-type"] == "image/jpeg" and shown.content == jpeg
    assert client.post("/api/camera/P1/F1/frame", content=b"not an image").status_code == 400
    assert client.post("/api/camera/P1/F2/frame", content=jpeg).status_code == 204  # any camera can be taken over
    assert client.get("/api/camera/P1/F2").content == jpeg
    assert client.post("/api/camera/P9/F1/frame", content=jpeg).status_code == 404
    assert client.post("/api/camera/P1/F1/frame", content=jpeg + b"x" * 2_000_000).status_code == 413


def test_push_stream_goes_stale(monkeypatch):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    from app.perception import ingest

    stream = ingest.PushStream("cam")
    assert stream.latest() is None and not stream.push(b"junk")
    ok, data = cv2.imencode(".jpg", np.zeros((90, 160, 3), np.uint8))
    assert ok and stream.push(data.tobytes())
    assert stream.latest().shape == (720, 1280, 3)
    monkeypatch.setattr(ingest, "STALE_AFTER_S", -1.0)
    assert stream.latest() is None


def test_static_frontend_and_health(client):
    assert "Talk-to-your-Company" in client.get("/").text
    assert client.get("/src/main.js").status_code == 200
    assert client.get("/vendor/three/three.module.js").status_code == 200
    assert client.get("/api/health").json() == {
        "ok": True, "modes": {"perception": "mock", "llm": "mock", "asr": "mock", "tts": "mock"}}


def test_real_backends_fall_back_to_mocks(site, tmp_path):
    """NFR3: on a laptop nothing real can load (no videos, no CUDA, no voice), and the app still starts."""
    settings = Settings(perception="real", llm="local", asr="local", tts="local",
                        data_dir=tmp_path, models_dir=tmp_path / "models")
    backends = build_backends(settings, site)
    assert backends.modes == {k: "mock (fallback)" for k in ("perception", "llm", "asr", "tts")}
    assert backends.llm.name == backends.asr.name == backends.tts.name == "mock"
    with TestClient(create_app(settings)) as c, c.websocket_connect("/ws") as ws:
        assert query(ws, "status")[1]


def test_mock_voice_and_metrics():
    wav = MockTTS().synthesize("Hello there.")
    assert 0.1 < wav_duration(wav) < 0.5
    assert MockASR("fixed").transcribe(wav) == "fixed"
    with pytest.raises(ValueError):
        MockASR().transcribe(b"junk")
    metrics = Metrics()
    assert metrics.message({"cam": 10.0}).voice_latency_ms is None
    metrics.record_voice_latency(1.234)
    assert metrics.message({"cam": 10.0}).voice_latency_ms == 1234

"""T01 config loader and T02 protocol round trips."""
import pytest

from app import protocol as p
from app.config import ConfigError, Settings, load_site, zone_key


def test_sample_site_is_two_plants_by_three_floors(site):
    assert [pl.id for pl in site.plants] == ["P1", "P2"]
    assert all(len(pl.floors) == 3 for pl in site.plants)
    assert len({f.camera.id for _, f in site.floors()}) == 6
    assert site.zone_keys()[0] == zone_key("P1", "F1") == "P1/F1"
    assert site.floor("P2", "F3").size_m == (50, 30)
    assert site.floor("P9", "F1") is None
    assert all(f.objects for _, f in site.floors())
    assert [f.camera.source_kind() for _, f in site.floors()] == ["browser"] + ["file"] * 5
    conveyor = site.floor("P1", "F1").objects[0]
    assert conveyor.type == "conveyor" and conveyor.polygon(0.5)[0] == (7.5, 10.5)


@pytest.mark.parametrize("text", [
    "plants: [",  # not YAML
    "just a string",  # not a mapping
    "plants: []",  # no plants
    "plants: [{id: P1, name: A, floors: [{id: F1, size_m: [40], camera: {id: c, video: v}}]}]",  # bad size
    "plants: [{id: P1, name: A, floors: [{id: F1, size_m: [-1, 5], camera: {id: c, video: v}}]}]",
    "plants: [{id: P1, name: A, floors: [{id: F1, size_m: [4, 5], camera: {id: c, video: v}, colour: red}]}]",
    "plants: [{id: P1, name: A, floors: [{id: F1, size_m: [4, 5], camera: {id: c, video: v}},"
    " {id: F1, size_m: [4, 5], camera: {id: d, video: v}}]}]",  # duplicate floor
    "plants: [{id: P1, name: A, floors: [{id: F1, size_m: [4, 5], camera: {id: c, video: v},"
    " zones: [{id: z, type: restricted, polygon: [[0, 0], [9, 0], [9, 9]]}]}]}]",  # zone outside floor
    "plants: [{id: P1, name: A, floors: [{id: F1, size_m: [4, 5], camera: {id: c, video: v, homography: [[1, 0]]}}]}]",
    "plants: [{id: P1, name: A, floors: [{id: F1, size_m: [4, 5], camera: {id: c, video: v},"
    " objects: [{id: r, type: rack, rect: [3, 1, 2, 1]}]}]}]",  # equipment outside the floor
    "plants: [{id: P1, name: A, floors: [{id: F1, size_m: [4, 5], camera: {id: c, video: v},"
    " objects: [{id: r, type: robot, rect: [1, 1, 1, 1]}]}]}]",  # unknown equipment type
    "plants: [{id: P1, name: A, floors: [{id: F1, size_m: [4, 5], camera: {id: c, video: webcam}}]}]",  # no device
])
def test_malformed_site_is_rejected(tmp_path, text):
    path = tmp_path / "site.yaml"
    path.write_text(text)
    with pytest.raises(ConfigError):
        load_site(path)


def test_camera_sources():
    from pathlib import Path

    from app.config import Camera, resolve_video

    assert Camera(id="c", video="webcam:0").source_kind() == "webcam"
    assert Camera(id="c", video="webcam:/dev/video2").source_kind() == "webcam"
    assert Camera(id="c", video="clip.mp4").source_kind() == "file"
    assert resolve_video("clip.mp4", Path("/cache/videos")) == Path("/cache/videos/clip.mp4")
    assert resolve_video(str(Path("/data/clip.mp4").resolve()), Path("/cache/videos")) == Path("/data/clip.mp4").resolve()


def test_missing_site_file_is_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_site(tmp_path / "nope.yaml")


def test_run_modes_from_env(monkeypatch):
    monkeypatch.setenv("LLM", "local")
    monkeypatch.setenv("DATA_DIR", "/cache/ttyc")
    s = Settings.from_env()
    assert (s.perception, s.llm, s.asr, s.tts) == ("mock", "local", "mock", "mock")
    assert s.data_dir.as_posix() == "/cache/ttyc"
    monkeypatch.setenv("TTS", "cloud")
    with pytest.raises(ConfigError):
        Settings.from_env()


EVENT = p.Event(id=1, ts=1.5, plant="P1", floor="F2", camera_id="cam_p1f2", type="near_miss", severity=3,
                track_ids=[4, 9], x=3.0, y=4.0, snapshot_path="/snapshots/evt_1.svg", summary="close call")


def test_server_messages_round_trip(site):
    messages = [
        p.SiteMsg(site=site),
        p.StateMsg(ts=2.0, zones={"P1/F1": [p.TrackState(id=1, cls="person", x=1.0, y=2.0)]}),
        p.EventMsg(event=EVENT),
        p.UiMsg(action="focus", plant="P2", floor="F3"),
        p.UiMsg(action="panel", event_ids=[1], content={"kind": "event", "event": EVENT.model_dump()}),
        p.TranscriptMsg(text="hello", final=True),
        p.AnswerMsg(text="hi", done=True),
        p.AudioMsg(seq=0, wav_b64="AAAA", last=True),
        p.MetricsMsg(fps={"cam_p1f1": 10.0}, voice_latency_ms=1200, gpu_pct=None, mem_gb=3.2),
    ]
    for message in messages:
        assert p.parse_server_message(message.model_dump_json()) == message


def test_client_messages_round_trip():
    for message in (p.AudioQuery(wav_b64="AAAA"), p.TextQuery(text="status"), p.SelectEvent(event_id=3)):
        parsed = p.parse_client_message(message.model_dump_json())
        assert parsed == message and type(parsed) is type(message)


@pytest.mark.parametrize("raw", ['{"type": "nope"}', '{"type": "text_query"}', '{"type": "text_query", "text": ""}',
                                 "not json", '{"type": "select_event", "event_id": "x"}'])
def test_bad_client_messages_are_rejected(raw):
    with pytest.raises(p.ProtocolError):
        p.parse_client_message(raw)


def test_event_type_and_severity_are_validated():
    with pytest.raises(ValueError):
        p.Event(**{**EVENT.model_dump(), "type": "fire"})
    with pytest.raises(ValueError):
        p.Event(**{**EVENT.model_dump(), "severity": 4})

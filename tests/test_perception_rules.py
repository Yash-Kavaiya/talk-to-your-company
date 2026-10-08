"""T03 mock perception, T10 rules, plus the pure-Python tracker and mapper (T17, T18)."""
import pytest

from app.config import split_zone_key
from app.events.rules import (RulesEngine, closing_speed, find_crowding, find_near_misses, people_in_restricted,
                              point_in_polygon)
from app.perception.base import Track
from app.perception.mapper import FloorMapper, apply_homography, foot_point, solve_homography
from app.perception.mock import MockPerception
from app.perception.tracker import ByteTracker, Detection, iou


def person(i, x, y, vx=0.0, vy=0.0, helmet=True):
    return Track(id=i, zone="P1/F1", cls="person", x=x, y=y, vx=vx, vy=vy, helmet=helmet)


def forklift(i, x, y, vx=0.0, vy=0.0):
    return Track(id=i, zone="P1/F1", cls="forklift", x=x, y=y, vx=vx, vy=vy)


# ---- T03 ----

def test_mock_tracks_stay_inside_floor_and_events_fire(site):
    mock = MockPerception(site, seed=3, event_period=15.0)
    rules = RulesEngine(site)
    fired = []
    for step in range(3000):  # 10 simulated minutes at 5 Hz
        mock.advance(0.2)
        for key, tracks in mock.current().items():
            w, d = site.floor(*split_zone_key(key)).size_m
            assert tracks, key
            for t in tracks:
                assert 0 <= t.x <= w and 0 <= t.y <= d, (key, t)
            fired += [(key, f.type) for f in rules.evaluate(key, tracks, step * 0.2)]
    assert set(site.zone_keys()) == set(mock.current())
    assert {kind for _, kind in fired} == {"near_miss", "restricted_zone", "no_helmet", "crowding"}
    assert len(fired) < 120  # scripted scenarios plus a little ambient noise, not a flood


def test_mock_is_deterministic_and_snapshots(site):
    a, b = MockPerception(site, seed=5), MockPerception(site, seed=5)
    for _ in range(50):
        a.advance(0.2)
        b.advance(0.2)
    pos = lambda m: [(t.id, t.x, t.y) for ts in m.current().values() for t in ts]  # noqa: E731
    assert pos(a) == pos(b)
    data, extension = a.snapshot("P1/F1", [1])
    assert extension == "svg" and data.startswith(b"<svg") and b"SYNTHETIC" in data
    assert a.frame_jpeg("P1/F1") is None
    a.start()
    a.tracks()
    assert set(a.fps()) == {f.camera.id for _, f in site.floors()}


# ---- T10 ----

def test_point_in_polygon():
    square = [(0, 0), (5, 0), (5, 5), (0, 5)]
    assert point_in_polygon(2, 2, square)
    assert not point_in_polygon(6, 2, square)


def test_near_miss_needs_distance_and_closing_speed():
    approaching = [person(1, 0, 0, vx=1.0), forklift(2, 1.5, 0, vx=-1.0)]
    assert closing_speed(*approaching) == pytest.approx(2.0)
    found = find_near_misses(approaching)
    assert [f.track_ids for f in found] == [[1, 2]] and found[0].severity == 3
    assert not find_near_misses([person(1, 0, 0, vx=1.0), forklift(2, 5, 0, vx=-1.0)])  # too far
    assert not find_near_misses([person(1, 0, 0), forklift(2, 1.5, 0)])  # standing still
    assert not find_near_misses([person(1, 0, 0, vx=-1.0), forklift(2, 1.5, 0, vx=1.0)])  # moving apart
    assert not find_near_misses([person(1, 0, 0, vx=1.0), person(2, 1.5, 0, vx=-1.0)])  # two people


def test_restricted_zone_needs_two_seconds_and_fires_once_per_stay(site):
    rules = RulesEngine(site)  # P1/F1 has restricted z1 = (0,0)-(6,6)
    inside, outside = [person(1, 3, 3)], [person(1, 20, 20)]
    assert people_in_restricted(inside, site.floor("P1", "F1").zones)
    assert not rules.evaluate("P1/F1", inside, 0.0)
    assert not rules.evaluate("P1/F1", inside, 1.9)
    assert [f.type for f in rules.evaluate("P1/F1", inside, 2.1)] == ["restricted_zone"]
    assert not rules.evaluate("P1/F1", inside, 100.0)  # still the same stay
    assert not rules.evaluate("P1/F1", outside, 101.0)
    assert not rules.evaluate("P1/F1", inside, 102.0)
    assert [f.type for f in rules.evaluate("P1/F1", inside, 104.5)] == ["restricted_zone"]
    assert not rules.evaluate("P1/F1", [forklift(9, 3, 3)], 200.0)  # vehicles are not people


def test_crowding_is_more_than_n_people_in_radius():
    close = [person(i, 20 + 0.5 * i, 20) for i in range(5)]
    found = find_crowding(close)
    assert len(found) == 1 and found[0].track_ids == [0, 1, 2, 3, 4]
    assert not find_crowding(close[:4])
    assert not find_crowding([person(i, 5.0 * i, 20) for i in range(6)])


def test_no_helmet_fires_once_until_helmet_is_back(site):
    rules = RulesEngine(site)
    bare, covered, unchecked = [person(1, 20, 20, helmet=False)], [person(1, 20, 20)], [person(1, 20, 20, helmet=None)]
    assert not rules.evaluate("P1/F1", unchecked, 0.0)
    assert [f.type for f in rules.evaluate("P1/F1", bare, 1.0)] == ["no_helmet"]
    assert not rules.evaluate("P1/F1", bare, 50.0)
    assert not rules.evaluate("P1/F1", covered, 51.0)
    assert [f.type for f in rules.evaluate("P1/F1", bare, 90.0)] == ["no_helmet"]


def test_debounce_same_type_and_tracks_within_30_seconds(site):
    rules = RulesEngine(site)
    pair = [person(1, 20, 20, vx=1.0), forklift(2, 21.5, 20, vx=-1.0)]
    assert len(rules.evaluate("P1/F1", pair, 0.0)) == 1
    assert not rules.evaluate("P1/F1", pair, 10.0)
    assert not rules.evaluate("P1/F1", pair, 29.9)
    assert len(rules.evaluate("P1/F1", pair, 30.5)) == 1
    other = [person(7, 20, 20, vx=1.0), forklift(8, 21.5, 20, vx=-1.0)]
    assert len(rules.evaluate("P1/F1", other, 31.0)) == 1  # different tracks are not debounced
    assert len(rules.evaluate("P1/F2", pair, 31.0)) == 1  # nor another floor


# ---- tracker and mapper ----

def test_tracker_keeps_ids_and_uses_weak_detections():
    tracker = ByteTracker()
    seen = []
    for step in range(6):
        a = Detection((100 + 5 * step, 100, 150 + 5 * step, 220), 0.9 if step != 3 else 0.2, "person")
        b = Detection((600 - 8 * step, 300, 700 - 8 * step, 380), 0.8, "forklift")
        seen.append({(t.id, t.cls) for t in tracker.update([a, b])})
    assert seen[0] == set()  # not confirmed on the first frame
    assert all(s == {(1, "person"), (2, "forklift")} for s in seen[1:])  # frame 3 matched through the weak box
    assert tracker.update([Detection((900, 50, 940, 150), 0.3, "person")]) == []  # weak boxes never start a track
    assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(1 / 3)


def test_tracker_drops_lost_tracks():
    tracker = ByteTracker(max_misses=2)
    box = Detection((100, 100, 150, 220), 0.9, "person")
    tracker.update([box])
    tracker.update([box])
    for _ in range(3):
        tracker.update([])
    assert tracker.update([box]) == []  # comes back as a new, unconfirmed track
    assert [t.id for t in tracker.update([box])] == [2]


def test_homography_from_four_points():
    image = [(100, 600), (1180, 600), (900, 200), (380, 200)]
    floor = [(0, 0), (40, 0), (40, 25), (0, 25)]
    h = solve_homography(image, floor)
    for (u, v), (x, y) in zip(image, floor):
        assert apply_homography(h, u, v) == pytest.approx((x, y), abs=1e-6)
    assert foot_point((100, 50, 200, 300)) == (150, 300)
    mapper = FloorMapper(h, (40, 25))
    x, y = mapper.to_floor((590, 100, 690, 400))
    assert x == pytest.approx(20, abs=0.01) and 0 < y < 25
    assert mapper.to_floor((0, 0, 10, 719))[0] == 0.0  # clamped to the floor
    with pytest.raises(ValueError):
        solve_homography([(0, 0), (1, 1), (2, 2), (3, 3)], floor)

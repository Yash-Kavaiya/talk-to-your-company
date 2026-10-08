"""SQLite event store (plan section 4)."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from app.protocol import Event

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    plant TEXT NOT NULL,
    floor TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    type TEXT NOT NULL,
    severity INTEGER NOT NULL,
    track_ids TEXT NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    snapshot_path TEXT,
    summary TEXT NOT NULL,
    person_id TEXT
);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts);
"""
_COLUMNS = "id, ts, plant, floor, camera_id, type, severity, track_ids, x, y, snapshot_path, summary, person_id"


class EventStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)
            if "person_id" not in [row[1] for row in self._db.execute("PRAGMA table_info(events)")]:
                self._db.execute("ALTER TABLE events ADD COLUMN person_id TEXT")  # database from before v6

    def add(
        self,
        *,
        ts: float,
        plant: str,
        floor: str,
        camera_id: str,
        type: str,
        severity: int,
        track_ids: list[int],
        x: float,
        y: float,
        summary: str,
        snapshot_path: Optional[str] = None,
        person_id: Optional[str] = None,
    ) -> Event:
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT INTO events (ts, plant, floor, camera_id, type, severity, track_ids, x, y, snapshot_path,"
                " summary, person_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ts, plant, floor, camera_id, type, severity, json.dumps(track_ids), x, y, snapshot_path, summary,
                 person_id),
            )
            event_id = cur.lastrowid
        return Event(id=event_id, ts=ts, plant=plant, floor=floor, camera_id=camera_id, type=type, severity=severity,
                     track_ids=track_ids, x=x, y=y, snapshot_path=snapshot_path, summary=summary,
                     person_id=person_id)

    def set_snapshot(self, event_id: int, snapshot_path: str) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE events SET snapshot_path = ? WHERE id = ?", (snapshot_path, event_id))

    def get(self, event_id: int) -> Optional[Event]:
        with self._lock:
            row = self._db.execute(f"SELECT {_COLUMNS} FROM events WHERE id = ?", (event_id,)).fetchone()
        return _to_event(row) if row else None

    def query(
        self,
        plant: Optional[str] = None,
        floor: Optional[str] = None,
        type: Optional[str] = None,
        person_id: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: int = 200,
    ) -> list[Event]:
        """Events matching every given filter, newest first."""
        where, args = [], []
        for column, value in (("plant", plant), ("floor", floor), ("type", type), ("person_id", person_id)):
            if value is not None:
                where.append(f"{column} = ?")
                args.append(value)
        if since is not None:
            where.append("ts >= ?")
            args.append(since)
        if until is not None:
            where.append("ts <= ?")
            args.append(until)
        sql = f"SELECT {_COLUMNS} FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts DESC, id DESC LIMIT ?"
        with self._lock:
            rows = self._db.execute(sql, (*args, limit)).fetchall()
        return [_to_event(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()


def _to_event(row: tuple) -> Event:
    return Event(id=row[0], ts=row[1], plant=row[2], floor=row[3], camera_id=row[4], type=row[5], severity=row[6],
                 track_ids=json.loads(row[7]), x=row[8], y=row[9], snapshot_path=row[10], summary=row[11], person_id=row[12])

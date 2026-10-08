"""FastAPI app: serves web/, pushes live state over /ws and answers queries (plan sections 1 and 5)."""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agent.loop import Agent, split_sentences
from app.agent.tools import OPEN_EVENT_MINUTES, Session, Tools
from app.backends import Backends, build_backends
from app.config import ROOT, Settings, Site, load_site, split_zone_key, zone_key
from app.events.rules import Finding, RulesEngine
from app.events.store import EventStore
from app.identity import People, load_directory
from app.metrics import Metrics
from app.perception.base import Track
from app.protocol import (AnswerMsg, AudioMsg, AudioQuery, ClientMessage, Event, EventMsg, ProtocolError,
                          SelectEvent, SiteMsg, StateMsg, TextQuery, TrackState, TranscriptMsg, UiMsg,
                          parse_client_message)

log = logging.getLogger(__name__)

STATE_INTERVAL_S = 0.2  # 5 Hz
METRICS_EVERY_TICKS = 5  # 1 Hz
WEB_DIR = ROOT / "web"
MEDIA_TYPES = {"jpg": "image/jpeg", "svg": "image/svg+xml"}
MAX_FRAME_BYTES = 2_000_000


class Hub:
    """Everything shared between connections: backends, store, rules and the broadcast loop."""

    def __init__(self, settings: Settings, site: Site, backends: Backends, store: EventStore) -> None:
        self.settings = settings
        self.site = site
        self.backends = backends
        self.store = store
        self.rules = RulesEngine(site)
        self.people = People(load_directory(settings.employees_path))
        self.metrics = Metrics()
        self.connections: set["Connection"] = set()
        self.latest_tracks: dict[str, list[Track]] = {}
        self.snapshot_dir = settings.data_dir / "snapshots"
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def state_message(self) -> StateMsg:
        zones = {key: [TrackState(id=t.id, cls=t.cls, x=round(t.x, 2), y=round(t.y, 2)) for t in tracks]
                 for key, tracks in self.latest_tracks.items()}
        return StateMsg(ts=time.time(), zones=zones)

    async def broadcast(self, message: BaseModel) -> None:
        for connection in list(self.connections):
            await connection.send(message)

    async def run(self) -> None:
        tick = 0
        while True:
            started = time.monotonic()
            try:
                await self._tick(tick)
            except Exception:
                log.exception("broadcast tick failed")
            tick += 1
            await asyncio.sleep(max(STATE_INTERVAL_S - (time.monotonic() - started), 0.01))

    async def _tick(self, tick: int) -> None:
        self.latest_tracks = self.backends.perception.tracks()
        await self.broadcast(self.state_message())
        now = time.time()
        self.people.badges.update(self.latest_tracks, now)
        for key, tracks in self.latest_tracks.items():
            for finding in self.rules.evaluate(key, tracks, now):
                event = self._record(key, finding, now)
                if event is not None:
                    await self.broadcast(EventMsg(event=event))
        self.people.close_visits(self.rules, now)
        if tick % METRICS_EVERY_TICKS == 0:
            fps = self.backends.perception.fps()
            await self.broadcast(await asyncio.to_thread(self.metrics.message, fps))

    def _record(self, key: str, finding: Finding, now: float) -> Optional[Event]:
        """Store a finding as an event, naming the person from the badge feed. None when nothing is wrong:
        a person in a restricted zone they are authorised for."""
        plant_id, floor_id = split_zone_key(key)
        tracks = {t.id: t for t in self.latest_tracks.get(key, [])}
        involved = [i for i in finding.track_ids if i in tracks and tracks[i].cls == "person"]
        person = self.people.badges.employee_for(involved[0]) if len(involved) == 1 else None
        summary = finding.summary
        if person:
            summary = summary.replace(f"Person {involved[0]}", f"{person.name} ({person.id})")
        if finding.type == "restricted_zone" and person:
            if f"{key}/{finding.zone_id}" in person.authorised_zones:
                return None
            summary = summary.rstrip(".") + ", without authorisation."
        event = self.store.add(
            ts=now, plant=plant_id, floor=floor_id, camera_id=self.site.floor(plant_id, floor_id).camera.id,
            type=finding.type, severity=finding.severity, track_ids=finding.track_ids,
            x=round(finding.x, 2), y=round(finding.y, 2), summary=summary,
            person_id=person.id if person else None,
        )
        if finding.type == "restricted_zone" and involved:
            entered = self.rules.entered_at(key, involved[0], finding.zone_id) or now
            self.people.open_visit(event.id, key, involved[0], finding.zone_id, entered)
        try:
            snapshot = self.backends.perception.snapshot(key, finding.track_ids)
            if snapshot:
                data, extension = snapshot
                name = f"evt_{event.id}.{extension}"
                (self.snapshot_dir / name).write_bytes(data)
                event.snapshot_path = f"/snapshots/{name}"
                self.store.set_snapshot(event.id, event.snapshot_path)
        except Exception:
            log.exception("snapshot for event %s failed", event.id)
        return event


class Connection:
    """One browser: its socket, its conversation and its agent."""

    def __init__(self, websocket: WebSocket, hub: Hub) -> None:
        self.websocket = websocket
        self.hub = hub
        self._send_lock = asyncio.Lock()
        self._query_lock = asyncio.Lock()
        self.tasks: set[asyncio.Task] = set()
        b = hub.backends
        self.tools = Tools(hub.site, hub.store, b.perception, lambda: hub.latest_tracks, b.llm.look, Session(),
                           people=hub.people)
        self.agent = Agent(b.llm, self.tools, hub.site)

    async def send(self, message: BaseModel) -> None:
        try:
            async with self._send_lock:
                await self.websocket.send_text(message.model_dump_json())
        except (WebSocketDisconnect, RuntimeError):
            self.hub.connections.discard(self)

    async def handle(self, message: ClientMessage) -> None:
        received = time.monotonic()
        try:
            if isinstance(message, SelectEvent):
                self.tools.show_event(message.event_id)
                await self._flush_ui()
            elif isinstance(message, TextQuery):
                await self._answer(message.text, received)
            elif isinstance(message, AudioQuery):
                await self._answer_audio(message.wav_b64, received)
        except Exception:
            log.exception("query failed")
            await self.send(AnswerMsg(text="Something went wrong while answering that.", done=True))

    async def _flush_ui(self) -> None:
        pending, self.tools.pending_ui = self.tools.pending_ui, []
        for ui in pending:
            await self.send(ui)

    async def _answer_audio(self, wav_b64: str, received: float) -> None:
        try:
            wav = base64.b64decode(wav_b64, validate=True)
            text = (await asyncio.to_thread(self.hub.backends.asr.transcribe, wav)).strip()
        except (binascii.Error, ValueError) as exc:
            log.warning("unusable audio query: %s", exc)
            text = ""
        if not text:
            await self.send(TranscriptMsg(text="", final=True))
            await self.send(AnswerMsg(text="I didn't catch that. Please try again.", done=True))
            return
        await self._answer(text, received)

    async def _answer(self, text: str, received: float) -> None:
        async with self._query_lock:
            await self.send(TranscriptMsg(text=text, final=True))
            reply = await self.agent.ask(text, self._send_ui)
            sentences = split_sentences(reply)
            for seq, sentence in enumerate(sentences):
                last = seq == len(sentences) - 1
                await self.send(AnswerMsg(text=sentence, done=last))
                wav = await self._speak(sentence)
                if seq == 0:
                    self.hub.metrics.record_voice_latency(time.monotonic() - received)
                await self.send(AudioMsg(seq=seq, wav_b64=base64.b64encode(wav).decode("ascii"), last=last))

    async def _send_ui(self, ui: UiMsg) -> None:
        await self.send(ui)

    async def _speak(self, sentence: str) -> bytes:
        try:
            return await asyncio.to_thread(self.hub.backends.tts.synthesize, sentence)
        except Exception:
            log.exception("speech synthesis failed")
            return b""


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        site = load_site(settings.site_path)
        backends = build_backends(settings, site)
        log.warning("run modes: %s", backends.modes)
        hub = Hub(settings, site, backends, EventStore(settings.data_dir / "events.db"))
        app.state.hub = hub
        backends.perception.start()
        loop_task = asyncio.create_task(hub.run())
        try:
            yield
        finally:
            loop_task.cancel()
            backends.perception.stop()
            hub.store.close()

    app = FastAPI(title="Talk-to-your-Company", lifespan=lifespan)

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "modes": app.state.hub.backends.modes}

    @app.get("/api/camera/{plant}/{floor}")
    async def camera(plant: str, floor: str) -> Response:
        """Current camera view of one floor with the tracked objects marked (JPEG, or SVG in mock mode)."""
        hub: Hub = app.state.hub
        if hub.site.floor(plant, floor) is None:
            raise HTTPException(404, "unknown plant or floor")
        view = await asyncio.to_thread(hub.backends.perception.view, zone_key(plant, floor))
        if view is None:
            raise HTTPException(503, "no frame yet")
        data, extension = view
        return Response(data, media_type=MEDIA_TYPES[extension], headers={"Cache-Control": "no-store"})

    @app.post("/api/camera/{plant}/{floor}/frame", status_code=204)
    async def push_frame(plant: str, floor: str, request: Request) -> Response:
        """One JPEG frame from a browser that shares its webcam or a recording into this floor's camera."""
        hub: Hub = app.state.hub
        if hub.site.floor(plant, floor) is None:
            raise HTTPException(404, "unknown plant or floor")
        jpeg = await request.body()
        if len(jpeg) > MAX_FRAME_BYTES:
            raise HTTPException(413, "frame too large")
        if not await asyncio.to_thread(hub.backends.perception.push_frame, zone_key(plant, floor), jpeg):
            raise HTTPException(400, "not a JPEG frame")
        return Response(status_code=204)

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        hub: Hub = app.state.hub
        await websocket.accept()
        connection = Connection(websocket, hub)
        await connection.send(SiteMsg(site=hub.site))
        if hub.latest_tracks:
            await connection.send(hub.state_message())
        recent = hub.store.query(since=time.time() - OPEN_EVENT_MINUTES * 60)
        for event in reversed(recent):
            await connection.send(EventMsg(event=event))
        hub.connections.add(connection)
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    message = parse_client_message(raw)
                except ProtocolError as exc:
                    log.warning("ignoring bad client message: %s", exc)
                    continue
                task = asyncio.create_task(connection.handle(message))
                connection.tasks.add(task)
                task.add_done_callback(connection.tasks.discard)
        except WebSocketDisconnect:
            pass
        finally:
            hub.connections.discard(connection)
            for task in connection.tasks:
                task.cancel()

    snapshot_dir = settings.data_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/snapshots", StaticFiles(directory=snapshot_dir), name="snapshots")
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()

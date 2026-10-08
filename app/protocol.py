"""Pydantic models for every WebSocket message (plan section 5). Field `type` discriminates."""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.config import Site

EventType = Literal["near_miss", "restricted_zone", "no_helmet", "crowding"]
TrackClass = Literal["person", "forklift", "vehicle"]


class Event(BaseModel):
    """One row of the SQLite `events` table (plan section 4)."""

    id: int
    ts: float
    plant: str
    floor: str
    camera_id: str
    type: EventType
    severity: int = Field(ge=1, le=3)
    track_ids: list[int]
    x: float
    y: float
    snapshot_path: Optional[str] = None
    summary: str
    person_id: Optional[str] = None  # employee id from the badge feed, when one person is involved


class TrackState(BaseModel):
    id: int
    cls: TrackClass
    x: float
    y: float


# ---- server to client ----

class SiteMsg(BaseModel):
    type: Literal["site"] = "site"
    site: Site


class StateMsg(BaseModel):
    type: Literal["state"] = "state"
    ts: float
    zones: dict[str, list[TrackState]]


class EventMsg(BaseModel):
    type: Literal["event"] = "event"
    event: Event


class UiMsg(BaseModel):
    type: Literal["ui"] = "ui"
    action: Literal["focus", "highlight", "panel"]
    plant: Optional[str] = None
    floor: Optional[str] = None
    event_ids: list[int] = []
    content: Optional[dict[str, Any]] = None


class TranscriptMsg(BaseModel):
    type: Literal["transcript"] = "transcript"
    text: str
    final: bool = True


class AnswerMsg(BaseModel):
    type: Literal["answer"] = "answer"
    text: str
    done: bool = False


class AudioMsg(BaseModel):
    type: Literal["audio"] = "audio"
    seq: int
    wav_b64: str
    last: bool = False


class MetricsMsg(BaseModel):
    type: Literal["metrics"] = "metrics"
    fps: dict[str, float]
    voice_latency_ms: Optional[float] = None
    gpu_pct: Optional[float] = None
    mem_gb: Optional[float] = None


ServerMessage = Annotated[
    Union[SiteMsg, StateMsg, EventMsg, UiMsg, TranscriptMsg, AnswerMsg, AudioMsg, MetricsMsg],
    Field(discriminator="type"),
]


# ---- client to server ----

class AudioQuery(BaseModel):
    type: Literal["audio_query"] = "audio_query"
    wav_b64: str


class TextQuery(BaseModel):
    type: Literal["text_query"] = "text_query"
    text: str = Field(min_length=1, max_length=500)


class SelectEvent(BaseModel):
    type: Literal["select_event"] = "select_event"
    event_id: int


ClientMessage = Annotated[Union[AudioQuery, TextQuery, SelectEvent], Field(discriminator="type")]

_client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)
_server_adapter: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)


class ProtocolError(ValueError):
    pass


def parse_client_message(raw: str | bytes) -> ClientMessage:
    try:
        return _client_adapter.validate_json(raw)
    except ValidationError as exc:
        raise ProtocolError(str(exc)) from exc


def parse_server_message(raw: str | bytes) -> ServerMessage:
    try:
        return _server_adapter.validate_json(raw)
    except ValidationError as exc:
        raise ProtocolError(str(exc)) from exc

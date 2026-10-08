"""Loads config/site.yaml and the run modes from the environment."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterator, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITE_PATH = ROOT / "config" / "site.yaml"
DEFAULT_EMPLOYEES_PATH = ROOT / "config" / "employees.yaml"

ZoneType = Literal["restricted", "walkway", "dock"]
ObjectType = Literal["conveyor", "rack", "machine", "pallets", "office"]


class ConfigError(ValueError):
    """The site file is missing, unreadable or does not match the schema."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Zone(_Strict):
    id: str
    type: ZoneType
    polygon: list[tuple[float, float]] = Field(min_length=3)


class FloorObject(_Strict):
    """Fixed equipment on a floor. `rect` is x, y, width, depth in metres, axis-aligned."""

    id: str
    type: ObjectType
    rect: tuple[float, float, float, float]

    def polygon(self, margin: float = 0.0) -> list[tuple[float, float]]:
        x, y, w, d = self.rect
        return [(x - margin, y - margin), (x + w + margin, y - margin),
                (x + w + margin, y + d + margin), (x - margin, y + d + margin)]


class Camera(_Strict):
    """`video` is a file (relative names live in VIDEOS_DIR), `webcam:<device>` for a camera on this
    machine, or `browser` for frames shared from a browser's webcam."""

    id: str
    video: str
    homography: Optional[list[list[float]]] = None

    @model_validator(mode="after")
    def _check_homography(self) -> "Camera":
        h = self.homography
        if h is not None and (len(h) != 3 or any(len(row) != 3 for row in h)):
            raise ValueError("homography must be a 3x3 matrix")
        if self.video.startswith("webcam") and not re.fullmatch(r"webcam:\S+", self.video):
            raise ValueError("a webcam source is written webcam:<device>, e.g. webcam:0")
        return self

    def source_kind(self) -> Literal["file", "webcam", "browser"]:
        if self.video == "browser":
            return "browser"
        return "webcam" if self.video.startswith("webcam:") else "file"


class Floor(_Strict):
    id: str
    size_m: tuple[float, float]
    camera: Camera
    zones: list[Zone] = []
    objects: list[FloorObject] = []

    @model_validator(mode="after")
    def _check(self) -> "Floor":
        w, d = self.size_m
        if w <= 0 or d <= 0:
            raise ValueError("size_m must be positive")
        _unique([z.id for z in self.zones], "zone id")
        for zone in self.zones:
            for x, y in zone.polygon:
                if not (0 <= x <= w and 0 <= y <= d):
                    raise ValueError(f"zone {zone.id} has a point outside the floor")
        _unique([o.id for o in self.objects], "object id")
        for obj in self.objects:
            x, y, ow, od = obj.rect
            if ow <= 0 or od <= 0 or x < 0 or y < 0 or x + ow > w or y + od > d:
                raise ValueError(f"object {obj.id} has no size or lies outside the floor")
        return self


class Plant(_Strict):
    id: str
    name: str
    floors: list[Floor] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> "Plant":
        _unique([f.id for f in self.floors], "floor id")
        return self


class Site(_Strict):
    plants: list[Plant] = Field(min_length=1)
    # floor key where mock perception stages its "person enters a restricted zone" scenario; any floor if unset
    demo_restricted_floor: Optional[str] = None

    @model_validator(mode="after")
    def _check(self) -> "Site":
        _unique([p.id for p in self.plants], "plant id")
        _unique([f.camera.id for _, f in self.floors()], "camera id")
        if self.demo_restricted_floor is not None:
            floor = self.floor(*self.demo_restricted_floor.split("/", 1)) if "/" in self.demo_restricted_floor else None
            if floor is None or not any(z.type == "restricted" for z in floor.zones):
                raise ValueError("demo_restricted_floor must name a floor that has a restricted zone")
        return self

    def floors(self) -> Iterator[tuple[Plant, Floor]]:
        for plant in self.plants:
            for floor in plant.floors:
                yield plant, floor

    def plant(self, plant_id: str) -> Optional[Plant]:
        return next((p for p in self.plants if p.id == plant_id), None)

    def floor(self, plant_id: str, floor_id: str) -> Optional[Floor]:
        plant = self.plant(plant_id)
        if plant is None:
            return None
        return next((f for f in plant.floors if f.id == floor_id), None)

    def zone_keys(self) -> list[str]:
        return [zone_key(p.id, f.id) for p, f in self.floors()]


def _unique(ids: list[str], what: str) -> None:
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            raise ValueError(f"duplicate {what}: {i}")
        seen.add(i)


def zone_key(plant_id: str, floor_id: str) -> str:
    """Global key of a floor, e.g. `P1/F1`."""
    return f"{plant_id}/{floor_id}"


def split_zone_key(key: str) -> tuple[str, str]:
    plant_id, floor_id = key.split("/", 1)
    return plant_id, floor_id


def resolve_video(video: str, videos_dir: Path) -> Path:
    """Path of a camera's video file: absolute as written, relative inside `videos_dir`."""
    path = Path(video)
    return path if path.is_absolute() else videos_dir / path


def load_site(path: str | Path = DEFAULT_SITE_PATH) -> Site:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a mapping with a 'plants' key")
    try:
        return Site.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{path} is malformed: {exc}") from exc


class Settings(BaseModel):
    """Run modes and paths. Every heavy component has a mock (see CLAUDE.md)."""

    perception: Literal["mock", "real"] = "mock"
    llm: Literal["mock", "local"] = "mock"
    asr: Literal["mock", "local"] = "mock"
    tts: Literal["mock", "local"] = "mock"
    device: Literal["cuda", "cpu"] = "cuda"  # cpu is for checking the real backends on a laptop
    site_path: Path = DEFAULT_SITE_PATH
    employees_path: Path = DEFAULT_EMPLOYEES_PATH
    data_dir: Path = ROOT / "data"
    models_dir: Path = Path("/cache/models")
    videos_dir: Path = Path("/cache/videos")

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        values = {
            "perception": env.get("PERCEPTION", "mock").lower(),
            "llm": env.get("LLM", "mock").lower(),
            "asr": env.get("ASR", "mock").lower(),
            "tts": env.get("TTS", "mock").lower(),
            "device": env.get("DEVICE", "cuda").lower(),
        }
        for field, var in (("site_path", "SITE_CONFIG"), ("employees_path", "EMPLOYEES"), ("data_dir", "DATA_DIR"), ("models_dir", "MODELS_DIR"),
                           ("videos_dir", "VIDEOS_DIR")):
            if env.get(var):
                values[field] = env[var]
        try:
            return cls.model_validate(values)
        except ValidationError as exc:
            raise ConfigError(f"bad run mode in environment: {exc}") from exc

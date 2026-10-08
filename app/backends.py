"""Builds the four heavy components from the run modes, falling back to mocks on failure (NFR3)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.agent.llm import LLM, MockLLM
from app.agent.prompts import HELMET_PROMPT
from app.config import Settings, Site
from app.perception.base import Perception
from app.perception.mock import MockPerception
from app.voice.asr import ASR, MockASR
from app.voice.tts import TTS, MockTTS

log = logging.getLogger(__name__)


@dataclass
class Backends:
    perception: Perception
    llm: LLM
    asr: ASR
    tts: TTS
    modes: dict[str, str]  # what is actually running, e.g. {"llm": "mock (fallback)"}


def _build(kind: str, wanted: str, make_real: Callable[[], Any], make_mock: Callable[[], Any],
           modes: dict[str, str]) -> Any:
    if wanted == "mock":
        modes[kind] = "mock"
        return make_mock()
    try:
        backend = make_real()
        modes[kind] = wanted
        return backend
    except Exception as exc:  # any load failure must leave the app demoable
        log.warning("%s backend '%s' failed to start, falling back to mock: %s", kind, wanted, exc)
        modes[kind] = "mock (fallback)"
        return make_mock()


def _real_perception(settings: Settings, site: Site) -> Perception:
    from app.perception.pipeline import RealPerception

    return RealPerception(site, settings.models_dir, settings.videos_dir)


def _local_llm(settings: Settings) -> LLM:
    from app.agent.llm import LocalLLM

    return LocalLLM(settings.models_dir, device=settings.device)


def _local_asr(settings: Settings) -> ASR:
    from app.voice.asr import LocalASR

    return LocalASR(settings.models_dir, device=settings.device)


def _local_tts(settings: Settings) -> TTS:
    from app.voice.tts import LocalTTS

    return LocalTTS(settings.models_dir)


def _directory(settings: Settings):
    from app.identity import load_directory

    return load_directory(settings.employees_path)


def helmet_answer(text: Optional[str]) -> Optional[bool]:
    """Vision model's yes/no on "is this person wearing a helmet" -> True, False or None (unclear)."""
    word = (text or "").strip().lower()
    if word.startswith("yes"):
        return True
    if word.startswith("no"):
        return False
    return None


def build_backends(settings: Settings, site: Site) -> Backends:
    modes: dict[str, str] = {}
    perception = _build("perception", settings.perception, lambda: _real_perception(settings, site),
                        lambda: MockPerception(site), modes)
    llm = _build("llm", settings.llm, lambda: _local_llm(settings), lambda: MockLLM(site, _directory(settings)), modes)
    asr = _build("asr", settings.asr, lambda: _local_asr(settings), MockASR, modes)
    tts = _build("tts", settings.tts, lambda: _local_tts(settings), MockTTS, modes)
    if modes["perception"] == "real" and modes["llm"] == "local":
        perception.helmet_check = lambda jpeg: helmet_answer(llm.try_look(jpeg, HELMET_PROMPT))
    return Backends(perception=perception, llm=llm, asr=asr, tts=tts, modes=modes)

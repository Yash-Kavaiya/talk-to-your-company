"""Speech synthesis: `MockTTS` and `LocalTTS` (Piper on the CPU)."""
from __future__ import annotations

import array
import io
import math
import os
import wave
from pathlib import Path
from typing import Optional, Protocol

MOCK_RATE = 16000


class TTS(Protocol):
    name: str

    def synthesize(self, text: str) -> bytes:
        """One sentence as a WAV file."""


class MockTTS:
    """Cannot speak: returns a short soft chime per sentence so audio playback can be exercised."""

    name = "mock"

    def synthesize(self, text: str) -> bytes:
        samples = array.array("h")
        for frequency in (660.0, 880.0):
            n = int(MOCK_RATE * 0.09)
            for i in range(n):
                envelope = math.sin(math.pi * i / n)
                samples.append(int(2500 * envelope * math.sin(2 * math.pi * frequency * i / MOCK_RATE)))
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(MOCK_RATE)
            f.writeframes(samples.tobytes())
        return buffer.getvalue()


class LocalTTS:
    """Piper voice. Raises if the package or the voice file is missing."""

    name = "local"

    def __init__(self, models_dir: Path, voice_path: Optional[str] = None) -> None:
        from piper import PiperVoice

        path = Path(voice_path or os.environ.get("PIPER_VOICE", models_dir / "piper" / "en_US-lessac-medium.onnx"))
        if not path.exists():
            raise FileNotFoundError(f"Piper voice not found: {path}")
        self._voice = PiperVoice.load(str(path))
        self.synthesize("Ready.")  # pre-warm

    def synthesize(self, text: str) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as f:
            # piper-tts 1.3 renamed synthesize(text, wav_file) to synthesize_wav
            write = getattr(self._voice, "synthesize_wav", None) or self._voice.synthesize
            write(text, f)
        return buffer.getvalue()

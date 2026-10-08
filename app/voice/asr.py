"""Speech recognition: `MockASR` and `LocalASR` (Whisper on the GPU)."""
from __future__ import annotations

import io
import os
import wave
from pathlib import Path
from typing import Optional, Protocol


class ASR(Protocol):
    name: str

    def transcribe(self, wav: bytes) -> str:
        """Text spoken in a WAV recording (PCM 16-bit)."""


def wav_duration(wav: bytes) -> float:
    """Length in seconds. Raises `ValueError` when the bytes are not a PCM WAV file."""
    try:
        with wave.open(io.BytesIO(wav)) as f:
            return f.getnframes() / f.getframerate()
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"not a WAV recording: {exc}") from exc


class MockASR:
    """Cannot hear: returns a fixed question so the audio path can be exercised without a model."""

    name = "mock"

    def __init__(self, text: Optional[str] = None) -> None:
        self.text = text or os.environ.get("MOCK_ASR_TEXT", "Give me a status of both plants.")

    def transcribe(self, wav: bytes) -> str:
        wav_duration(wav)
        return self.text


class LocalASR:
    """Whisper through `transformers` on the pre-installed PyTorch. Raises if it cannot load."""

    name = "local"

    def __init__(self, models_dir: Path, model_id: Optional[str] = None, device: str = "cuda") -> None:
        import torch

        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available")
        from transformers import pipeline

        self.model_id = model_id or os.environ.get("ASR_MODEL", "openai/whisper-small")
        self._pipe = pipeline("automatic-speech-recognition", model=self.model_id, device=device,
                              torch_dtype=torch.float16 if device == "cuda" else torch.float32, model_kwargs={"cache_dir": str(models_dir)})

    def transcribe(self, wav: bytes) -> str:
        import numpy as np

        with wave.open(io.BytesIO(wav)) as f:
            if f.getsampwidth() != 2:
                raise ValueError("expected 16-bit PCM")
            rate, channels = f.getframerate(), f.getnchannels()
            samples = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1)
        # English-only checkpoints (whisper-*.en) reject the language and task arguments
        multilingual = getattr(self._pipe.model.generation_config, "is_multilingual", True)
        kwargs = {"language": "en", "task": "transcribe"} if multilingual else {}
        result = self._pipe({"raw": samples, "sampling_rate": rate}, generate_kwargs=kwargs)
        return result["text"].strip()

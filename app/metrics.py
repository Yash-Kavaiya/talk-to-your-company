"""Numbers for the HUD: fps per stream, last voice latency, GPU use and memory."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from app.protocol import MetricsMsg

_JETSON_GPU_LOAD = Path("/sys/devices/platform/gpu.0/load")  # per mille


def memory_gb() -> Optional[float]:
    """Memory in use inside the container (cgroup) or on the machine, in GB."""
    for path in ("/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory/memory.usage_in_bytes"):
        try:
            return round(int(Path(path).read_text()) / 1e9, 2)
        except (OSError, ValueError):
            pass
    try:
        import psutil

        return round(psutil.virtual_memory().used / 1e9, 2)
    except ImportError:
        return None


def gpu_pct() -> Optional[float]:
    """GPU utilisation in percent, or None when there is no GPU to read."""
    try:
        return round(int(_JETSON_GPU_LOAD.read_text()) / 10.0, 1)
    except (OSError, ValueError):
        pass
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=2).stdout
            return float(out.strip().splitlines()[0])
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            pass
    return None


class Metrics:
    def __init__(self) -> None:
        self.voice_latency_ms: Optional[float] = None

    def record_voice_latency(self, seconds: float) -> None:
        self.voice_latency_ms = round(seconds * 1000)

    def message(self, fps: dict[str, float]) -> MetricsMsg:
        return MetricsMsg(fps=fps, voice_latency_ms=self.voice_latency_ms, gpu_pct=gpu_pct(), mem_gb=memory_gb())

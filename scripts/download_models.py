#!/usr/bin/env python3
"""Fetch every model into /cache/models and export the detector to TensorRT. Run once, before the demo.

This is the only step that uses the network; scripts/run.sh then runs offline.
    python3 scripts/download_models.py [--models-dir /cache/models] [--streams 6] [--skip-engine]
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

VLM = os.environ.get("VLM_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct")
WHISPER = os.environ.get("ASR_MODEL", "openai/whisper-small")
PIPER_REPO = "rhasspy/piper-voices"
PIPER_FILES = ["en/en_US/lessac/medium/en_US-lessac-medium.onnx", "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"]
YOLO_WEIGHTS = "yolo11s.pt"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models-dir", type=Path, default=Path(os.environ.get("MODELS_DIR", "/cache/models")))
    parser.add_argument("--streams", type=int, default=6, help="largest detector batch (one frame per stream)")
    parser.add_argument("--skip-engine", action="store_true", help="do not export the TensorRT engine")
    args = parser.parse_args()
    models: Path = args.models_dir.resolve()
    models.mkdir(parents=True, exist_ok=True)

    from huggingface_hub import hf_hub_download, snapshot_download

    for repo in (VLM, WHISPER):
        print(f"downloading {repo}")
        snapshot_download(repo, cache_dir=str(models))

    piper_dir = models / "piper"
    piper_dir.mkdir(exist_ok=True)
    for name in PIPER_FILES:
        print(f"downloading {name}")
        shutil.copy(hf_hub_download(PIPER_REPO, name, cache_dir=str(models)), piper_dir / Path(name).name)

    from ultralytics import YOLO

    weights = models / YOLO_WEIGHTS
    if not weights.exists():
        print(f"downloading {YOLO_WEIGHTS}")
        os.chdir(models)  # ultralytics downloads into the working directory
        YOLO(YOLO_WEIGHTS)
    if not args.skip_engine:
        print("exporting TensorRT FP16 engine (takes several minutes)")
        YOLO(str(weights)).export(format="engine", half=True, dynamic=True, batch=args.streams, imgsz=640)
    print(f"done: {sorted(p.name for p in models.iterdir())}")


if __name__ == "__main__":
    main()

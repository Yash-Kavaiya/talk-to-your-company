"""YOLO detector, TensorRT FP16 when an engine file exists, batched across streams (plan section 7)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from app.perception.tracker import Detection

# Model class name -> our class. COCO has no forklift; "truck" is what COCO weights call one.
# Weights trained with a real "forklift" class work without changes.
CLASS_MAP = {"person": "person", "forklift": "forklift", "truck": "forklift",
             "car": "vehicle", "bus": "vehicle", "motorcycle": "vehicle"}


def default_weights(models_dir: Path) -> Path:
    """The TensorRT engine if it was exported, else the PyTorch weights."""
    override = os.environ.get("DETECTOR_WEIGHTS")
    if override:
        return Path(override)
    engine = models_dir / "yolo11s.engine"
    return engine if engine.exists() else models_dir / "yolo11s.pt"


class Detector:
    def __init__(self, models_dir: Path, weights: Optional[Path] = None) -> None:
        from ultralytics import YOLO

        path = weights or default_weights(models_dir)
        if not path.exists():
            raise FileNotFoundError(f"detector weights not found: {path} (run scripts/download_models.py)")
        self._model = YOLO(str(path), task="detect")
        import torch

        # half precision only for PyTorch weights on the GPU; an engine has its precision baked in
        self._half = path.suffix == ".pt" and torch.cuda.is_available()
        self._classes: dict[int, str] = {}
        # smaller input = faster and less accurate; 640 suits the Jetson, a laptop CPU needs less
        self._size = int(os.environ.get("DETECTOR_IMGSZ", "640"))

    def detect(self, frames: list[Any]) -> list[list[Detection]]:
        """Detections per frame for one batch of BGR frames."""
        if not frames:
            return []
        precision = {"half": True} if self._half else {}
        results = self._model.predict(frames, imgsz=self._size, conf=0.1, verbose=False, **precision)
        if not self._classes:
            self._classes = {i: CLASS_MAP[name] for i, name in results[0].names.items() if name in CLASS_MAP}
        batch = []
        for result in results:
            boxes = result.boxes
            detections = []
            for bbox, score, cls in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist()):
                name = self._classes.get(int(cls))
                if name:
                    detections.append(Detection(bbox=tuple(bbox), score=score, cls=name))
            batch.append(detections)
        return batch

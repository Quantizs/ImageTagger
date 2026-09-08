"""One reusable YOLO11l detector for people and road/rail vehicles."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

DEFAULT_WEIGHTS = Path(__file__).resolve().parent / "models" / "yolo11l.pt"
COCO_CLASSES = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 6: "train", 7: "truck"}


@dataclass(frozen=True)
class Detection:
    kind: str
    box: tuple[float, float, float, float]
    confidence: float
    class_name: str

    @property
    def center(self):
        x1, y1, x2, y2 = self.box
        return (x1 + x2) / 2, (y1 + y2) / 2


def detection_counts(detections):
    return {"people": sum(d.kind == "person" for d in detections),
            "vehicles": sum(d.kind == "vehicle" for d in detections)}


class YoloSceneDetector:
    def __init__(self, weights=DEFAULT_WEIGHTS, confidence=0.25, image_size=1280, device=None):
        if not math.isfinite(confidence) or not 0 < confidence <= 1:
            raise ValueError("A detektálási küszöb 0-nál nagyobb, legfeljebb 1 legyen.")
        if not isinstance(image_size, int) or not 32 <= image_size <= 4096:
            raise ValueError("A YOLO képméret 32 és 4096 pixel közötti egész szám legyen.")
        config = Path(os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(__file__).resolve().parent / ".ultralytics"))).expanduser()
        config.mkdir(parents=True, exist_ok=True)
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("A YOLO export függőségei hiányoznak. Telepítés: python -m pip install -r requirements-export.txt. "
                               "Detektálás nélküli export: --no-detection.") from exc
        weights = Path(weights).expanduser().resolve()
        if not weights.exists() and weights.name != "yolo11l.pt":
            raise ValueError(f"A modellfájl nem található: {weights}")
        weights.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.model = YOLO(str(weights), task="detect")
            if self.model.task != "detect" or any(self.model.names.get(i) != name for i, name in COCO_CLASSES.items()):
                raise ValueError("COCO osztályokkal tanított YOLO detektormodell szükséges.")
        except Exception as exc:
            raise RuntimeError(f"A YOLO11l modell nem tölthető be ({weights}): {exc}") from exc
        self.confidence = confidence
        self.image_size = image_size
        self.device = device

    def detect(self, image: Image.Image) -> list[Detection]:
        # PIL metadata must not rotate the image differently from the annotator.
        try:
            with image.convert("RGB") as clean:
                clean.info.clear()
                results = self.model.predict(source=clean, conf=self.confidence, imgsz=self.image_size,
                                             device=self.device, classes=list(COCO_CLASSES),
                                             max_det=1000, save=False, verbose=False)
            if len(results) != 1 or results[0].boxes is None:
                raise ValueError("A modell nem adott érvényes detektálási eredményt.")
            boxes = results[0].boxes
            coordinates = boxes.xyxy.cpu().tolist()
            classes = boxes.cls.cpu().tolist()
            scores = boxes.conf.cpu().tolist()
            detections = []
            for coords, class_id, score in zip(coordinates, classes, scores):
                class_id = int(class_id)
                if class_id not in COCO_CLASSES or not all(math.isfinite(v) for v in (*coords, score)):
                    continue
                if score < self.confidence:
                    continue
                x1, y1, x2, y2 = coords
                box = (max(0, min(image.width, x1)), max(0, min(image.height, y1)),
                       max(0, min(image.width, x2)), max(0, min(image.height, y2)))
                if box[2] <= box[0] or box[3] <= box[1]:
                    continue
                detections.append(Detection("person" if class_id == 0 else "vehicle", box,
                                            float(score), COCO_CLASSES[class_id]))
            # Stable visual order instead of confidence-based numbering.
            return sorted(detections, key=lambda d: (d.kind, d.center[1], d.center[0], d.class_name))
        except Exception as exc:
            raise RuntimeError(f"A YOLO felismerés sikertelen: {exc}") from exc

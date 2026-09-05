"""File storage and geometry for the image annotator (independent of the GUI)."""

from __future__ import annotations

import csv
import io
import json
import math
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from PIL import Image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".gif"}
Point = tuple[float, float]
Polygon = list[Point]


def polygon_area(points: Polygon) -> float:
    """Shoelace area; multiply normalized area by width * height for pixels²."""
    return abs(sum(x * points[(i + 1) % len(points)][1]
                   - points[(i + 1) % len(points)][0] * y
                   for i, (x, y) in enumerate(points))) / 2


def valid_polygon(points: Polygon) -> bool:
    """Four finite, normalized corners in clockwise screen order, strictly convex."""
    if len(points) != 4 or any(not math.isfinite(v) or not 0 <= v <= 1
                               for point in points for v in point):
        return False
    crosses = []
    for i in range(4):
        a, b, c = points[i], points[(i + 1) % 4], points[(i + 2) % 4]
        crosses.append((b[0] - a[0]) * (c[1] - b[1])
                       - (b[1] - a[1]) * (c[0] - b[0]))
    return all(cross > 0 for cross in crosses)


def parse_annotations(text: str) -> list[Polygon]:
    polygons = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            values = [float(value) for value in line.split()]
        except ValueError as exc:
            raise ValueError(f"{number}. sor: nem szám típusú koordináta.") from exc
        if len(values) != 8:
            raise ValueError(f"{number}. sor: pontosan 8 koordináta szükséges.")
        points = list(zip(values[::2], values[1::2]))
        if not valid_polygon(points):
            raise ValueError(f"{number}. sor: hibás, kereszteződő vagy nem konvex négyszög.")
        polygons.append(points)
    return polygons


def serialize_annotations(polygons: list[Polygon]) -> str:
    for polygon in polygons:
        if not valid_polygon(polygon):
            raise ValueError("Érvénytelen poligon nem menthető.")
    # Round-trip precision also preserves tiny valid objects in very large images.
    return "".join(" ".join(format(v, ".17g") for point in polygon for v in point) + "\n"
                   for polygon in polygons)


def atomic_write(path: Path, text: str) -> None:
    """Replace one file only after the complete new content is flushed to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=path.parent, prefix=".tmp-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@dataclass
class ImageRecord:
    path: Path
    annotation_path: Path
    width: int = 0
    height: int = 0
    polygons: list[Polygon] = field(default_factory=list)
    annotation_error: str = ""
    image_error: str = ""
    dirty: bool = False

    @property
    def editable(self) -> bool:
        return not self.annotation_error and not self.image_error


class AnnotationStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory).expanduser().resolve()
        if not self.directory.is_dir():
            raise ValueError("A megadott képmappa nem létezik.")
        self.output_directory = self.directory / "annotations"
        self.records: list[ImageRecord] = []
        for path in sorted(self.directory.iterdir(), key=lambda p: p.name.casefold()):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            record = ImageRecord(path, self.output_directory / (path.name + ".txt"))
            try:
                with Image.open(path) as source:
                    record.width, record.height = source.size
            except (OSError, ValueError, Image.DecompressionBombError) as exc:
                record.image_error = str(exc)
            if record.annotation_path.exists():
                try:
                    record.polygons = parse_annotations(record.annotation_path.read_text(encoding="utf-8-sig"))
                except (OSError, ValueError) as exc:
                    record.annotation_error = str(exc)
            self.records.append(record)
        if not self.records:
            raise ValueError("A mappában nincs támogatott kép (JPG, PNG, BMP, TIFF, WEBP, GIF).")
        self.session_warning = ""

    def save_record(self, record: ImageRecord) -> None:
        if not record.dirty:
            return
        if not record.editable:
            raise ValueError("A hibás kép vagy annotáció nem írható felül.")
        atomic_write(record.annotation_path, serialize_annotations(record.polygons))
        record.dirty = False

    def save_all(self) -> None:
        for record in self.records:
            self.save_record(record)

    def restore_index(self) -> int:
        path = self.output_directory / "session.json"
        if not path.exists():
            return 0
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            last_image = state["last_image"]
            return next((i for i, record in enumerate(self.records)
                         if record.path.name == last_image), 0)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.session_warning = f"A korábbi pozíció nem olvasható: {exc}"
            return 0

    def save_session(self, index: int) -> None:
        atomic_write(self.output_directory / "session.json", json.dumps({
            "version": 1, "last_image": self.records[index].path.name,
        }, ensure_ascii=False, indent=2) + "\n")

    def statistics(self) -> tuple[dict, list[dict]]:
        rows = []
        areas = []
        for record in self.records:
            record_areas = ([polygon_area(polygon) * record.width * record.height
                             for polygon in record.polygons]
                            if not record.image_error and not record.annotation_error else [])
            areas.extend(record_areas)
            rows.append({
                "image": record.path.name,
                "width_px": record.width, "height_px": record.height,
                "object_count": len(record.polygons),
                "mean_object_area_px2": mean(record_areas) if record_areas else 0,
                "total_object_area_px2": sum(record_areas),
                "error": "; ".join(filter(None, (record.image_error, record.annotation_error))),
            })
        annotated = sum(bool(record.polygons) for record in self.records)
        objects = sum(len(record.polygons) for record in self.records)
        stats = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "directory": str(self.directory),
            "total_images": len(self.records),
            "annotated_images": annotated,
            "images_without_annotations": len(self.records) - annotated,
            "total_objects": objects,
            "mean_object_area_px2": mean(areas) if areas else 0,
            "min_object_area_px2": min(areas, default=0),
            "max_object_area_px2": max(areas, default=0),
            "objects_with_measurable_area": len(areas),
            "mean_objects_per_image": objects / len(self.records),
            "mean_objects_per_annotated_image": objects / annotated if annotated else 0,
            "images_with_errors": sum(bool(row["error"]) for row in rows),
            "errors": [{"image": row["image"], "error": row["error"]}
                       for row in rows if row["error"]],
        }
        return stats, rows

    def save_statistics(self) -> dict:
        self.save_all()
        stats, rows = self.statistics()
        atomic_write(self.output_directory / "statistics.json",
                     json.dumps(stats, ensure_ascii=False, indent=2) + "\n")
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        atomic_write(self.output_directory / "statistics_per_image.csv", output.getvalue())
        return stats

"""Shared rental-advertising categories for annotation, migration and export."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BoardType:
    name: str
    width_cm: float | None = None
    height_cm: float | None = None
    approximate_ratio: float | None = None

    @property
    def ratio(self) -> float:
        return self.approximate_ratio if self.approximate_ratio is not None else self.width_cm / self.height_cm

    @property
    def size_label(self) -> str:
        if self.approximate_ratio is not None:
            return f"Kiinduló arány: {self.ratio:g}:1"
        return f"{self.width_cm:g} × {self.height_cm:g} cm".replace(".", ",")


CATEGORIES = {
    board.name: board for board in (
        BoardType("BKV_álló", 70, 100),
        BoardType("Citylight", 118.5, 175),
        BoardType("Óriásplakát", 504, 238),
        BoardType("Kandeláber", 100, 140),
        BoardType("Reklámháló", approximate_ratio=2),
        BoardType("Tetőreklám", approximate_ratio=3),
        BoardType("Korlátreklám", 133, 63),
    )
}


def aspect_ratio(points) -> float:
    width = (math.dist(points[0], points[1]) + math.dist(points[3], points[2])) / 2
    height = (math.dist(points[0], points[3]) + math.dist(points[1], points[2])) / 2
    if not math.isfinite(width + height) or min(width, height) <= 0:
        raise ValueError("A tábla szélessége és magassága pozitív, véges szám legyen.")
    return width / height


def classify_board(points) -> BoardType:
    ratio = aspect_ratio(points)
    return min(CATEGORIES.values(), key=lambda board: abs(math.log(ratio / board.ratio)))


def predict_category(polygon, size) -> str:
    # Measure original pixels, not normalized coordinates or axis-aligned bounds.
    return classify_board([(x * size[0], y * size[1]) for x, y in polygon]).name


class CategorizedPolygon(list):
    """A four-point list with category provenance; geometry consumers stay compatible."""

    def __init__(self, points, category: str, source: str):
        if category not in CATEGORIES or source not in ("auto", "manual"):
            raise ValueError("Ismeretlen kategória vagy kategóriaeredet (auto/manual).")
        super().__init__(points)
        self.category = category
        self.category_source = source


def auto_category(polygon, size):
    if getattr(polygon, "category_source", None) == "manual":
        return CategorizedPolygon(polygon, polygon.category, "manual")
    return CategorizedPolygon(polygon, predict_category(polygon, size), "auto")


def edited_polygon(original, points, size):
    """Keep manual choices through edits; update automatic choices from new geometry."""
    if getattr(original, "category_source", None) == "manual":
        return CategorizedPolygon(points, original.category, "manual")
    return auto_category(points, size)

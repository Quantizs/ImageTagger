"""Three-band annotation frames and a rectified advertising-board contact sheet."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

BLUE = (0, 80, 255)
RED = (255, 30, 35)
GREEN = (0, 220, 70)
INK = "#152d46"
MUTED = "#61758a"
PAPER = "#f0f4f8"
Point = tuple[float, float]


@dataclass(frozen=True)
class BoardType:
    name: str
    width_cm: int
    height_cm: int

    @property
    def ratio(self):
        return self.width_cm / self.height_cm


PORTRAIT = BoardType("Kandelláber", 100, 140)
BILLBOARD = BoardType("Óriásplakát", 504, 238)


def line_width(size: tuple[int, int], ratio: float = 0.003) -> int:
    """Width of each colored band, rounded to at least one pixel."""
    return max(1, math.floor(min(size) * ratio + 0.5))


def pixel_points(polygon, size):
    width, height = size
    return [(min(width - 1, max(0, x * width)), min(height - 1, max(0, y * height)))
            for x, y in polygon]


def classify_board(points: list[Point]) -> BoardType:
    """Compare mean opposing edge lengths in pixels, allowing camera roll."""
    width = (math.dist(points[0], points[1]) + math.dist(points[3], points[2])) / 2
    height = (math.dist(points[0], points[3]) + math.dist(points[1], points[2])) / 2
    if min(width, height) <= 0:
        raise ValueError("A tábla szélessége és magassága nem lehet nulla.")
    ratio = width / height
    return min((PORTRAIT, BILLBOARD), key=lambda board: abs(math.log(ratio / board.ratio)))


def _solve(matrix, values):
    """Small pivoted linear solver; perspective rectification needs eight unknowns."""
    rows = [list(row) + [value] for row, value in zip(matrix, values)]
    for column in range(len(values)):
        pivot = max(range(column, len(values)), key=lambda i: abs(rows[i][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        if abs(divisor) < 1e-12:
            raise ValueError("A négyszög túl lapos a perspektívakorrekcióhoz.")
        rows[column] = [value / divisor for value in rows[column]]
        for i in range(len(values)):
            if i != column:
                factor = rows[i][column]
                rows[i] = [a - factor * b for a, b in zip(rows[i], rows[column])]
    return [row[-1] for row in rows]


def perspective_coefficients(points: list[Point], size: tuple[int, int]):
    """Inverse projective mapping: output rectangle to source TL, TR, BR, BL."""
    matrix, values = [], []
    # Solve in a unit square to avoid ill conditioning with large output sizes.
    for (u, v), (x, y) in zip(((0, 0), (1, 0), (1, 1), (0, 1)), points):
        matrix.extend(((u, v, 1, 0, 0, 0, -x * u, -x * v),
                       (0, 0, 0, u, v, 1, -y * u, -y * v)))
        values.extend((x, y))
    a, b, c, d, e, f, g, h = _solve(matrix, values)
    width, height = size
    return a / width, b / height, c, d / width, e / height, f, g / width, h / height


def rectify_board(source: Image.Image, points: list[Point], board: BoardType, height: int):
    size = (max(1, round(height * board.ratio)), height)
    return source.transform(size, Image.Transform.PERSPECTIVE,
                            perspective_coefficients(points, size),
                            resample=Image.Resampling.BICUBIC)


def offset_polygon(points: list[Point], distance: float) -> list[Point]:
    """Parallel outward edges of a clockwise, convex screen-space polygon."""
    result = []
    for i, point in enumerate(points):
        previous, following = points[i - 1], points[(i + 1) % len(points)]
        dx1, dy1 = point[0] - previous[0], point[1] - previous[1]
        dx2, dy2 = following[0] - point[0], following[1] - point[1]
        length1, length2 = math.hypot(dx1, dy1), math.hypot(dx2, dy2)
        n1, n2 = (dy1 / length1, -dx1 / length1), (dy2 / length2, -dx2 / length2)
        divisor = max(1e-10, 1 + n1[0] * n2[0] + n1[1] * n2[1])
        shift = (distance * (n1[0] + n2[0]) / divisor,
                 distance * (n1[1] + n2[1]) / divisor)
        # Keep very acute corners from producing arbitrarily long spikes.
        factor = min(1, 8 * distance / max(math.hypot(*shift), 1e-10))
        result.append((point[0] + shift[0] * factor, point[1] + shift[1] * factor))
    return result


def draw_frames(canvas: Image.Image, polygons: list[list[Point]], width: int):
    # Compose each hollow frame independently, preserving overlapping objects.
    blue_width = max(1, width // 3)
    red_width = max(1, (width - blue_width) // 2)
    for points in polygons:
        outer = offset_polygon(points, width)
        left = max(0, math.floor(min(p[0] for p in outer)) - 1)
        top = max(0, math.floor(min(p[1] for p in outer)) - 1)
        right = min(canvas.width, math.ceil(max(p[0] for p in outer)) + 2)
        bottom = min(canvas.height, math.ceil(max(p[1] for p in outer)) + 2)
        if right <= left or bottom <= top:
            continue
        with Image.new("RGBA", (right - left, bottom - top)) as overlay:
            draw = ImageDraw.Draw(overlay)
            for shape, color in ((outer, GREEN),
                                 (offset_polygon(points, blue_width + red_width), RED),
                                 (offset_polygon(points, blue_width), BLUE)):
                draw.polygon([(x - left, y - top) for x, y in shape], fill=(*color, 255))
            draw.polygon([(x - left, y - top) for x, y in points], fill=(0, 0, 0, 0))
            canvas.paste(overlay, (left, top), overlay)


def polygon_rect_overlap(points: list[Point], rect) -> float:
    """Exact area of a convex polygon clipped against a candidate label box."""
    clipped = list(points)
    for axis, boundary, sign in ((0, rect[0], 1), (0, rect[2], -1),
                                 (1, rect[1], 1), (1, rect[3], -1)):
        source, clipped = clipped, []
        if not source:
            return 0.0
        previous = source[-1]
        for current in source:
            inside = sign * (current[axis] - boundary) >= 0
            was_inside = sign * (previous[axis] - boundary) >= 0
            if inside != was_inside:
                t = (boundary - previous[axis]) / (current[axis] - previous[axis])
                clipped.append(tuple(previous[j] + t * (current[j] - previous[j]) for j in (0, 1)))
            if inside:
                clipped.append(current)
            previous = current
    return abs(sum(p[0] * clipped[(i + 1) % len(clipped)][1]
                   - p[1] * clipped[(i + 1) % len(clipped)][0]
                   for i, p in enumerate(clipped))) / 2 if clipped else 0.0


def rect_overlap(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def nearest_boundary(point: Point, polygon: list[Point]) -> Point:
    candidates = []
    for i, a in enumerate(polygon):
        b = polygon[(i + 1) % len(polygon)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0, min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / max(dx * dx + dy * dy, 1e-12)))
        candidates.append((a[0] + t * dx, a[1] + t * dy))
    return min(candidates, key=lambda candidate: math.dist(point, candidate))


def place_badges(polygons: list[list[Point]], size: tuple[int, int], diameter: int, gap: int):
    """Prefer nearby external labels, minimizing overlap with all boards and labels."""
    placed = []
    for polygon in polygons:
        left, right = min(p[0] for p in polygon), max(p[0] for p in polygon)
        top, bottom = min(p[1] for p in polygon), max(p[1] for p in polygon)
        candidates = []
        for step in range(4):
            spacing = gap + step * diameter
            for fraction in (0.5, 0, 1, 0.25, 0.75):
                x = left + fraction * (right - left) - diameter / 2
                y = top + fraction * (bottom - top) - diameter / 2
                candidates.extend(((x, top - spacing - diameter), (x, bottom + spacing),
                                   (left - spacing - diameter, y), (right + spacing, y)))
        boxes = []
        for x, y in candidates:
            x, y = round(max(0, min(size[0] - diameter, x))), round(max(0, min(size[1] - diameter, y)))
            boxes.append((x, y, x + diameter, y + diameter))

        def score(box):
            object_overlap = sum(polygon_rect_overlap(other, box) for other in polygons)
            label_overlap = sum(rect_overlap(other, box) for other in placed)
            center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            distance = math.dist(center, nearest_boundary(center, polygon))
            return (object_overlap + 2 * label_overlap) * 1e6 + distance

        placed.append(min(boxes, key=score))
    return placed


@lru_cache(maxsize=64)
def font(size: int, bold=False):
    names = (["C:/Windows/Fonts/seguisb.ttf", "DejaVuSans-Bold.ttf"] if bold else
             ["C:/Windows/Fonts/segoeui.ttf", "DejaVuSans.ttf"])
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    # Pillow 10.0 also supports the default font without a size argument.
    return ImageFont.load_default()


def badge(draw, box, number):
    draw.rounded_rectangle(box, radius=(box[2] - box[0]) * 0.3, fill=INK, outline="white", width=2)
    diameter = box[2] - box[0]
    size = round(diameter * (0.5 if number < 100 else 0.37))
    draw.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2 - 1), str(number),
              font=font(size, True), fill="white", anchor="mm")


def _fit_text(draw, text, maximum, text_font):
    if draw.textlength(text, font=text_font) <= maximum:
        return text
    while text and draw.textlength(text + "…", font=text_font) > maximum:
        text = text[:-1]
    return text + "…"


def grid_layout(types, cell_width, card_height, image_width, image_height, gap=14, pad=16):
    """Choose a compact grid; landscape boards span three portrait-sized columns."""
    spans = [3 if board == BILLBOARD else 1 for board in types]
    candidates = []
    for columns in range(max(spans), min(9, sum(spans)) + 1):
        placements = []
        row, column = 0, 0
        for span in spans:
            if column + span > columns:
                row, column = row + 1, 0
            placements.append((row, column, span))
            column += span
        actual_columns = max(column + span for _, column, span in placements)
        sidebar_width = actual_columns * cell_width + (actual_columns - 1) * gap + 2 * pad
        minimum_width = max(spans) * cell_width + (max(spans) - 1) * gap + 2 * pad
        if sidebar_width > max(minimum_width, 2 * image_width):
            continue
        body_height = max(image_height, (row + 1) * card_height + row * gap + 2 * pad)
        total_width, total_height = image_width + sidebar_width, body_height + 138
        # Prefer a compact landscape sheet, avoiding a very tall, mostly empty photo panel.
        score = total_width * total_height * (1 + 0.15 * abs(math.log(total_width / total_height / 1.8)))
        candidates.append((score, actual_columns, placements, row + 1))
    _, columns, placements, rows = min(candidates, key=lambda item: item[0])
    return columns, placements, rows


def compose_export(source: Image.Image, polygons, ratio=0.003, crop_height=320, title="") -> Image.Image:
    """Original-resolution photo at left; a grid of unmarked, rectified crops at right."""
    if not polygons:
        raise ValueError("Legalább egy poligon szükséges az exporthoz.")
    if not isinstance(crop_height, int) or not 120 <= crop_height <= 1600:
        raise ValueError("A kivágások magassága 120 és 1600 pixel közötti egész szám legyen.")
    width = 3 * line_width(source.size, ratio)
    diameter = max(28, min(64, round(min(source.size) * 0.034)))
    margin = max(40, diameter + width + 10)
    points = [pixel_points(polygon, source.size) for polygon in polygons]
    types = [classify_board(polygon) for polygon in points]
    image_width, image_height = source.width + 2 * margin, source.height + 2 * margin
    header = 94
    gap, pad = 14, 16
    cell_width = max(190, round(crop_height * PORTRAIT.ratio) + 2 * pad)
    card_height = crop_height + 94
    columns, placements, rows = grid_layout(types, cell_width, card_height, image_width, image_height, gap, pad)
    sidebar_width = columns * cell_width + (columns - 1) * gap + 2 * pad
    body_height = max(image_height, rows * card_height + (rows - 1) * gap + 2 * pad)
    with source.convert("RGB") as clean:
        clean.info.clear()
        result = Image.new("RGB", (image_width + sidebar_width, header + body_height + 44), PAPER)
        draw = ImageDraw.Draw(result)
        draw.rectangle((0, 0, result.width, 7), fill=INK)
        draw.text((margin, 29), "REKLÁMTÁBLÁK", font=font(13, True), fill=MUTED)
        filename = _fit_text(draw, title or "Annotált kép", image_width - 2 * margin, font(23, True))
        draw.text((margin, 50), filename, font=font(23, True), fill=INK)
        side_x = image_width
        draw.rectangle((side_x, 7, result.width, result.height), fill="#ffffff")
        draw.line((side_x, 7, side_x, result.height), fill="#d7e1eb", width=1)
        draw.text((side_x + pad, 28), "Táblák közelről", font=font(23, True), fill=INK)
        draw.text((side_x + pad, 62), f"{len(polygons)} objektum  ·  Becsült típusok", font=font(14), fill=MUTED)

        # Center the photo vertically when many cards make the sidebar taller.
        photo_y = header + (body_height - image_height) // 2
        with Image.new("RGB", (image_width, image_height), PAPER) as photo:
            photo.paste(clean, (margin, margin))
            shifted = [[(x + margin, y + margin) for x, y in polygon] for polygon in points]
            boxes = place_badges(shifted, photo.size, diameter, width + 7)
            photo_draw = ImageDraw.Draw(photo)
            for polygon, box in zip(shifted, boxes):
                center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
                target = nearest_boundary(center, polygon)
                photo_draw.line((center, target), fill="white", width=4)
                photo_draw.line((center, target), fill=INK, width=2)
            draw_frames(photo, shifted, width)
            for i, box in enumerate(boxes, 1):
                badge(photo_draw, box, i)
            result.paste(photo, (0, photo_y))

        for i, (polygon, board, placement) in enumerate(zip(points, types, placements), 1):
            row, column, span = placement
            x = side_x + pad + column * (cell_width + gap)
            y = header + pad + row * (card_height + gap)
            card_width = span * cell_width + (span - 1) * gap
            draw.rounded_rectangle((x + 1, y + 3, x + card_width + 1, y + card_height + 3),
                                   radius=12, fill="#e8eef4")
            draw.rounded_rectangle((x, y, x + card_width, y + card_height), radius=12,
                                   fill="#f7f9fc", outline="#dce5ee", width=1)
            badge(draw, (x + 12, y + 12, x + 44, y + 44), i)
            draw.text((x + 54, y + 11), board.name, font=font(16, True), fill=INK)
            draw.text((x + 54, y + 33), f"{board.width_cm} × {board.height_cm} cm", font=font(13), fill=MUTED)
            with rectify_board(clean, polygon, board, crop_height) as crop:
                crop_x, crop_y = x + (card_width - crop.width) // 2, y + 60
                draw.rectangle((crop_x - 1, crop_y - 1, crop_x + crop.width, crop_y + crop.height), fill="#d1dce6")
                result.paste(crop, (crop_x, crop_y))
            footer = _fit_text(draw, "Szemből · egységes magasság", card_width - 24, font(12))
            draw.text((x + 12, y + card_height - 25), footer, font=font(12), fill=MUTED)

        draw.text((margin, result.height - 29), f"{len(polygons)} tábla  /  Azonos szám = azonos objektum",
                  font=font(13), fill=MUTED)
        result.info["source_origin"] = (margin, photo_y + margin)
        return result

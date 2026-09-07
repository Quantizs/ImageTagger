import math
import unittest

from PIL import Image, ImageDraw
from surface_categories import CategorizedPolygon

from export_layout import (
    BILLBOARD, PORTRAIT, BLUE, RED, GREEN, classify_board, compose_export,
    draw_frames, perspective_coefficients, place_badges, polygon_rect_overlap,
    rect_overlap, rectify_board,
)


class LayoutTests(unittest.TestCase):
    def test_classification_uses_pixel_edges_and_ignores_camera_roll(self):
        for board in (PORTRAIT, BILLBOARD):
            for angle in (0, 0.7, 1.4):
                points = [(0, 0), (board.width_cm, 0), (board.width_cm, board.height_cm), (0, board.height_cm)]
                rotated = [(x * math.cos(angle) - y * math.sin(angle),
                            x * math.sin(angle) + y * math.cos(angle)) for x, y in points]
                self.assertEqual(classify_board(rotated), board)

    def test_perspective_mapping_lands_on_all_four_source_corners(self):
        points = [(30, 20), (230, 50), (190, 180), (50, 150)]
        a, b, c, d, e, f, g, h = perspective_coefficients(points, (504, 238))
        for (u, v), (x, y) in zip(((0, 0), (504, 0), (504, 238), (0, 238)), points):
            divisor = g * u + h * v + 1
            self.assertAlmostEqual((a * u + b * v + c) / divisor, x)
            self.assertAlmostEqual((d * u + e * v + f) / divisor, y)

    def test_rectification_preserves_corner_order_and_enlarges_to_physical_ratio(self):
        with Image.new("RGB", (160, 140), "white") as source:
            draw = ImageDraw.Draw(source)
            draw.rectangle((0, 0, 79, 69), fill="red")
            draw.rectangle((80, 0, 159, 69), fill="green")
            draw.rectangle((80, 70, 159, 139), fill="blue")
            draw.rectangle((0, 70, 79, 139), fill="yellow")
            points = [(20, 10), (140, 25), (130, 120), (30, 110)]
            for board in (PORTRAIT, BILLBOARD):
                with rectify_board(source, points, board, 320) as crop:
                    self.assertEqual(crop.size, (round(320 * board.ratio), 320))
                    for position, color in (((0.05, 0.05), (255, 0, 0)), ((0.95, 0.05), (0, 128, 0)),
                                            ((0.95, 0.95), (0, 0, 255)), ((0.05, 0.95), (255, 255, 0))):
                        self.assertEqual(crop.getpixel((int(position[0] * crop.width), int(position[1] * crop.height))), color)

    def test_three_bands_are_ordered_outward_and_do_not_fill_object(self):
        with Image.new("RGB", (200, 200), "white") as image:
            draw_frames(image, [[(50, 50), (150, 50), (150, 150), (50, 150)]], 9)
            self.assertEqual(image.getpixel((100, 100)), (255, 255, 255))
            self.assertEqual(image.getpixel((100, 49)), BLUE)
            self.assertEqual(image.getpixel((100, 45)), RED)
            self.assertEqual(image.getpixel((100, 42)), GREEN)
            self.assertEqual(image.getpixel((100, 39)), (255, 255, 255))

    def test_badges_avoid_nearby_boards_and_each_other(self):
        polygons = [[(100, 100), (180, 100), (180, 240), (100, 240)],
                    [(100, 50), (180, 50), (180, 90), (100, 90)],
                    [(185, 100), (265, 100), (265, 240), (185, 240)]]
        boxes = place_badges(polygons, (400, 340), 28, 8)
        for i, box in enumerate(boxes):
            self.assertTrue(0 <= box[0] < box[2] <= 400)
            self.assertTrue(0 <= box[1] < box[3] <= 340)
            self.assertEqual(sum(polygon_rect_overlap(polygon, box) for polygon in polygons), 0)
            self.assertEqual(sum(rect_overlap(other, box) for other in boxes[:i]), 0)

    def test_sidebar_grows_for_all_objects_without_resizing_source(self):
        polygons = [[(0.1, 0.1), (0.3, 0.1), (0.3, 0.7), (0.1, 0.7)]] * 9
        with Image.new("RGB", (400, 300), "#aabbcc") as source:
            before = source.tobytes()
            with compose_export(source, polygons, crop_height=240) as result:
                self.assertGreater(result.width, source.width)
                self.assertGreater(result.height, 3 * 240)
                x, y = result.info["source_origin"]
                self.assertEqual(result.getpixel((x + 200, y + 150)), (170, 187, 204))
            self.assertEqual(source.tobytes(), before)

    def test_invalid_crop_height_rejected(self):
        with Image.new("RGB", (100, 100)) as source:
            for height in (0, 119, 1601, 240.5):
                with self.subTest(height=height), self.assertRaises(ValueError):
                    compose_export(source, [[(0, 0), (1, 0), (1, 1), (0, 1)]], crop_height=height)

    def test_many_billboards_use_multiple_columns_instead_of_a_tall_strip(self):
        polygons = [CategorizedPolygon([(0.1, 0.1), (0.5, 0.1), (0.5, 0.3), (0.1, 0.3)], "Óriásplakát", "manual")] * 9
        with Image.new("RGB", (1280, 766), "white") as source:
            with compose_export(source, polygons) as result:
                self.assertLess(result.height, 2000)
                self.assertLess(result.width, 4500)
                self.assertGreater(result.width, result.height)


if __name__ == "__main__":
    unittest.main()

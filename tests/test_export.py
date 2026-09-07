import tempfile
import unittest
from pathlib import Path

from PIL import Image

from annotation_store import serialize_annotations
from export_polygons import export_images, line_width, draw_polygons

POLYGONS = [
    [(0.1, 0.2), (0.6, 0.15), (0.65, 0.7), (0.12, 0.75)],
    [(0.7, 0.1), (0.9, 0.1), (0.9, 0.3), (0.7, 0.3)],
]


class ExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.labels = self.directory / "annotations"
        self.labels.mkdir()
        for name in ("marked.png", "empty.png", "missing.png"):
            Image.new("RGB", (400, 300), "white").save(self.directory / name)
        self.label = self.labels / "marked.png.txt"
        self.label.write_text(serialize_annotations(POLYGONS))
        (self.labels / "empty.png.txt").write_text("")

    def test_only_annotated_images_exported_with_sidebar_and_unchanged_originals(self):
        originals = {path: path.read_bytes() for path in self.directory.glob("*.png")}
        report = export_images(self.directory)
        self.assertEqual(report["exported_images"], 1)
        self.assertEqual(report["polygons"], 2)
        self.assertEqual(report["skipped_images"], 2)
        self.assertEqual(report["errors"], [])
        self.assertEqual([path.name for path in (self.directory / "output").glob("*.png")], ["marked.png.png"])
        with Image.open(self.directory / "output" / "marked.png.png") as image:
            self.assertGreater(image.width, 400)
            self.assertGreater(image.height, 300)
            with Image.open(self.directory / "marked.png") as source, draw_polygons(source, POLYGONS) as rendered:
                x, y = rendered.info["source_origin"]
                self.assertEqual(image.getpixel((x + 120, y + 120)), (255, 255, 255))
        for path, content in originals.items():
            self.assertEqual(path.read_bytes(), content)

    def test_rerun_removes_only_previous_export_after_last_polygon_deleted(self):
        export_images(self.directory)
        self.label.write_text("")
        report = export_images(self.directory)
        self.assertEqual(report["exported_images"], 0)
        self.assertEqual(list((self.directory / "output").glob("*.png")), [])

    def test_source_and_annotation_directories_cannot_be_output(self):
        for path in (self.directory, self.labels, self.labels / "nested", self.directory.parent):
            with self.subTest(path=path), self.assertRaises(ValueError):
                export_images(self.directory, path)

    def test_existing_unrelated_output_file_is_preserved(self):
        output = self.directory / "output"
        output.mkdir()
        unrelated = output / "personal.png"
        unrelated.write_bytes(b"preserve")
        with self.assertRaises(ValueError):
            export_images(self.directory)
        self.assertEqual(unrelated.read_bytes(), b"preserve")

    def test_bad_annotation_reported_and_other_images_still_exported(self):
        (self.labels / "empty.png.txt").write_text("broken")
        report = export_images(self.directory)
        self.assertEqual(report["exported_images"], 1)
        self.assertEqual(len(report["errors"]), 1)
        self.assertFalse((self.directory / "output" / "empty.png.png").exists())

    def test_image_boundary_and_grayscale_and_same_stem(self):
        Image.new("L", (400, 300), 255).save(self.directory / "marked.jpg")
        (self.labels / "marked.jpg.txt").write_text("0 0 1 0 1 1 0 1\n")
        export_images(self.directory)
        with Image.open(self.directory / "output" / "marked.jpg.png") as image:
            self.assertEqual(image.mode, "RGB")
            self.assertGreater(image.width, 400)
            self.assertGreater(image.height, 300)
        self.assertTrue((self.directory / "output" / "marked.png.png").exists())

    def test_width_scales_with_shorter_side_and_can_be_adjusted(self):
        self.assertEqual(line_width((100, 50)), 1)
        self.assertEqual(line_width((1920, 1080)), 3)
        self.assertEqual(line_width((2160, 3840)), 6)
        self.assertEqual(line_width((1920, 1080), 0.005), 5)
        for ratio in (0, -1, float("nan"), float("inf"), 0.2):
            with self.subTest(ratio=ratio), self.assertRaises(ValueError):
                export_images(self.directory, ratio=ratio)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from annotation_store import (
    AnnotationStore, atomic_write, parse_annotations, polygon_area,
    serialize_annotations, valid_polygon,
)

RECT = [(0.1, 0.2), (0.6, 0.2), (0.6, 0.7), (0.1, 0.7)]
TRAPEZOID = [(0.2, 0.2), (0.8, 0.2), (0.6, 0.8), (0.4, 0.8)]


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        Image.new("RGB", (200, 100)).save(self.directory / "a.jpg")
        Image.new("RGB", (100, 100)).save(self.directory / "b.png")

    def test_round_trip_and_corner_order(self):
        self.assertEqual(parse_annotations(serialize_annotations([RECT, TRAPEZOID])), [RECT, TRAPEZOID])
        self.assertEqual(len(serialize_annotations([RECT]).split()), 8)
        self.assertAlmostEqual(polygon_area(TRAPEZOID), 0.24)

    def test_bad_coordinates_and_crossing_corners_are_rejected(self):
        for text in ("0 0 1 0", "a b c d e f g h", "0 0 nan 0 1 1 0 1",
                     "0 0 1 0 1 1 -0.1 1", "0 0 1 1 1 0 0 1",
                     "0 0 0 0 1 1 0 1", "0 0 0 1 1 1 1 0"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_annotations(text)
        self.assertFalse(valid_polygon([(0, 0), (1, 0), (0.2, 0.2), (0, 1)]))

    def test_save_and_resume_individual_images(self):
        store = AnnotationStore(self.directory)
        record = store.records[0]
        record.polygons = [RECT, TRAPEZOID]
        record.dirty = True
        store.save_all()
        store.save_session(1)
        restored = AnnotationStore(self.directory)
        self.assertEqual(restored.records[0].polygons, [RECT, TRAPEZOID])
        self.assertEqual(restored.records[1].polygons, [])
        self.assertEqual(restored.restore_index(), 1)
        self.assertFalse(record.dirty)

    def test_delete_last_object_persists_empty_file(self):
        store = AnnotationStore(self.directory)
        record = store.records[0]
        record.polygons = [RECT]
        record.dirty = True
        store.save_all()
        record.polygons.clear()
        record.dirty = True
        store.save_all()
        self.assertEqual(record.annotation_path.read_text(), "")
        self.assertEqual(AnnotationStore(self.directory).records[0].polygons, [])

    def test_same_stem_different_extensions_do_not_collide(self):
        Image.new("RGB", (10, 10)).save(self.directory / "a.png")
        store = AnnotationStore(self.directory)
        paths = [record.annotation_path for record in store.records]
        self.assertEqual(len(paths), len(set(paths)))

    def test_corrupt_annotation_is_preserved(self):
        store = AnnotationStore(self.directory)
        path = store.records[0].annotation_path
        atomic_write(path, "broken annotation")
        store = AnnotationStore(self.directory)
        record = store.records[0]
        self.assertFalse(record.editable)
        store.save_statistics()
        self.assertEqual(path.read_text(), "broken annotation")
        record.dirty = True
        with self.assertRaises(ValueError):
            store.save_record(record)

    def test_failed_replace_preserves_previous_data_and_dirty_flag(self):
        store = AnnotationStore(self.directory)
        record = store.records[0]
        atomic_write(record.annotation_path, serialize_annotations([RECT]))
        record.polygons = [TRAPEZOID]
        record.dirty = True
        with patch("annotation_store.os.replace", side_effect=PermissionError("test")):
            with self.assertRaises(PermissionError):
                store.save_record(record)
        self.assertTrue(record.dirty)
        self.assertEqual(parse_annotations(record.annotation_path.read_text()), [RECT])
        self.assertEqual(list(store.output_directory.glob(".tmp-*")), [])

    def test_statistics_use_polygon_area_and_both_image_denominators(self):
        store = AnnotationStore(self.directory)
        store.records[0].polygons = [RECT, TRAPEZOID]
        store.records[0].dirty = True
        stats = store.save_statistics()
        self.assertEqual(stats["total_objects"], 2)
        self.assertEqual(stats["annotated_images"], 1)
        self.assertAlmostEqual(stats["mean_object_area_px2"], 4900)
        self.assertEqual(stats["mean_objects_per_image"], 1)
        self.assertEqual(stats["mean_objects_per_annotated_image"], 2)
        self.assertEqual(json.loads((store.output_directory / "statistics.json").read_text())["total_objects"], 2)
        self.assertEqual(len((store.output_directory / "statistics_per_image.csv").read_text().splitlines()), 3)

    def test_empty_statistics_have_zero_averages(self):
        stats = AnnotationStore(self.directory).save_statistics()
        for key in ("total_objects", "mean_object_area_px2", "mean_objects_per_image",
                    "mean_objects_per_annotated_image"):
            self.assertEqual(stats[key], 0)

    def test_unreadable_image_is_reported_and_navigation_inventory_survives(self):
        (self.directory / "bad.jpg").write_bytes(b"not an image")
        store = AnnotationStore(self.directory)
        self.assertEqual(len(store.records), 3)
        stats, _ = store.statistics()
        self.assertEqual(stats["images_with_errors"], 1)

    def test_corrupt_session_and_removed_last_image_fall_back(self):
        store = AnnotationStore(self.directory)
        atomic_write(store.output_directory / "session.json", "[]")
        self.assertEqual(store.restore_index(), 0)
        self.assertTrue(store.session_warning)
        atomic_write(store.output_directory / "session.json", '{"last_image": "missing.png"}')
        self.assertEqual(store.restore_index(), 0)


if __name__ == "__main__":
    unittest.main()

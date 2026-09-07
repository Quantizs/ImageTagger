import copy
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from annotation_store import AnnotationStore, parse_annotations, serialize_annotations
from categorize_annotations import categorize_directory
from export_layout import compose_export, grid_layout
from surface_categories import CATEGORIES, CategorizedPolygon, auto_category, edited_polygon, predict_category

RECT = [(0.1, 0.1), (0.5, 0.1), (0.5, 0.6), (0.1, 0.6)]


class CategoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        Image.new("RGB", (1000, 1000), "white").save(self.directory / "a.png")
        self.labels = self.directory / "annotations"
        self.labels.mkdir()
        self.path = self.labels / "a.png.txt"

    def test_all_seven_exact_ratios_classify_using_original_pixel_dimensions(self):
        self.assertEqual(len(CATEGORIES), 7)
        for name, board in CATEGORIES.items():
            height, width = 100, 100 * board.ratio
            points = [(10 / 2000, 10 / 500), ((10 + width) / 2000, 10 / 500),
                      ((10 + width) / 2000, (10 + height) / 500), (10 / 2000, (10 + height) / 500)]
            with self.subTest(name=name):
                self.assertEqual(predict_category(points, (2000, 500)), name)

    def test_legacy_and_categorized_lines_can_coexist_and_round_trip(self):
        polygons = [RECT, CategorizedPolygon(RECT, "BKV_álló", "manual"),
                    CategorizedPolygon(RECT, "Tetőreklám", "auto")]
        text = serialize_annotations(polygons)
        self.assertEqual([len(line.split()) for line in text.splitlines()], [8, 10, 10])
        loaded = parse_annotations(text)
        self.assertEqual(loaded[0], RECT)
        self.assertEqual((loaded[1].category, loaded[1].category_source), ("BKV_álló", "manual"))
        self.assertEqual(serialize_annotations(loaded), text)
        self.assertEqual(serialize_annotations(copy.deepcopy(loaded)), text)

    def test_unknown_category_or_provenance_is_rejected(self):
        coordinates = serialize_annotations([RECT]).strip()
        for suffix in ("unknown manual", "Citylight unknown", "Citylight", "Citylight auto extra"):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                parse_annotations(coordinates + " " + suffix)

    def test_manual_assignment_survives_geometry_edit_and_auto_rerun(self):
        original = CategorizedPolygon(RECT, "Citylight", "manual")
        wide = [(0, 0), (0.9, 0), (0.9, 0.3), (0, 0.3)]
        edited = edited_polygon(original, wide, (1000, 1000))
        self.assertEqual(edited, wide)
        self.assertEqual((edited.category, edited.category_source), ("Citylight", "manual"))
        self.assertEqual(auto_category(edited, (1000, 1000)).category, "Citylight")
        original = CategorizedPolygon(RECT, "Citylight", "auto")
        self.assertEqual(edited_polygon(original, wide, (1000, 1000)).category, "Tetőreklám")

    def test_bulk_migration_preserves_manual_geometry_and_exact_original_backup(self):
        original = ("\ufeff" + serialize_annotations([RECT, CategorizedPolygon(RECT, "Reklámháló", "manual")])).replace("\n", "\r\n").encode("utf-8")
        self.path.write_bytes(original)
        report = categorize_directory(self.directory)
        self.assertEqual(report["changed"], 1)
        self.assertEqual(report["manual_preserved"], 1)
        self.assertEqual(report["errors"], [])
        loaded = parse_annotations(self.path.read_text(encoding="utf-8"))
        self.assertEqual([list(p) for p in loaded], [RECT, RECT])
        self.assertEqual(loaded[1].category, "Reklámháló")
        self.assertEqual(loaded[1].category_source, "manual")
        backup = self.labels / "backups" / "a.png.txt.before_categories.bak"
        self.assertEqual(backup.read_bytes(), original)
        categorized = self.path.read_bytes()
        again = categorize_directory(self.directory)
        self.assertEqual(again["changed"], 0)
        self.assertEqual(self.path.read_bytes(), categorized)
        self.assertEqual(backup.read_bytes(), original)

    def test_dry_run_leaves_every_file_unchanged(self):
        self.path.write_text(serialize_annotations([RECT]), encoding="utf-8")
        before = {p.relative_to(self.directory): p.read_bytes() for p in self.directory.rglob("*") if p.is_file()}
        report = categorize_directory(self.directory, dry_run=True)
        self.assertEqual(report["changed"], 1)
        after = {p.relative_to(self.directory): p.read_bytes() for p in self.directory.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_corrupt_metadata_is_reported_and_preserved(self):
        self.path.write_text(serialize_annotations([RECT]).strip() + " Unknown manual", encoding="utf-8")
        original = self.path.read_bytes()
        self.assertEqual(len(categorize_directory(self.directory)["errors"]), 1)
        self.assertEqual(self.path.read_bytes(), original)

    def test_delete_and_reorder_keep_categories_attached_to_their_polygons(self):
        store = AnnotationStore(self.directory)
        record = store.records[0]
        record.polygons = [CategorizedPolygon(RECT, name, "manual") for name in CATEGORIES]
        record.polygons.reverse()
        del record.polygons[2]
        record.dirty = True
        store.save_all()
        loaded = AnnotationStore(self.directory).records[0]
        expected = list(reversed(CATEGORIES))
        del expected[2]
        self.assertEqual([p.category for p in loaded.polygons], expected)
        self.assertTrue(all(p.category_source == "manual" for p in loaded.polygons))

    def test_export_uses_saved_categories_even_when_geometry_suggests_another_type(self):
        polygons = [CategorizedPolygon(RECT, name, "manual") for name in CATEGORIES]
        with Image.new("RGB", (400, 300), "white") as source:
            with compose_export(source, polygons, crop_height=240) as rendered:
                self.assertEqual(rendered.info["crop_sizes"], [(round(240 * board.ratio), 240) for board in CATEGORIES.values()])
        columns, placements, _ = grid_layout(list(CATEGORIES.values()), 203, 334, 1000, 700)
        for board, (_, column, span) in zip(CATEGORIES.values(), placements):
            self.assertLessEqual(column + span, columns)
            self.assertGreaterEqual(span * 203 + (span - 1) * 14 - 32, round(240 * board.ratio))

    def test_category_statistics_include_uncategorized_and_manual_counts(self):
        self.path.write_text(serialize_annotations([RECT, CategorizedPolygon(RECT, "Citylight", "manual")]), encoding="utf-8")
        stats, _ = AnnotationStore(self.directory).statistics()
        self.assertEqual(stats["objects_per_category"]["Citylight"], 1)
        self.assertEqual(stats["objects_without_category"], 1)
        self.assertEqual(stats["manually_categorized_objects"], 1)


if __name__ == "__main__":
    unittest.main()

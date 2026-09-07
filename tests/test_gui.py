"""Opt-in window tests: set IMAGE_TAGGER_GUI_TESTS=1 before running unittest."""

import json
import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from annotation_store import AnnotationStore, parse_annotations
from image_tagger import ImageTagger


@unittest.skipUnless(os.environ.get("IMAGE_TAGGER_GUI_TESTS") == "1", "GUI tests are opt-in")
class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        Image.new("RGB", (800, 600), "#526d82").save(self.directory / "a.png")
        Image.new("RGB", (400, 300), "#567d65").save(self.directory / "b.png")
        self.root = tk.Tk()
        self.app = ImageTagger(self.root)
        self.root.update()
        self.app.open_directory(self.directory)
        self.root.update()
        self.root.focus_force()
        self.root.update()
        self.addCleanup(self.destroy_root)

    def destroy_root(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def event(self, point):
        x, y = self.app.screen_point(point)
        return SimpleNamespace(x=x, y=y)

    def draw(self, start=(0.1, 0.2), end=(0.6, 0.7)):
        self.app.draw_mode()
        self.app.mouse_down(self.event(start))
        self.app.mouse_move(self.event(end))
        self.app.mouse_up(self.event(end))

    def test_drawing_dragging_keyboard_navigation_and_restart(self):
        self.draw()
        self.draw((0.3, 0.3), (0.8, 0.8))
        self.assertEqual(len(self.app.record.polygons), 2)
        self.app.mouse_down(self.event((0.3, 0.3)))
        self.app.mouse_move(self.event((0.4, 0.25)))
        self.app.mouse_up(self.event((0.4, 0.25)))
        self.assertAlmostEqual(self.app.record.polygons[1][0][0], 0.4)
        saved = parse_annotations(self.app.record.annotation_path.read_text(encoding="utf-8"))
        self.assertEqual(saved, self.app.record.polygons)
        self.root.event_generate("<Right>")
        self.root.update()
        self.assertEqual(self.app.index, 1)
        self.assertEqual(self.app.record.polygons, [])
        self.app.navigate(-1)
        self.assertEqual(self.app.record.polygons, saved)
        self.app.close()
        restored = AnnotationStore(self.directory)
        self.assertEqual(restored.restore_index(), 0)
        self.assertEqual(restored.records[0].polygons, saved)
        self.assertEqual(json.loads((restored.output_directory / "statistics.json").read_text())["total_objects"], 2)

    def test_delete_undo_redo_and_empty_file(self):
        self.draw()
        self.app.delete_selected()
        self.assertEqual(self.app.record.polygons, [])
        self.assertEqual(self.app.record.annotation_path.read_text(), "")
        self.app.undo()
        self.assertEqual(len(self.app.record.polygons), 1)
        self.app.redo()
        self.assertEqual(self.app.record.polygons, [])

    def test_escape_restores_pre_drag_geometry_even_after_autosave(self):
        self.draw()
        before = self.app.record.annotation_path.read_text()
        self.app.mouse_down(self.event((0.1, 0.2)))
        self.app.mouse_move(self.event((0.2, 0.1)))
        self.app.autosave()
        self.assertNotEqual(self.app.record.annotation_path.read_text(), before)
        self.app.cancel_drag()
        self.assertEqual(self.app.record.annotation_path.read_text(), before)

    def test_crossing_corners_rejected_and_moving_clamped_to_image(self):
        self.draw()
        before = self.app.record.annotation_path.read_text()
        self.app.mouse_down(self.event((0.1, 0.2)))
        self.app.mouse_up(self.event((0.9, 0.9)))
        self.assertEqual(self.app.record.annotation_path.read_text(), before)
        self.app.mouse_down(self.event((0.3, 0.4)))
        self.app.mouse_up(self.event((1, 1)))
        polygon = self.app.record.polygons[0]
        self.assertAlmostEqual(max(p[0] for p in polygon), 1)
        self.assertAlmostEqual(max(p[1] for p in polygon), 1)

    def test_zoom_keeps_point_under_cursor_and_edit_coordinates(self):
        self.draw()
        before = self.app.record.polygons.copy()
        event = self.event((0.35, 0.45))
        self.app.zoom(event, 1)
        actual = self.app.image_point(event.x, event.y)
        self.assertAlmostEqual(actual[0], 0.35)
        self.assertAlmostEqual(actual[1], 0.45)
        self.assertEqual(self.app.record.polygons, before)
        self.app.fit_image()

    def test_failed_save_blocks_navigation_and_keeps_changes(self):
        self.draw()
        self.app.record.dirty = True
        with patch.object(self.app.store, "save_all", side_effect=PermissionError("test")), \
                patch("image_tagger.messagebox.showerror"):
            self.app.navigate(1)
        self.assertEqual(self.app.index, 0)
        self.assertTrue(self.app.record.dirty)
        self.assertEqual(len(self.app.record.polygons), 1)
        self.assertIn("MENTÉSI HIBA", self.app.status_var.get())

    def test_new_object_gets_auto_category_and_manual_selection_persists_through_edits(self):
        self.draw((0.1, 0.1), (0.225, 0.1 + 140 / 600))
        polygon = self.app.record.polygons[0]
        self.assertEqual((polygon.category, polygon.category_source), ("Kandeláber", "auto"))
        self.app.category_var.set("Citylight")
        self.app.category_combo.event_generate("<<ComboboxSelected>>")
        self.root.update()
        self.assertEqual(self.app.record.polygons[0].category_source, "manual")
        self.app.mouse_down(self.event((0.1, 0.1)))
        self.app.mouse_up(self.event((0.08, 0.08)))
        self.app.mouse_down(self.event((0.16, 0.2)))
        self.app.mouse_up(self.event((0.3, 0.3)))
        loaded = AnnotationStore(self.directory).records[0].polygons[0]
        self.assertEqual((loaded.category, loaded.category_source), ("Citylight", "manual"))
        self.app.navigate(1)
        self.app.navigate(-1)
        self.assertEqual(self.app.record.polygons[0].category, "Citylight")

    def test_manual_category_and_reset_to_auto_are_undoable(self):
        self.draw()
        automatic = self.app.record.polygons[0].category
        self.app.category_var.set("BKV_álló")
        self.app.set_manual_category()
        self.app.undo()
        self.assertEqual(self.app.record.polygons[0].category, automatic)
        self.assertEqual(self.app.record.polygons[0].category_source, "auto")
        self.app.redo()
        self.assertEqual(self.app.record.polygons[0].category, "BKV_álló")
        self.app.selected = 0
        self.app.reset_auto_category()
        self.assertEqual(self.app.record.polygons[0].category, automatic)
        self.app.undo()
        self.assertEqual(self.app.record.polygons[0].category_source, "manual")

    def test_folder_categorization_protects_even_manual_confirmation_of_same_value(self):
        self.draw()
        self.app.set_manual_category()
        self.app.record.polygons.append([(0.1, 0.1), (0.9, 0.1), (0.9, 0.4), (0.1, 0.4)])
        self.app.changed()
        with patch("image_tagger.messagebox.showinfo"):
            self.app.categorize_folder()
        loaded = AnnotationStore(self.directory).records[0].polygons
        self.assertEqual(loaded[0].category_source, "manual")
        self.assertEqual(loaded[1].category_source, "auto")

    def test_category_selector_arrows_do_not_navigate_images(self):
        self.draw()
        self.app.category_combo.focus_force()
        self.root.update()
        self.app.category_combo.event_generate("<Right>")
        self.root.update()
        self.assertEqual(self.app.index, 0)


if __name__ == "__main__":
    unittest.main()

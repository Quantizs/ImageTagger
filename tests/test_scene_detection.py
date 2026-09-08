import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image, ImageColor

from export_layout import compose_export, detection_radius, draw_detections, PEOPLE_COLOR, VEHICLE_COLOR
from export_polygons import export_images
from scene_detection import COCO_CLASSES, Detection, YoloSceneDetector, detection_counts


def tensor(values):
    result = Mock()
    result.cpu.return_value.tolist.return_value = values
    return result


class SceneDetectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.weights = self.directory / "yolo11l.pt"

    def fake_model(self, coords, classes, scores):
        boxes = SimpleNamespace(xyxy=tensor(coords), cls=tensor(classes), conf=tensor(scores))
        model = Mock(task="detect", names=COCO_CLASSES)
        model.predict.return_value = [SimpleNamespace(boxes=boxes)]
        return model

    def test_model_maps_classes_filters_and_keeps_original_pixel_centers(self):
        model = self.fake_model([[10, 20, 50, 80], [80, 50, 200, 150], [0, 0, 50, 50],
                                 [20, 20, 40, 40], [20, 20, 20, 30]],
                                [0, 2, 16, 0, 0], [.9, .8, .99, .1, .99])
        factory = Mock(return_value=model)
        with patch.dict("sys.modules", {"ultralytics": SimpleNamespace(YOLO=factory)}):
            detector = YoloSceneDetector(self.weights, image_size=1280)
        with Image.new("RGB", (400, 300), "white") as source:
            source.info["exif"] = b"ignored metadata"
            detections = detector.detect(source)
            detector.detect(source)
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(model.predict.call_count, 2)
        self.assertEqual(detection_counts(detections), {"people": 1, "vehicles": 1})
        self.assertEqual(detections[0].center, (30, 50))
        self.assertEqual(detections[1].center, (140, 100))
        options = model.predict.call_args.kwargs
        self.assertEqual(options["classes"], list(COCO_CLASSES))
        self.assertEqual(options["imgsz"], 1280)
        self.assertFalse(options["save"])
        self.assertEqual(options["source"].info, {})

    def test_zero_detections_is_valid_but_missing_result_is_an_error(self):
        model = self.fake_model([], [], [])
        with patch.dict("sys.modules", {"ultralytics": SimpleNamespace(YOLO=Mock(return_value=model))}):
            detector = YoloSceneDetector(self.weights)
        with Image.new("RGB", (100, 100)) as source:
            self.assertEqual(detector.detect(source), [])
            model.predict.return_value = []
            with self.assertRaises(RuntimeError):
                detector.detect(source)

    def test_wrong_class_map_fails_instead_of_reporting_misleading_counts(self):
        model = self.fake_model([], [], [])
        model.names = {0: "car"}
        with patch.dict("sys.modules", {"ultralytics": SimpleNamespace(YOLO=Mock(return_value=model))}):
            with self.assertRaises(RuntimeError):
                YoloSceneDetector(self.weights)

    def test_marker_colors_and_sizes_are_independent_of_box_size(self):
        detections = [Detection("person", (10, 10, 110, 110), .9, "person"),
                      Detection("vehicle", (198, 198, 202, 202), .9, "car")]
        with Image.new("RGB", (300, 300), "white") as image:
            draw_detections(image, detections, image.size)
            radius = detection_radius(image.size)
            self.assertEqual(image.getpixel((60 + radius - 2, 60)), ImageColor.getrgb(PEOPLE_COLOR))
            self.assertEqual(image.getpixel((200 + radius - 2, 200)), ImageColor.getrgb(VEHICLE_COLOR))
            self.assertEqual(image.getpixel((10, 10)), (255, 255, 255))
        self.assertEqual(detection_radius((1920, 1080)), 15)
        self.assertEqual(detection_radius((3840, 2160)), 30)

    def test_detections_on_every_image_but_only_annotated_images_exported(self):
        labels = self.directory / "annotations"
        labels.mkdir()
        for name in ("a.png", "b.png", "c.png"):
            Image.new("RGB", (200, 200), "white").save(self.directory / name)
        (labels / "a.png.txt").write_text("0.1 0.1 0.9 0.1 0.9 0.9 0.1 0.9\n")
        (labels / "b.png.txt").write_text("")
        detector = Mock()
        detector.detect.return_value = [Detection("person", (10, 10, 20, 20), .9, "person")]
        with patch("export_polygons.YoloSceneDetector", return_value=detector) as factory:
            report = export_images(self.directory)
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(detector.detect.call_count, 3)
        self.assertEqual(report["detected_images"], 3)
        self.assertEqual(report["people"], 3)
        self.assertEqual(report["exported_images"], 1)
        self.assertEqual(len(list((self.directory / "output").glob("*.png"))), 1)

    def test_detection_failure_preserves_previous_export(self):
        labels = self.directory / "annotations"
        labels.mkdir()
        Image.new("RGB", (200, 200), "white").save(self.directory / "a.png")
        (labels / "a.png.txt").write_text("0.1 0.1 0.9 0.1 0.9 0.9 0.1 0.9\n")
        export_images(self.directory, detect_scene=False)
        output = self.directory / "output" / "a.png.png"
        original = output.read_bytes()
        detector = Mock()
        detector.detect.side_effect = RuntimeError("inference failed")
        with self.assertRaises(RuntimeError):
            export_images(self.directory, detector=detector)
        self.assertEqual(output.read_bytes(), original)

    def test_counts_include_zero_and_sidebar_crops_stay_unmarked(self):
        polygons = [[(.1, .1), (.9, .1), (.9, .9), (.1, .9)]]
        detections = [Detection("person", (40, 40, 160, 160), .9, "person")]
        from export_layout import rectify_board
        crop_colors = []

        def capture_crop(*args):
            crop = rectify_board(*args)
            crop_colors.append(crop.getpixel((crop.width // 2, crop.height // 2)))
            return crop

        with Image.new("RGB", (200, 200), "white") as image:
            with patch("export_layout.rectify_board", side_effect=capture_crop):
                with compose_export(image, polygons, detections=detections) as result:
                    self.assertEqual(result.info["detection_counts"], {"people": 1, "vehicles": 0})
            with compose_export(image, polygons, detections=[]) as result:
                self.assertEqual(result.info["detection_counts"], {"people": 0, "vehicles": 0})
            self.assertEqual(image.getpixel((100, 100)), (255, 255, 255))
        self.assertEqual(crop_colors, [(255, 255, 255)])

    def test_invalid_detector_options_are_rejected_before_loading(self):
        for confidence in (0, -1, float("nan"), 1.1):
            with self.subTest(confidence=confidence), self.assertRaises(ValueError):
                YoloSceneDetector(self.weights, confidence=confidence)
        for size in (0, 31, 4097, 1280.5):
            with self.subTest(size=size), self.assertRaises(ValueError):
                YoloSceneDetector(self.weights, image_size=size)


if __name__ == "__main__":
    unittest.main()

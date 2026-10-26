"""Check mask rejection and safe JSON forest inference."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

SHAPE_AVAILABLE = (importlib.util.find_spec("cv2") is not None and
                   importlib.util.find_spec("sklearn") is not None)
if SHAPE_AVAILABLE:
    from sklearn.ensemble import RandomForestClassifier
    from src.tie_mount_shape_rf import (FEATURE_NAMES, MODEL_FORMAT, SEGMENTATION_SPEC, ShapeUnavailable,
                                        classify_crop, classify_photo_cascade, export_forest,
                                        extract_features, extract_with_fallback,
                                        load_forest, probability)


@unittest.skipUnless(SHAPE_AVAILABLE, "install requirements-shape.txt for optional outline RF tests")
class ShapeRFTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = Path(__file__).resolve().parents[1] / "build" / "work"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.temp_root = Path(self.temporary.name)

    def test_part_features_and_boundary_rejection(self) -> None:
        image = Image.new("RGB", (256, 256), (117, 76, 39))
        ImageDraw.Draw(image).rectangle((35, 35, 220, 220), fill=(235, 235, 232))
        features, quality = extract_features(image)
        self.assertEqual(features.shape, (len(FEATURE_NAMES),))
        self.assertTrue(np.isfinite(features).all())
        self.assertEqual(quality["mask"], "grabcut_lab_center_border")
        clipped = Image.new("RGB", (256, 256), (117, 76, 39))
        ImageDraw.Draw(clipped).rectangle((0, 35, 220, 220), fill=(235, 235, 232))
        with self.assertRaisesRegex(ShapeUnavailable, "boundary"):
            extract_features(clipped)

    def test_json_tree_matches_sklearn_and_hash_is_checked(self) -> None:
        rng = np.random.default_rng(7)
        samples = rng.normal(size=(40, len(FEATURE_NAMES)))
        labels = np.asarray([0, 1] * 20)
        model = RandomForestClassifier(n_estimators=9, max_depth=3, random_state=3)
        model.fit(samples, labels)
        forest = export_forest(model)
        for vector, expected in zip(samples, model.predict_proba(samples)[:, 1]):
            self.assertAlmostEqual(probability(vector, forest), expected, places=12)
        with tempfile.TemporaryDirectory(dir=self.temp_root) as temp:
            directory = Path(temp)
            model_path = directory / "model.json"
            manifest_path = directory / "manifest.json"
            model_path.write_text(json.dumps(forest), encoding="utf-8")
            manifest_path.write_text(json.dumps({"format": MODEL_FORMAT,
                                                 "segmentation": SEGMENTATION_SPEC,
                                                 "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest()}),
                                     encoding="utf-8")
            loaded, _ = load_forest(model_path, manifest_path)
            self.assertEqual(loaded["feature_names"], list(FEATURE_NAMES))
            model_path.write_text(model_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                load_forest(model_path, manifest_path)

    def test_bad_segmentation_is_unavailable_not_good(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.temp_root) as temp:
            photo = Path(temp) / "blank.png"
            Image.new("RGB", (256, 256), (0, 0, 0)).save(photo)
            result = classify_crop(photo, {"format": MODEL_FORMAT,
                                           "feature_names": list(FEATURE_NAMES), "trees": []})
            self.assertEqual(result["verdict"], "unavailable")

    def test_wider_original_fallback_checks_source_hash(self) -> None:
        source = Image.new("RGB", (512, 512), (117, 76, 39))
        ImageDraw.Draw(source).rectangle((100, 100, 380, 380), fill=(235, 235, 232))
        photo = self.temp_root / "original.png"
        source.save(photo)
        unusable_primary = Image.new("RGB", (256, 256), (0, 0, 0))
        with self.assertRaisesRegex(ShapeUnavailable, "hash mismatch"):
            extract_with_fallback(unusable_primary, photo, (56, 56, 456, 456), "0" * 64)
        vector, quality = extract_with_fallback(
            unusable_primary, photo, (56, 56, 456, 456), hashlib.sha256(photo.read_bytes()).hexdigest())
        self.assertEqual(vector.shape, (len(FEATURE_NAMES),))
        self.assertEqual(quality["crop_variant"], "wider_original_photo")
        self.assertEqual(quality["crop_box_original_xyxy"], [0.0, 0.0, 512.0, 512.0])

    def test_second_route_keeps_binary_verdict_and_review_flag(self) -> None:
        photo = self.temp_root / "input.png"
        Image.new("RGB", (256, 256), (117, 76, 39)).save(photo)
        forest = {"format": MODEL_FORMAT, "feature_names": list(FEATURE_NAMES),
                  "segmentation": SEGMENTATION_SPEC,
                  "trees": [{"left": [-1], "right": [-1], "feature": [-2],
                             "threshold": [-2.0], "defect_probability": [0.2]}]}
        quality = {"crop_variant": "frozen_primary_relaxed",
                   "crop_box_original_xyxy": [0, 0, 256, 256], "border_contact": True}
        with patch("src.tie_mount_shape_rf.crop_mount", return_value=(Image.new("RGB", (256, 256)),
                                                                      {"crop_box": [0, 0, 256, 256],
                                                                       "source_size": [256, 256]})), \
             patch("src.tie_mount_shape_rf.extract_with_fallback", side_effect=ShapeUnavailable("border")), \
             patch("src.tie_mount_shape_rf.extract_relaxed_with_fallback",
                   return_value=(np.zeros(len(FEATURE_NAMES)), quality)):
            result = classify_photo_cascade(photo, forest, forest)
        self.assertEqual(result["verdict"], "good")
        self.assertEqual(result["route"], "relaxed_border_contact")
        self.assertTrue(result["low_quality"])
        self.assertTrue(result["review_recommended"])

    def test_relocated_strict_route_saves_actual_crop_and_box(self) -> None:
        photo = self.temp_root / "raw.png"
        Image.new("RGB", (256, 256), (117, 76, 39)).save(photo)
        used = self.temp_root / "used.png"
        forest = {"format": MODEL_FORMAT, "feature_names": list(FEATURE_NAMES),
                  "segmentation": SEGMENTATION_SPEC,
                  "trees": [{"left": [-1], "right": [-1], "feature": [-2],
                             "threshold": [-2.0], "defect_probability": [0.2]}]}
        quality = {"crop_variant": "relocated_padded_original",
                   "crop_box_original_xyxy": [-10, 12, 246, 268], "border_contact": False}
        relocated = Image.new("RGB", (256, 256), (235, 235, 232))
        with patch("src.tie_mount_shape_rf.crop_mount", return_value=(Image.new("RGB", (256, 256)),
                                                                      {"crop_box": [0, 0, 256, 256],
                                                                       "source_size": [256, 256]})), \
             patch("src.tie_mount_shape_rf.extract_strict_with_relocation",
                   return_value=(np.zeros(len(FEATURE_NAMES)), quality)), \
             patch("src.tie_mount_shape_rf.relocate_photo", return_value=(relocated, {})):
            result = classify_photo_cascade(photo, forest, forest, used_crop_output=used)
        self.assertEqual(result["verdict"], "good")
        self.assertEqual(result["route"], "strict_relocated")
        self.assertEqual(result["quality"]["crop_box_original_xyxy"], [-10, 12, 246, 268])
        self.assertEqual(result["used_crop_sha256"], hashlib.sha256(used.read_bytes()).hexdigest())
        self.assertTrue(result["review_recommended"])


if __name__ == "__main__":
    unittest.main()

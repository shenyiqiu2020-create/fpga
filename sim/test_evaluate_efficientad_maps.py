"""Checks for map-to-image matching and image-level AUROC."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from sim.evaluate_efficientad_maps import (
    checked_reference_difference,
    classify_with_normal_validation,
    evaluate,
    image_auc,
    pixel_auc,
)


class EfficientAdMapEvaluationTests(unittest.TestCase):
    def test_tied_scores_have_half_credit(self) -> None:
        self.assertAlmostEqual(image_auc([0, 0, 1, 1], [0.1, 0.2, 0.2, 0.3]), 0.875)

    def test_threshold_uses_only_normal_validation_and_strict_comparison(self) -> None:
        rows = [
            {"label": 0, "score_max": 0.4},
            {"label": 0, "score_max": 0.6},
            {"label": 1, "score_max": 0.5},
            {"label": 1, "score_max": 0.9},
        ]
        threshold, counts = classify_with_normal_validation([0.1, 0.5], rows)
        self.assertEqual(threshold, 0.5)
        self.assertEqual(counts, {"tp": 1, "fn": 1, "tn": 1, "fp": 1})
        self.assertEqual([row["predicted_defect"] for row in rows], [0, 1, 0, 1])

    def test_reconstructed_map_must_match_saved_reference(self) -> None:
        reference = np.zeros((2, 2), dtype=np.float32)
        self.assertEqual(checked_reference_difference(reference, reference.copy()), 0.0)
        with self.assertRaisesRegex(ValueError, "differs"):
            checked_reference_difference(reference, np.ones((2, 2), dtype=np.float32))

    def test_pixel_auc_handles_ties_and_bad_masks(self) -> None:
        mask = np.array([[0, 0], [1, 1]], dtype=np.uint8)
        scores = np.array([[0.1, 0.2], [0.2, 0.3]], dtype=np.float32)
        self.assertAlmostEqual(pixel_auc(mask, scores), 0.875)
        with self.assertRaisesRegex(ValueError, "defect and background"):
            pixel_auc(np.zeros((2, 2), dtype=np.uint8), scores)
        with self.assertRaisesRegex(ValueError, "matching 2D"):
            pixel_auc(mask, scores[:, :1])

    def test_matches_each_map_to_its_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class_root = root / "bottle"
            maps_root = root / "maps"
            for category, score in (("good", 0.1), ("broken", 0.9)):
                image_dir = class_root / "test" / category
                map_dir = maps_root / category
                image_dir.mkdir(parents=True)
                map_dir.mkdir(parents=True)
                Image.fromarray(np.zeros((3, 4, 3), dtype=np.uint8)).save(image_dir / "000.png")
                Image.fromarray(np.full((3, 4), score, dtype=np.float32)).save(map_dir / "000.tiff")
            rows, summary = evaluate(class_root, maps_root)
            self.assertEqual(len(rows), 2)
            self.assertEqual(summary["image_auroc_percent"], 100.0)
            (maps_root / "broken/000.tiff").unlink()
            with self.assertRaisesRegex(ValueError, "1 missing"):
                evaluate(class_root, maps_root)


if __name__ == "__main__":
    unittest.main()

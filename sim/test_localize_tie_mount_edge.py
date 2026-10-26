"""Synthetic checks for the fixed outer-edge localization candidate."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from sim.localize_tie_mount_edge import expected_edge_band, localize


BACKGROUND = (40, 100, 40)
PART = (220, 220, 215)


def sample(kind: str, angle: int = 0) -> tuple[Image.Image, np.ndarray]:
    crop = Image.new("RGB", (256, 256), BACKGROUND)
    draw = ImageDraw.Draw(crop)
    draw.rectangle((32, 32, 223, 223), fill=PART)
    score_map = np.zeros((256, 256), dtype=np.float32)
    score_map[128, 128] = 10.0  # stronger, unrelated interior response
    if kind == "corner":
        draw.polygon(((176, 32), (223, 32), (223, 80)), fill=BACKGROUND)
        score_map[48:53, 203:208] = 6.0  # inside the missing expected corner
    elif kind == "edge":
        draw.rectangle((115, 32, 141, 58), fill=BACKGROUND)
        score_map[46:51, 126:131] = 6.0  # inside the missing edge notch
    else:
        raise ValueError(kind)
    if angle:
        crop = crop.rotate(angle, resample=Image.Resampling.NEAREST,
                           fillcolor=BACKGROUND)
        rotated = Image.fromarray(score_map, mode="F").rotate(
            angle, resample=Image.Resampling.NEAREST, fillcolor=0)
        score_map = np.asarray(rotated, dtype=np.float32)
    return crop, score_map


class EdgeLocalizationTest(unittest.TestCase):
    def _check_missing_region(self, kind: str, angle: int) -> None:
        crop, score_map = sample(kind, angle)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_path, map_path, output_dir = root / "crop.png", root / "fused.tiff", root / "out"
            crop.save(image_path)
            Image.fromarray(score_map, mode="F").save(map_path)
            result = localize(image_path, map_path, output_dir)
            self.assertEqual(result["raw_global_peak_xy_score"]["score"], 10.0)
            self.assertEqual(result["expected_edge_peak_xy_score"]["score"], 6.0)
            self.assertFalse(result["raw_peak_in_expected_edge_band"])
            self.assertTrue((output_dir / "preview.png").is_file())
            self.assertTrue((output_dir / "expected_edge_band.png").is_file())
            self.assertEqual(result, json.loads((output_dir / "result.json").read_text()))
            self.assertEqual(result["purpose"],
                             "candidate outer-edge localization, not a defect verdict")

    def test_missing_corner_remains_in_expected_band(self) -> None:
        self._check_missing_region("corner", 0)

    def test_middle_edge_notch_remains_in_expected_band(self) -> None:
        self._check_missing_region("edge", 0)

    def test_rotated_edge_notch(self) -> None:
        self._check_missing_region("edge", 15)

    def test_rejects_ambiguous_crop_and_nonfinite_map(self) -> None:
        with self.assertRaisesRegex(ValueError, "isolated reliably"):
            expected_edge_band(Image.new("RGB", (256, 256), PART))
        crop, score_map = sample("corner")
        score_map[0, 0] = np.inf
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            crop.save(root / "crop.png")
            Image.fromarray(score_map, mode="F").save(root / "map.tiff")
            with self.assertRaisesRegex(ValueError, "nonfinite"):
                localize(root / "crop.png", root / "map.tiff", root / "out")
            self.assertFalse((root / "out").exists())


if __name__ == "__main__":
    unittest.main()

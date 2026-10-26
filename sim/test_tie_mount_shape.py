"""Synthetic checks for the separate outer-contour candidate diagnostic."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from src.tie_mount_shape import analyze_crop, analyze_image


BACKGROUND = (170, 150, 130)
PART = (190, 220, 235)  # colored light defeats the original low-chroma mask


def complete_part() -> Image.Image:
    image = Image.new("RGB", (256, 256), BACKGROUND)
    ImageDraw.Draw(image).rectangle((50, 50, 205, 205), fill=PART)
    return image


class TieMountShapeTest(unittest.TestCase):
    def test_complete_part_has_low_outer_contour_evidence(self) -> None:
        result = analyze_image(complete_part())
        self.assertEqual(result["status"], "uncertain")
        self.assertLess(result["relative_depth_score"], 0.02)
        self.assertIsNone(result["candidate"])
        self.assertFalse(result["validated_location"])

    def test_middle_edge_notch_is_localized_even_when_rotated(self) -> None:
        image = complete_part()
        ImageDraw.Draw(image).rectangle((112, 50, 144, 90), fill=BACKGROUND)
        straight = analyze_image(image)
        self.assertEqual(straight["status"], "candidate")
        self.assertGreater(straight["relative_depth_score"], 0.2)
        self.assertAlmostEqual(straight["candidate"]["expected_edge_xy"][1], 50, delta=2)
        self.assertTrue(105 <= straight["candidate"]["expected_edge_xy"][0] <= 150)

        rotated = image.rotate(27, resample=Image.Resampling.BILINEAR,
                               fillcolor=BACKGROUND)
        rotated_result = analyze_image(rotated)
        self.assertEqual(rotated_result["status"], "candidate")
        self.assertGreater(rotated_result["relative_depth_score"], 0.2)

    def test_missing_corner_is_a_candidate(self) -> None:
        image = complete_part()
        ImageDraw.Draw(image).polygon([(155, 50), (205, 50), (205, 100)],
                                      fill=BACKGROUND)
        result = analyze_image(image)
        self.assertEqual(result["status"], "candidate")
        self.assertGreater(result["relative_depth_score"], 0.2)
        x, y = result["candidate"]["expected_edge_xy"]
        self.assertGreater(x, 150)
        self.assertLess(y, 105)

    def test_internal_hole_is_not_outer_loss(self) -> None:
        image = complete_part()
        ImageDraw.Draw(image).ellipse((115, 115, 140, 140), fill=BACKGROUND)
        result = analyze_image(image)
        self.assertEqual(result["status"], "uncertain")
        self.assertLess(result["relative_depth_score"], 0.02)
        self.assertIsNone(result["candidate"])

    def test_clipped_source_is_rejected(self) -> None:
        image = Image.new("RGB", (256, 256), BACKGROUND)
        ImageDraw.Draw(image).rectangle((0, 50, 165, 205), fill=PART)
        result = analyze_image(image)
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("crop boundary", result["reason"])
        self.assertIsNone(result["candidate"])

    def test_unavailable_result_is_recorded_without_a_preview_marker(self) -> None:
        image = Image.new("RGB", (256, 256), BACKGROUND)
        ImageDraw.Draw(image).rectangle((0, 50, 165, 205), fill=PART)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temporary:
            root = Path(temporary)
            crop_path = root / "clipped.png"
            image.save(crop_path)
            output_dir = root / "result"
            result = analyze_crop(crop_path, output_dir)
            saved = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(saved["status"], "unavailable")
            self.assertFalse((output_dir / "preview.png").exists())

    def test_requires_256_square_crop(self) -> None:
        with self.assertRaisesRegex(ValueError, "256x256"):
            analyze_image(Image.new("RGB", (200, 200), BACKGROUND))


if __name__ == "__main__":
    unittest.main()

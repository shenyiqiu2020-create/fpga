"""Regression checks for full-part framing at different rotations."""

from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from src.tie_mount_crop import locate_mount


class TieMountCropTest(unittest.TestCase):
    def test_rotated_part_fits_with_less_than_default_padding(self) -> None:
        image = Image.new("RGB", (300, 400), (100, 150, 100))
        ImageDraw.Draw(image).polygon(
            [(150, 70), (285, 200), (150, 330), (15, 200)],
            fill=(230, 230, 230),
        )

        left, top, right, bottom = locate_mount(image)

        self.assertEqual((right - left, bottom - top), (300, 300))
        self.assertEqual(left, 0)
        self.assertLess(top, 70)
        self.assertGreater(bottom, 330)

    def test_clipped_part_at_frame_edge_is_rejected(self) -> None:
        image = Image.new("RGB", (300, 400), (100, 150, 100))
        ImageDraw.Draw(image).rectangle((40, 0, 260, 130), fill=(230, 230, 230))

        with self.assertRaisesRegex(ValueError, "touches the image boundary"):
            locate_mount(image)


if __name__ == "__main__":
    unittest.main()

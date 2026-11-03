"""Regression checks for full-part framing at different rotations."""

from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from src.tie_mount_crop import locate_mount, white_foreground_mask


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

    def test_separate_white_edge_glare_does_not_reject_centered_part(self) -> None:
        image = Image.new("RGB", (300, 400), (100, 150, 100))
        draw = ImageDraw.Draw(image)
        draw.rectangle((70, 100, 230, 260), fill=(230, 230, 230))
        draw.rectangle((0, 20, 3, 80), fill=(230, 230, 230))

        left, top, right, bottom = locate_mount(image)
        self.assertLess(left, 70)
        self.assertLess(top, 100)
        self.assertGreater(right, 230)
        self.assertGreater(bottom, 260)

    def test_blue_cast_part_uses_fallback_on_warm_background(self) -> None:
        image = Image.new("RGB", (300, 400), (175, 155, 135))
        ImageDraw.Draw(image).rectangle((70, 120, 230, 280), fill=(190, 220, 235))

        self.assertFalse(white_foreground_mask(image).any())
        self.assertEqual(locate_mount(image), (52, 102, 249, 299))

    def test_blue_cast_part_beats_bright_mat_at_frame(self) -> None:
        image = Image.new("RGB", (300, 400), (115, 145, 105))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 299, 80), fill=(165, 180, 155))
        draw.rectangle((70, 120, 230, 280), fill=(190, 220, 235))

        self.assertTrue(white_foreground_mask(image)[0].any())
        self.assertEqual(locate_mount(image), (52, 102, 249, 299))

    def test_blue_cast_edge_notch_stays_in_crop(self) -> None:
        image = Image.new("RGB", (300, 400), (175, 155, 135))
        ImageDraw.Draw(image).polygon(
            [(70, 100), (230, 100), (230, 145), (195, 145),
             (195, 180), (230, 180), (230, 260), (70, 260)],
            fill=(190, 220, 235),
        )

        left, top, right, bottom = locate_mount(image)
        self.assertLess(left, 70)
        self.assertLess(top, 100)
        self.assertGreater(right, 230)
        self.assertGreater(bottom, 260)

    def test_blue_cast_part_clipped_by_source_frame_is_rejected(self) -> None:
        image = Image.new("RGB", (300, 400), (175, 155, 135))
        ImageDraw.Draw(image).rectangle((0, 120, 175, 280), fill=(190, 220, 235))

        with self.assertRaisesRegex(ValueError, "touches the image boundary"):
            locate_mount(image)


if __name__ == "__main__":
    unittest.main()

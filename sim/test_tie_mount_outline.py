"""Geometry checks for a square photographed at arbitrary planar rotations."""

from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from src.tie_mount_crop import white_foreground_mask
from src.tie_mount_outline import corner_loss_score


class TieMountOutlineTest(unittest.TestCase):
    def test_corner_loss_score_at_unseen_planar_rotations(self) -> None:
        background = (82, 137, 81)
        for damaged in (False, True):
            base = Image.new("RGB", (320, 320), background)
            draw = ImageDraw.Draw(base)
            draw.rounded_rectangle((60, 60, 260, 260), radius=5,
                                   fill=(232, 232, 232))
            if damaged:
                draw.polygon(((208, 60), (260, 60), (260, 112)), fill=background)
            for rotation in (0, 17, 35, 62, 83):
                with self.subTest(damaged=damaged, rotation=rotation):
                    image = base.rotate(rotation, resample=Image.Resampling.BICUBIC,
                                        fillcolor=background)
                    result = corner_loss_score(white_foreground_mask(image))
                    if damaged:
                        self.assertGreater(result["corner_loss_score"], 0.35)
                    else:
                        self.assertLess(result["corner_loss_score"], 0.35)


if __name__ == "__main__":
    unittest.main()

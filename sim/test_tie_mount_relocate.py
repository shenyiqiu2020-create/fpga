"""Synthetic checks for the original-photo localization fallback."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from src.tie_mount_crop import locate_mount
from src.tie_mount_relocate import relocate_photo


BACKGROUND = (95, 125, 90)
TINTED_PART = (190, 215, 230)


class RelocatePhotoTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = Path(__file__).resolve().parents[1] / "build" / "work"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_relocalizes_full_part_when_primary_accepts_small_bright_patch(self) -> None:
        image = Image.new("RGB", (400, 600), BACKGROUND)
        draw = ImageDraw.Draw(image)
        draw.rectangle((80, 120, 300, 340), fill=TINTED_PART)
        draw.rectangle((130, 170, 210, 250), fill=(225, 225, 225))
        old_box = locate_mount(image)
        self.assertLess(old_box[2], 300)  # the first mask saw only the patch
        source = self.root / "source.png"
        image.save(source)
        crop, record = relocate_photo(source)
        x0, y0, x1, y1 = record["crop_box_original_xyxy"]
        self.assertLessEqual(x0, 80)
        self.assertLessEqual(y0, 120)
        self.assertGreaterEqual(x1, 300)
        self.assertGreaterEqual(y1, 340)
        self.assertEqual(crop.size, (256, 256))
        self.assertEqual(record["virtual_border_pixels"], 0)

    def test_virtual_border_keeps_near_edge_part_inside_crop(self) -> None:
        image = Image.new("RGB", (300, 500), BACKGROUND)
        ImageDraw.Draw(image).rectangle((5, 120, 245, 360), fill=TINTED_PART)
        source = self.root / "near_edge.png"
        image.save(source)
        crop, record = relocate_photo(source, padded=True)
        x0, y0, x1, y1 = record["crop_box_original_xyxy"]
        self.assertGreater(record["virtual_border_pixels"], 0)
        self.assertLessEqual(x0, 5)
        self.assertLessEqual(y0, 120)
        self.assertGreaterEqual(x1, 245)
        self.assertGreaterEqual(y1, 360)
        self.assertEqual(crop.size, (256, 256))

    def test_original_hash_is_verified(self) -> None:
        source = self.root / "image.png"
        Image.new("RGB", (300, 500), BACKGROUND).save(source)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            relocate_photo(source, expected_sha256="0" * 64)


if __name__ == "__main__":
    unittest.main()

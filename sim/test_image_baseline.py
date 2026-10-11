"""End-to-end checks for the synthetic image baseline and saved outputs."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from sim.make_demo_images import generate
from src.image_baseline import detect, run


class ImageBaselineTests(unittest.TestCase):
    def test_synthetic_images_and_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generate(root / "input")
            expected = {
                "normal": ("normal", []),
                "missing_corner": ("defect", [(24, 24, 40, 40)]),
                "missing_hole": ("defect", [(71, 71, 83, 83)]),
            }
            for name, (verdict, boxes) in expected.items():
                with self.subTest(name=name):
                    out = root / name
                    result = run(root / "input/normal.png", root / "input" / f"{name}.png", out)
                    self.assertEqual(result["verdict"], verdict)
                    self.assertEqual([(r["left"], r["top"], r["right"], r["bottom"])
                                      for r in result["regions"]], boxes)
                    self.assertEqual(json.loads((out / "result.json").read_text(encoding="utf-8")), result)
                    self.assertEqual(np.load(out / "score.npy").shape, (128, 128))
                    for filename in ("score.png", "mask.png", "overlay.png"):
                        with Image.open(out / filename) as image:
                            self.assertEqual(image.size, (128, 128))

    def test_reject_misalignment_and_invalid_parameters(self) -> None:
        image = np.zeros((8, 8), dtype=np.float32)
        with self.assertRaisesRegex(ValueError, "same-size"):
            detect(image, image[:, :7])
        with self.assertRaisesRegex(ValueError, "threshold"):
            detect(image, image, threshold=0)
        with self.assertRaisesRegex(ValueError, "min_area"):
            detect(image, image, min_area=0)

    def test_small_noise_is_ignored(self) -> None:
        reference = np.zeros((8, 8), dtype=np.float32)
        target = reference.copy()
        target[2, 2] = 1
        _, mask, regions = detect(reference, target, threshold=0.25, min_area=2)
        self.assertFalse(mask.any())
        self.assertEqual(regions, [])


if __name__ == "__main__":
    unittest.main()

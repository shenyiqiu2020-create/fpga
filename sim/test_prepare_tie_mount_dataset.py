"""Check the data split guard before using photographs of physical parts."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from sim.prepare_tie_mount_dataset import prepare, read_manifest


class ManifestGroupingTest(unittest.TestCase):
    def test_one_part_cannot_cross_train_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]
            for name in names:
                (root / name).write_bytes(b"placeholder")
            manifest = root / "photos.csv"
            with manifest.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(("file", "object_group", "split", "label"))
                writer.writerows((
                    ("a.jpg", "part1", "train", "good"),
                    ("b.jpg", "part1", "validation", "good"),
                    ("c.jpg", "part2", "test", "good"),
                    ("d.jpg", "part3", "test", "missing_corner"),
                ))
            with self.assertRaisesRegex(ValueError, "crosses data splits"):
                read_manifest(manifest)

    def test_quarter_turns_apply_only_to_training_group(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "photos.csv"
            with manifest.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(("file", "object_group", "split", "label"))
                for group, split, label in (("n1", "train", "good"),
                                            ("n2", "validation", "good"),
                                            ("n3", "test", "good"),
                                            ("d1", "test", "missing_corner")):
                    (root / f"{group}.jpg").write_bytes(b"placeholder")
                    writer.writerow((f"{group}.jpg", group, split, label))
            image = Image.new("RGB", (8, 8), "black")
            image.putpixel((0, 0), (255, 255, 255))
            metadata = {"source_size": [8, 8], "crop_box": [0, 0, 8, 8]}
            with patch("sim.prepare_tie_mount_dataset.crop_mount",
                       return_value=(image, metadata)):
                result = prepare(manifest, root / "prepared", train_quarter_turns=True)
            self.assertEqual(result["source_images"], 4)
            self.assertEqual(result["generated_images"], 7)
            self.assertEqual(result["physical_parts"], 4)
            outputs = json.loads((root / "prepared" / "prepared_manifest.json").read_text())
            self.assertEqual([row["augmentation_degrees"] for row in outputs],
                             [0, 90, 180, 270, 0, 0, 0])
            self.assertTrue(all(row["split"] == "train" for row in outputs
                                if row["augmentation_degrees"] != 0))
            train_dir = root / "prepared" / "tie_mount" / "train" / "good"
            self.assertEqual(len(list(train_dir.glob("*.png"))), 4)
            rotated = Image.open(train_dir / "0001_n1_r90.png")
            self.assertEqual(rotated.getpixel((0, 7)), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()

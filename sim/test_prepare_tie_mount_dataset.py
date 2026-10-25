"""Check the data split guard before using photographs of physical parts."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from sim.prepare_tie_mount_dataset import read_manifest


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


if __name__ == "__main__":
    unittest.main()

"""Check source freezing, leakage groups and the separate holdout output."""

from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from sim.freeze_tie_mount_expanded import freeze, group_plan, prepare_frozen


class FreezeExpandedTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = Path(__file__).resolve().parents[1] / "build" / "work"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "photos"
        self.source.mkdir()
        self.folders = ("do30", "do31", "do35", "正常14", "正常33", "正常34",
                        "正常35", "正常40", "正常42")
        for folder in self.folders:
            (self.source / folder).mkdir()
        colors = {
            "do30": (255, 0, 0), "do31": (240, 0, 0), "do35": (220, 0, 0),
            "正常14": (0, 20, 255), "正常33": (0, 40, 255),
            "正常34": (0, 60, 255), "正常35": (0, 80, 255),
            "正常40": (0, 100, 255), "正常42": (0, 120, 255),
        }
        for folder, color in colors.items():
            filename = "reject.jpg" if folder == "do31" else "a.jpg"
            Image.new("RGB", (32, 32), color).save(self.source / folder / filename)
        shutil.copyfile(self.source / "正常14" / "a.jpg", self.source / "正常14" / "b.jpg")
        shutil.copyfile(self.source / "正常33" / "a.jpg", self.source / "正常34" / "copied.jpg")
        Image.new("RGB", (32, 32), (0, 50, 255)).save(self.source / "正常33" / "b.jpg")

    def _freeze(self, output_name: str = "snapshot") -> dict:
        return freeze(self.source, self.root / output_name,
                      self.root / "tracked_inventory.csv", self.folders, 12)

    def test_roles_and_independent_object_ids(self) -> None:
        self.assertEqual(group_plan("正常34"), ("N34", "good", "train"))
        self.assertEqual(group_plan("正常42"), ("N42", "good", "holdout"))
        self.assertEqual(group_plan("do30"), ("D33", "defect", "development"))
        self.assertEqual(group_plan("do31"), ("D34", "defect", "development"))
        self.assertEqual(group_plan("do35"), ("D38", "defect", "holdout"))
        self.assertEqual(group_plan("正常35"), ("N35", "good", "validation"))

    def test_freeze_skips_copies_and_protects_holdout(self) -> None:
        summary = self._freeze()
        self.assertEqual(summary["photos"], 12)
        self.assertEqual(summary["unique_photos"], 10)
        with (self.root / "snapshot" / "inventory.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        by_file = {(row["folder"], row["filename"]): row for row in rows}
        self.assertEqual(by_file[("正常14", "b.jpg")]["duplicate_of"], "正常14/a.jpg")
        self.assertEqual(by_file[("正常34", "copied.jpg")]["duplicate_of"], "正常33/a.jpg")
        self.assertEqual(by_file[("正常33", "a.jpg")]["leakage_cluster"],
                         by_file[("正常34", "a.jpg")]["leakage_cluster"])
        self.assertNotEqual(by_file[("正常33", "a.jpg")]["object_group"],
                            by_file[("正常34", "a.jpg")]["object_group"])
        with (self.root / "snapshot" / "development.csv").open(encoding="utf-8", newline="") as stream:
            dev = list(csv.DictReader(stream))
        with (self.root / "snapshot" / "holdout.csv").open(encoding="utf-8", newline="") as stream:
            holdout = list(csv.DictReader(stream))
        self.assertEqual({row["object_group"] for row in holdout}, {"N42", "D38"})
        self.assertEqual({row["split"] for row in holdout}, {"holdout"})
        self.assertEqual({row["split"] for row in dev}, {"train", "validation", "test"})
        self.assertFalse({row["file"] for row in dev} & {row["file"] for row in holdout})
        self._freeze("second_snapshot")
        Image.new("RGB", (32, 32), (3, 4, 5)).save(self.source / "正常40" / "a.jpg")
        with self.assertRaisesRegex(ValueError, "tracked inventory differs"):
            self._freeze("changed_snapshot")

    def test_preparation_records_rejects_without_holdout_leakage(self) -> None:
        self._freeze()

        def fake_crop(path: Path, size: int) -> tuple[Image.Image, dict]:
            if path.name == "reject.jpg":
                raise ValueError("synthetic reject")
            return Image.new("RGB", (size, size), (1, 2, 3)), {
                "source_size": [32, 32], "crop_box": [0, 0, 32, 32]}

        dev_root = self.root / "development_prepared"
        hold_root = self.root / "holdout_prepared"
        result = prepare_frozen(self.root / "snapshot", dev_root, hold_root, fake_crop)
        self.assertEqual(len(result["rejected"]), 1)
        self.assertEqual(result["skipped_duplicate_photos"], 2)
        self.assertTrue(list((dev_root / "tie_mount" / "test" / "good").glob("*.png")))
        self.assertTrue(list((dev_root / "tie_mount" / "test" / "defect").glob("*.png")))
        self.assertEqual(len(list((hold_root / "crops").glob("*.png"))), 2)
        with (dev_root / "source_map.csv").open(encoding="utf-8", newline="") as stream:
            dev = list(csv.DictReader(stream))
        with (hold_root / "source_map.csv").open(encoding="utf-8", newline="") as stream:
            holdout = list(csv.DictReader(stream))
        self.assertTrue(all(row["role"] != "holdout" for row in dev))
        self.assertTrue(all(row["role"] == "holdout" for row in holdout))
        self.assertEqual([row["crop_error"] for row in dev if row["crop_status"] == "rejected"],
                         ["synthetic reject"])


if __name__ == "__main__":
    unittest.main()

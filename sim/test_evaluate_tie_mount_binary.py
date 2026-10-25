"""Check that multiple views remain one physical test unit."""

import csv
import tempfile
import unittest
from pathlib import Path

from sim.evaluate_tie_mount_binary import evaluate


class BinaryAuditTest(unittest.TestCase):
    def test_counts_photos_and_parts_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scores.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(("image", "object_group", "label", "score", "threshold"))
                writer.writerows((
                    ("d1a", "D1", "defect", 0.2, 0.1),
                    ("d1b", "D1", "defect", 0.05, 0.1),
                    ("n1a", "N1", "good", 0.12, 0.1),
                    ("n1b", "N1", "good", 0.03, 0.1),
                ))
            result = evaluate(path)
        self.assertEqual(result["photos"],
                         {"count": 4, "tp": 1, "fn": 1, "tn": 1, "fp": 1})
        self.assertEqual(result["parts_any_view"],
                         {"count": 2, "tp": 1, "fn": 0, "tn": 0, "fp": 1})


if __name__ == "__main__":
    unittest.main()

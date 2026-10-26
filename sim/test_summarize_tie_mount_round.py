"""Check that grouped accuracy and crop coverage use different denominators."""

import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

from sim.summarize_tie_mount_round import summarize


class SummarizeRoundTest(unittest.TestCase):
    def test_rejection_and_repeated_views_do_not_inflate_part_accuracy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = []
            predictions = []
            for index, (group, label, score) in enumerate(
                (("N01", "good", 0.1), ("N01", "good", 0.8),
                 ("D01", "defect", 0.2), ("D01", "defect", 0.9)), 1
            ):
                image = f"{index:04d}_{group}.png"
                relative = f"tie_mount/test/{label}/{image}"
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(image.encode())
                sources.append({"folder": group, "filename": image, "object_group": group,
                                "leakage_cluster": group, "label": label, "role": "development",
                                "sha256": "unused", "duplicate_of": "", "crop_status": "accepted",
                                "crop_error": "", "output": relative})
                predictions.append({"image": image,
                                    "crop_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                    "score_max": score, "threshold": 0.5,
                                    "predicted_defect": score > 0.5})
            sources.append({**sources[0], "filename": "bad.jpg", "output": "",
                            "crop_status": "rejected", "crop_error": "crop failed"})
            source_map = root / "source_map.csv"
            with source_map.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=sources[0])
                writer.writeheader()
                writer.writerows(sources)
            prediction_file = root / "predictions.csv"
            with prediction_file.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=predictions[0])
                writer.writeheader()
                writer.writerows(predictions)
            _, report = summarize(source_map, prediction_file, "development")
            self.assertEqual(report["source_photos"], 5)
            self.assertEqual(report["crop_status"], {"accepted": 4, "rejected": 1})
            self.assertEqual(report["photos"]["accuracy"], 0.5)
            self.assertEqual(report["parts_any_view"]["count"], 2)
            self.assertEqual(report["parts_any_view"]["accuracy"], 0.5)
            self.assertEqual(report["parts_any_view"]["balanced_accuracy"], 0.5)


if __name__ == "__main__":
    unittest.main()

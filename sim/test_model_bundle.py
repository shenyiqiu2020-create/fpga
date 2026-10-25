"""Check that frozen EfficientAD files are used as one inseparable bundle."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sim.model_bundle import ALL_NAMES, create_model_bundle, verify_model_bundle


class ModelBundleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parents[1]
        )
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.trainings = self.root / "trainings"
        self.trainings.mkdir()
        for name in ALL_NAMES[:3]:
            (self.trainings / name).write_bytes(name.encode("ascii"))
        self.normalization = self.root / "normalization.npz"
        self.summary = self.root / "summary.json"
        self.normalization.write_bytes(b"calibration for run A")
        self.summary.write_text('{"threshold": 0.1}', encoding="utf-8")
        self.manifest_path = self.root / "bundle.json"
        self.manifest = create_model_bundle(
            "run-A", self.trainings, self.normalization, self.summary
        )
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_matching_bundle_passes(self) -> None:
        verified = verify_model_bundle(self.manifest_path, self.trainings,
                                       self.normalization, self.summary)
        self.assertEqual(verified["bundle_id"], "run-A")
        self.assertEqual(set(verified["sha256"]), set(ALL_NAMES))

    def test_mixed_training_and_calibration_files_are_rejected(self) -> None:
        self.normalization.write_bytes(b"calibration for run B")
        with self.assertRaisesRegex(ValueError, "mismatch for normalization.npz"):
            verify_model_bundle(self.manifest_path, self.trainings,
                                self.normalization, self.summary)

        self.normalization.write_bytes(b"calibration for run A")
        (self.trainings / "student_final.pth").write_bytes(b"student from run B")
        with self.assertRaisesRegex(ValueError, "mismatch for student_final.pth"):
            verify_model_bundle(self.manifest_path, self.trainings,
                                self.normalization, self.summary)

    def test_alternate_bundle_requires_its_own_manifest(self) -> None:
        self.normalization.write_bytes(b"calibration for run B")
        other = self.root / "bundle-B.json"
        other.write_text(json.dumps(create_model_bundle(
            "run-B", self.trainings, self.normalization, self.summary
        )), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            verify_model_bundle(self.manifest_path, self.trainings,
                                self.normalization, self.summary)
        self.assertEqual(verify_model_bundle(other, self.trainings,
                                            self.normalization, self.summary)["bundle_id"],
                         "run-B")

    def test_invalid_manifest_is_rejected(self) -> None:
        self.manifest["sha256"].pop("summary.json")
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid EfficientAD model bundle"):
            verify_model_bundle(self.manifest_path, self.trainings,
                                self.normalization, self.summary)


if __name__ == "__main__":
    unittest.main()

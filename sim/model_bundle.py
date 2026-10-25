"""Bind one frozen EfficientAD model to its calibration and threshold files.

The manifest checks byte identity. Its creator must still establish that the
five files came from the same training run; hashes alone cannot prove that.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


DEFAULT_BUNDLE_MANIFEST = (
    Path(__file__).resolve().parent / "model_bundles" / "tie_mount_grouped_v1_300step.json"
)
MODEL_NAMES = ("teacher_final.pth", "student_final.pth", "autoencoder_final.pth")
CALIBRATION_NAMES = ("normalization.npz", "summary.json")
ALL_NAMES = MODEL_NAMES + CALIBRATION_NAMES
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def bundle_files(trainings_dir: Path, normalization: Path, summary: Path) -> dict[str, Path]:
    return {**{name: trainings_dir / name for name in MODEL_NAMES},
            "normalization.npz": normalization, "summary.json": summary}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_model_bundle(bundle_id: str, trainings_dir: Path, normalization: Path,
                        summary: Path) -> dict:
    if not bundle_id or not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle_id):
        raise ValueError("bundle_id must contain only letters, digits, _, . or -")
    paths = bundle_files(trainings_dir, normalization, summary)
    return {"schema_version": 1, "bundle_id": bundle_id,
            "sha256": {name: sha256_file(paths[name]) for name in ALL_NAMES}}


def verify_model_bundle(manifest_path: Path, trainings_dir: Path,
                        normalization: Path, summary: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (not isinstance(manifest, dict)
            or manifest.get("schema_version") != 1
            or not isinstance(manifest.get("bundle_id"), str)
            or not manifest["bundle_id"]
            or not isinstance(manifest.get("sha256"), dict)
            or set(manifest["sha256"]) != set(ALL_NAMES)
            or any(not isinstance(value, str) or not _SHA256.fullmatch(value)
                   for value in manifest["sha256"].values())):
        raise ValueError(f"invalid EfficientAD model bundle manifest: {manifest_path}")
    paths = bundle_files(trainings_dir, normalization, summary)
    for name in ALL_NAMES:
        actual = sha256_file(paths[name])
        expected = manifest["sha256"][name]
        if actual != expected:
            raise ValueError(
                f"EfficientAD model bundle mismatch for {name}: "
                f"expected {expected}, found {actual}; manifest={manifest_path}"
            )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--trainings-dir", required=True, type=Path)
    parser.add_argument("--normalization", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    manifest = create_model_bundle(args.bundle_id, args.trainings_dir,
                                   args.normalization, args.summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()

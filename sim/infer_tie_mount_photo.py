"""Classify one original tie-mount photo with the frozen EfficientAD baseline.

The locator supplies the same 256x256 crop used by the grouped dataset.
The model, calibration, and threshold are loaded without retraining or tuning.
Run this with the isolated EfficientAD Python environment from the repo root.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from src.tie_mount_crop import crop_mount
from sim.infer_tie_mount_holdout import run as infer_crops
from sim.model_bundle import DEFAULT_BUNDLE_MANIFEST, verify_model_bundle


def run(args: argparse.Namespace) -> dict:
    if not args.photo.is_file():
        raise FileNotFoundError(args.photo)
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)

    # Check before creating the crop directory. An explicit alternate model
    # needs an explicit matching bundle manifest.
    verify_model_bundle(args.bundle_manifest, args.trainings_dir,
                        args.normalization, args.summary)

    # Locate before creating output so a rejected photo leaves no result folder.
    crop, crop_record = crop_mount(args.photo, size=256)
    crops_dir = args.output_dir / "crops"
    crops_dir.mkdir(parents=True)
    crop_path = crops_dir / "input.png"
    crop.save(crop_path)

    infer_dir = args.output_dir / "inference"
    manifest = infer_crops(argparse.Namespace(
        external_repo=args.external_repo,
        images_dir=crops_dir,
        trainings_dir=args.trainings_dir,
        normalization=args.normalization,
        summary=args.summary,
        bundle_manifest=args.bundle_manifest,
        output_dir=infer_dir,
    ))
    with (infer_dir / "predictions.csv").open(newline="", encoding="utf-8") as stream:
        predictions = list(csv.DictReader(stream))
    if len(predictions) != 1:
        raise RuntimeError("expected exactly one prediction")
    row = predictions[0]
    if row["predicted_defect"] not in ("True", "False"):
        raise ValueError("unexpected prediction value")
    predicted_defect = row["predicted_defect"] == "True"
    result = {
        "source": str(args.photo.resolve()),
        "source_sha256": hashlib.sha256(args.photo.read_bytes()).hexdigest(),
        "crop": crop_record,
        "crop_file": str(crop_path.resolve()),
        "predicted_defect": predicted_defect,
        "verdict": "defect" if predicted_defect else "normal",
        "score": float(row["score_max"]),
        "threshold": float(row["threshold"]),
        "model_hashes": manifest["model_hashes"],
        "normalization_sha256": manifest["normalization_sha256"],
        "threshold_summary_sha256": manifest["summary_sha256"],
        "model_bundle_id": manifest["model_bundle_id"],
        "model_bundle_manifest_sha256": manifest["model_bundle_manifest_sha256"],
        "device": manifest["device"],
    }
    (args.output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photo", type=Path, help="original phone JPEG or PNG")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--external-repo", type=Path,
                        default=Path("build/work/external/efficientad"))
    parser.add_argument("--trainings-dir", type=Path,
                        default=Path("build/work/results/tie_mount_grouped_v1_300step/trainings/mvtec_loco/tie_mount"))
    parser.add_argument("--normalization", type=Path,
                        default=Path("build/work/results/tie_mount_grouped_v1_300step/components/normalization.npz"))
    parser.add_argument("--summary", type=Path,
                        default=Path("build/work/results/tie_mount_grouped_v1_300step/components/summary.json"))
    parser.add_argument("--bundle-manifest", type=Path,
                        default=DEFAULT_BUNDLE_MANIFEST)
    args = parser.parse_args()
    print(json.dumps(run(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

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

from PIL import Image, ImageDraw, ImageOps

from src.tie_mount_crop import crop_mount
from sim.infer_tie_mount_holdout import run as infer_crops
from sim.localize_tie_mount_edge import localize
from sim.model_bundle import DEFAULT_BUNDLE_MANIFEST, verify_model_bundle


MODEL_PROFILES = {
    "golden_v3": (
        Path("build/work/results/tie_mount_grouped_v1_300step/trainings/mvtec_loco/tie_mount"),
        Path("build/work/results/tie_mount_grouped_v1_300step/components/normalization.npz"),
        Path("build/work/results/tie_mount_grouped_v1_300step/components/summary.json"),
        DEFAULT_BUNDLE_MANIFEST,
    ),
    "batch_20261026": (
        Path("build/work/results/tie_mount_20261026_3000step/trainings/mvtec_loco/tie_mount"),
        Path("build/work/results/tie_mount_20261026_3000step/components_dedup_validation/normalization.npz"),
        Path("build/work/results/tie_mount_20261026_3000step/components_dedup_validation/summary.json"),
        Path("sim/model_bundles/tie_mount_20261026_3000step_dedupval.json"),
    ),
}


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
    if getattr(args, "mark_edge_candidate", False) and predicted_defect:
        try:
            location = localize(crop_path, infer_dir / "maps" / "combined" / "input.tiff",
                                args.output_dir / "edge_location")
            point = location["expected_edge_peak_xy_score"]
            box = crop_record["crop_box"]
            side = box[2] - box[0]
            source_x = box[0] + point["x"] * side / 256
            source_y = box[1] + point["y"] * side / 256
            with Image.open(args.photo) as source:
                annotated = ImageOps.exif_transpose(source).convert("RGB")
            draw = ImageDraw.Draw(annotated)
            radius = max(12, round(min(annotated.size) * 0.01))
            draw.ellipse((source_x - radius, source_y - radius,
                          source_x + radius, source_y + radius),
                         outline=(255, 0, 0), width=max(3, radius // 5))
            annotated.save(args.output_dir / "edge_location" / "source_preview.jpg", quality=92)
            result["defect_location_candidate"] = {
                "status": "candidate",
                "method": "EfficientAD fused-map peak in expected outer-edge band",
                "crop_xy": [point["x"], point["y"]],
                "source_xy_after_exif_orientation": [round(source_x, 1), round(source_y, 1)],
                "source_preview": "edge_location/source_preview.jpg",
                "crop_preview": "edge_location/preview.png",
                "validated_location": False,
            }
        except ValueError as error:
            result["defect_location_candidate"] = {
                "status": "unavailable", "reason": str(error), "validated_location": False,
            }
    (args.output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photo", type=Path, help="original phone JPEG or PNG")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--model-profile", choices=tuple(MODEL_PROFILES), default="golden_v3",
                        help="explicit frozen model bundle; existing golden_v3 remains the default")
    parser.add_argument("--mark-edge-candidate", action="store_true",
                        help="mark a tentative outer-edge location when the model reports a defect")
    parser.add_argument("--external-repo", type=Path,
                        default=Path("build/work/external/efficientad"))
    parser.add_argument("--trainings-dir", type=Path)
    parser.add_argument("--normalization", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--bundle-manifest", type=Path)
    args = parser.parse_args()
    defaults = MODEL_PROFILES[args.model_profile]
    for name, value in zip(("trainings_dir", "normalization", "summary", "bundle_manifest"), defaults):
        if getattr(args, name) is None:
            setattr(args, name, value)
    print(json.dumps(run(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

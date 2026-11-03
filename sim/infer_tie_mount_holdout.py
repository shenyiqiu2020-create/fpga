"""Run frozen EfficientAD weights and calibration on new 256x256 crops.

This intentionally does not recompute normalization or tune a threshold with
the supplied images. Run with the isolated Python environment of EfficientAD.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import tifffile
import torch
from PIL import Image

from sim.export_efficientad_components import full_size_map
from sim.model_bundle import DEFAULT_BUNDLE_MANIFEST, MODEL_NAMES, sha256_file, verify_model_bundle


def run(args: argparse.Namespace) -> dict:
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    if not args.images_dir.is_dir():
        raise FileNotFoundError(args.images_dir)
    image_paths = sorted(args.images_dir.glob("*.png"))
    if not image_paths:
        raise ValueError("no PNG crops found")

    # Fail before loading any weights or writing any result if calibration,
    # threshold, and model files are not the frozen set named by this manifest.
    bundle = verify_model_bundle(args.bundle_manifest, args.trainings_dir,
                                 args.normalization, args.summary)

    sys.path.insert(0, str(args.external_repo.resolve()))
    import efficientad as candidate  # noqa: E402

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    models = (
        candidate.get_pdn_small(candidate.out_channels),
        candidate.get_pdn_small(2 * candidate.out_channels),
        candidate.get_autoencoder(candidate.out_channels),
    )
    model_hashes = {}
    for model, name in zip(models, MODEL_NAMES):
        path = args.trainings_dir / name
        saved = torch.load(path, map_location="cpu")
        model.load_state_dict(saved.state_dict())
        model.eval().to(device)
        model_hashes[name] = bundle["sha256"][name]

    with np.load(args.normalization) as calibration:
        required = ("teacher_mean", "teacher_std", "q_st_start", "q_st_end",
                    "q_ae_start", "q_ae_end")
        if set(calibration.files) != set(required):
            raise ValueError("unexpected EfficientAD calibration fields")
        tensors = tuple(torch.from_numpy(calibration[key]).to(device) for key in required)
    threshold_summary = json.loads(args.summary.read_text(encoding="utf-8"))
    threshold = float(threshold_summary["threshold"])
    if not np.isfinite(threshold):
        raise ValueError("threshold must be finite")

    args.output_dir.mkdir(parents=True)
    rows = []
    for path in image_paths:
        with Image.open(path) as image:
            if image.size != (256, 256):
                raise ValueError(f"expected 256x256 crop: {path}")
            image_tensor = candidate.default_transform(image.convert("RGB"))[None].to(device)
        with torch.no_grad():
            predicted = candidate.predict(image_tensor, *models, *tensors)
            maps = tuple(full_size_map(component, 256, 256) for component in predicted)
        if any(not np.isfinite(component).all() for component in maps):
            raise ValueError(f"nonfinite anomaly map for {path}")
        for component_name, array in zip(("combined", "student_teacher", "autoencoder"), maps):
            destination = args.output_dir / "maps" / component_name
            destination.mkdir(parents=True, exist_ok=True)
            tifffile.imwrite(destination / f"{path.stem}.tiff", array)
        peak_y, peak_x = np.unravel_index(int(np.argmax(maps[0])), maps[0].shape)
        score = float(maps[0][peak_y, peak_x])
        rows.append({"image": path.name,
                     "crop_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "score_max": score,
                     "threshold": threshold,
                     "predicted_defect": score > threshold,
                     "peak_x": int(peak_x), "peak_y": int(peak_y)})
    with (args.output_dir / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    manifest = {"device": str(device), "images_dir": str(args.images_dir),
                "model_bundle_id": bundle["bundle_id"],
                "model_bundle_manifest_sha256": sha256_file(args.bundle_manifest),
                "model_hashes": model_hashes,
                "normalization_sha256": hashlib.sha256(args.normalization.read_bytes()).hexdigest(),
                "summary_sha256": hashlib.sha256(args.summary.read_bytes()).hexdigest(),
                "threshold": threshold, "image_count": len(rows)}
    (args.output_dir / "inference_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-repo", required=True, type=Path)
    parser.add_argument("--images-dir", required=True, type=Path)
    parser.add_argument("--trainings-dir", required=True, type=Path)
    parser.add_argument("--normalization", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--bundle-manifest", type=Path,
                        default=DEFAULT_BUNDLE_MANIFEST)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

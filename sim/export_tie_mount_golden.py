"""Export one frozen EfficientAD inference as a PS/PL comparison fixture.

The input is an existing 256x256 crop.  This is a numerical interface export,
not a new training run, calibration pass, or estimate of detection accuracy.
Run with the isolated EfficientAD Python environment from the repository root.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from sim.export_efficientad_components import full_size_map
from sim.model_bundle import DEFAULT_BUNDLE_MANIFEST, MODEL_NAMES, sha256_file, verify_model_bundle


def _save_array(output_dir: Path, name: str, array: np.ndarray) -> dict:
    array = np.ascontiguousarray(array)
    if not np.isfinite(array).all():
        raise ValueError(f"nonfinite tensor: {name}")
    path = output_dir / f"{name}.npy"
    np.save(path, array, allow_pickle=False)
    return {"file": path.name, "shape": list(array.shape), "dtype": str(array.dtype),
            "sha256": sha256_file(path)}


def run(args: argparse.Namespace) -> dict:
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    if not args.crop.is_file():
        raise FileNotFoundError(args.crop)
    bundle = verify_model_bundle(args.bundle_manifest, args.trainings_dir,
                                 args.normalization, args.summary)

    sys.path.insert(0, str(args.external_repo.resolve()))
    import efficientad as candidate  # noqa: E402 - pinned external implementation

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    models = (candidate.get_pdn_small(candidate.out_channels),
              candidate.get_pdn_small(2 * candidate.out_channels),
              candidate.get_autoencoder(candidate.out_channels))
    for model, name in zip(models, MODEL_NAMES):
        saved = torch.load(args.trainings_dir / name, map_location="cpu")
        model.load_state_dict(saved.state_dict())
        model.eval().to(device)

    keys = ("teacher_mean", "teacher_std", "q_st_start", "q_st_end",
            "q_ae_start", "q_ae_end")
    with np.load(args.normalization, allow_pickle=False) as calibration:
        if set(calibration.files) != set(keys):
            raise ValueError("unexpected EfficientAD calibration fields")
        mean, std, q_st_start, q_st_end, q_ae_start, q_ae_end = (
            torch.from_numpy(calibration[key]).to(device) for key in keys)
    if torch.any(std <= 0) or torch.any(q_st_end <= q_st_start) or torch.any(q_ae_end <= q_ae_start):
        raise ValueError("invalid calibration denominators")
    threshold = float(json.loads(args.summary.read_text(encoding="utf-8"))["threshold"])
    if not np.isfinite(threshold):
        raise ValueError("nonfinite threshold")

    with Image.open(args.crop) as opened:
        image = opened.convert("RGB")
    if image.size != (256, 256):
        raise ValueError("expected a 256x256 crop")
    input_rgb = np.asarray(image, dtype=np.uint8)
    input_tensor = candidate.default_transform(image)[None].to(device)
    with torch.no_grad():
        teacher = (models[0](input_tensor) - mean) / std
        student = models[1](input_tensor)
        autoencoder = models[2](input_tensor)
        channels = candidate.out_channels
        student_st, student_ae = student[:, :channels], student[:, channels:]
        map_st_raw = torch.mean((teacher - student_st) ** 2, dim=1, keepdim=True)
        map_ae_raw = torch.mean((autoencoder - student_ae) ** 2, dim=1, keepdim=True)
        map_st = 0.1 * (map_st_raw - q_st_start) / (q_st_end - q_st_start)
        map_ae = 0.1 * (map_ae_raw - q_ae_start) / (q_ae_end - q_ae_start)
        fused = 0.5 * map_st + 0.5 * map_ae
        reference = candidate.predict(input_tensor, *models, mean, std,
                                      q_st_start, q_st_end, q_ae_start, q_ae_end)
        for exported, original in zip((fused, map_st, map_ae), reference):
            torch.testing.assert_close(exported, original, rtol=0, atol=0)
        fused_256 = full_size_map(fused, 256, 256)

    arrays = {
        "input_rgb_hwc": input_rgb,
        "input_normalized_chw": input_tensor[0].cpu().numpy(),
        "teacher_normalized_chw": teacher[0].cpu().numpy(),
        "student_teacher_chw": student_st[0].cpu().numpy(),
        "autoencoder_chw": autoencoder[0].cpu().numpy(),
        "student_autoencoder_chw": student_ae[0].cpu().numpy(),
        "student_teacher_raw_hw": map_st_raw[0, 0].cpu().numpy(),
        "autoencoder_raw_hw": map_ae_raw[0, 0].cpu().numpy(),
        "student_teacher_calibrated_hw": map_st[0, 0].cpu().numpy(),
        "autoencoder_calibrated_hw": map_ae[0, 0].cpu().numpy(),
        "fused_hw": fused[0, 0].cpu().numpy(),
        "fused_full_hw": fused_256,
    }
    if any(not np.isfinite(value).all() for value in arrays.values()):
        raise ValueError("nonfinite output")
    score = float(np.max(fused_256))
    args.output_dir.mkdir(parents=True)
    metadata = {
        "schema_version": 1,
        "purpose": "float32 software golden fixture for PS/PL comparison; not an accuracy claim",
        "object_group": args.object_group,
        "reference_label": args.reference_label,
        "crop_source": str(args.crop.resolve()),
        "crop_sha256": sha256_file(args.crop),
        "model_bundle_id": bundle["bundle_id"],
        "model_bundle_manifest_sha256": sha256_file(args.bundle_manifest),
        "model_hashes": {name: bundle["sha256"][name] for name in MODEL_NAMES},
        "normalization_sha256": sha256_file(args.normalization),
        "threshold_summary_sha256": sha256_file(args.summary),
        "device": str(device),
        "layout": "input_rgb is HWC; all features are CHW; all maps are HW; arrays are little-endian float32 except uint8 RGB",
        "map_rule": "mean of 384 squared channel differences, then 0.1 quantile normalization per branch, then 0.5+0.5 fusion; pad 4 pixels each side and bilinear resize to 256x256",
        "quantiles": {"student_teacher_start": float(q_st_start.cpu().item()),
                      "student_teacher_end": float(q_st_end.cpu().item()),
                      "autoencoder_start": float(q_ae_start.cpu().item()),
                      "autoencoder_end": float(q_ae_end.cpu().item())},
        "score": score,
        "threshold": threshold,
        "predicted_defect": score > threshold,
        "arrays": {name: _save_array(args.output_dir, name, value)
                   for name, value in arrays.items()},
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("crop", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--object-group", required=True,
                        help="physical part identity, for example N02 or D07")
    parser.add_argument("--reference-label", required=True, choices=("normal", "defect"),
                        help="human reference label; not used to compute the model output")
    parser.add_argument("--external-repo", type=Path,
                        default=Path("build/work/external/efficientad"))
    parser.add_argument("--trainings-dir", type=Path,
                        default=Path("build/work/results/tie_mount_grouped_v1_300step/trainings/mvtec_loco/tie_mount"))
    parser.add_argument("--normalization", type=Path,
                        default=Path("build/work/results/tie_mount_grouped_v1_300step/components/normalization.npz"))
    parser.add_argument("--summary", type=Path,
                        default=Path("build/work/results/tie_mount_grouped_v1_300step/components/summary.json"))
    parser.add_argument("--bundle-manifest", type=Path, default=DEFAULT_BUNDLE_MANIFEST)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps({"output_dir": str(args.output_dir), "score": result["score"],
                      "threshold": result["threshold"],
                      "predicted_defect": result["predicted_defect"]}, indent=2))


if __name__ == "__main__":
    main()

"""Check a float32 EfficientAD golden fixture without loading PyTorch models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from sim.model_bundle import sha256_file


FEATURE_SHAPE = (384, 56, 56)
MAP_SHAPE = (56, 56)


def _full_size_map_numpy(fused: np.ndarray) -> np.ndarray:
    """Match zero padding and bilinear resize with align_corners=False."""
    padded = np.pad(fused, ((4, 4), (4, 4)), mode="constant")
    source = np.clip((np.arange(256, dtype=np.float32) + 0.5) / 4.0 - 0.5,
                     0.0, 63.0)
    low = np.floor(source).astype(np.int64)
    high = np.minimum(low + 1, 63)
    weight = source - low.astype(np.float32)
    top = (1.0 - weight[:, None]) * padded[low[:, None], low[None, :]] \
        + weight[:, None] * padded[high[:, None], low[None, :]]
    bottom = (1.0 - weight[:, None]) * padded[low[:, None], high[None, :]] \
        + weight[:, None] * padded[high[:, None], high[None, :]]
    return (1.0 - weight[None, :]) * top + weight[None, :] * bottom


def verify(directory: Path) -> dict:
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    arrays = {}
    for name, entry in metadata["arrays"].items():
        path = directory / entry["file"]
        if path.name != entry["file"] or sha256_file(path) != entry["sha256"]:
            raise ValueError(f"file identity mismatch: {name}")
        value = np.load(path, allow_pickle=False)
        if list(value.shape) != entry["shape"] or str(value.dtype) != entry["dtype"]:
            raise ValueError(f"array layout mismatch: {name}")
        if not np.isfinite(value).all():
            raise ValueError(f"nonfinite array: {name}")
        arrays[name] = value

    features = ("teacher_normalized_chw", "student_teacher_chw",
                "autoencoder_chw", "student_autoencoder_chw")
    maps = ("student_teacher_raw_hw", "autoencoder_raw_hw",
            "student_teacher_calibrated_hw", "autoencoder_calibrated_hw", "fused_hw")
    if arrays["input_rgb_hwc"].shape != (256, 256, 3) or arrays["input_rgb_hwc"].dtype != np.uint8:
        raise ValueError("RGB input layout mismatch")
    if arrays["input_normalized_chw"].shape != (3, 256, 256):
        raise ValueError("normalized input layout mismatch")
    if any(arrays[name].shape != FEATURE_SHAPE or arrays[name].dtype != np.float32
           for name in features):
        raise ValueError("feature layout mismatch")
    if any(arrays[name].shape != MAP_SHAPE or arrays[name].dtype != np.float32
           for name in maps):
        raise ValueError("local map layout mismatch")
    if arrays["fused_full_hw"].shape != (256, 256):
        raise ValueError("full map layout mismatch")

    rgb = arrays["input_rgb_hwc"].astype(np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    normalized = ((rgb - mean) / std).transpose(2, 0, 1)
    np.testing.assert_allclose(normalized, arrays["input_normalized_chw"], rtol=0, atol=5e-7)

    for left, right, raw_name in (
        ("teacher_normalized_chw", "student_teacher_chw", "student_teacher_raw_hw"),
        ("autoencoder_chw", "student_autoencoder_chw", "autoencoder_raw_hw"),
    ):
        difference = arrays[left] - arrays[right]
        calculated = np.mean(difference * difference, axis=0, dtype=np.float32)
        np.testing.assert_allclose(calculated, arrays[raw_name], rtol=2e-6, atol=2e-6)

    quantiles = metadata["quantiles"]
    for prefix, raw_name, calibrated_name in (
        ("student_teacher", "student_teacher_raw_hw", "student_teacher_calibrated_hw"),
        ("autoencoder", "autoencoder_raw_hw", "autoencoder_calibrated_hw"),
    ):
        start = float(quantiles[f"{prefix}_start"])
        end = float(quantiles[f"{prefix}_end"])
        if not np.isfinite([start, end]).all() or end <= start:
            raise ValueError(f"invalid {prefix} quantiles")
        calculated = 0.1 * (arrays[raw_name] - start) / (end - start)
        np.testing.assert_allclose(calculated, arrays[calibrated_name], rtol=2e-6, atol=2e-6)
    fused = (0.5 * arrays["student_teacher_calibrated_hw"]
             + 0.5 * arrays["autoencoder_calibrated_hw"])
    np.testing.assert_allclose(fused, arrays["fused_hw"], rtol=0, atol=1e-7)
    np.testing.assert_allclose(_full_size_map_numpy(fused), arrays["fused_full_hw"],
                               rtol=0, atol=1e-6)
    score = float(np.max(arrays["fused_full_hw"]))
    if score != metadata["score"] or (score > float(metadata["threshold"])) != metadata["predicted_defect"]:
        raise ValueError("score or verdict mismatch")
    return {"model_bundle_id": metadata["model_bundle_id"], "score": score,
            "threshold": metadata["threshold"], "predicted_defect": metadata["predicted_defect"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.fixture_dir), indent=2))


if __name__ == "__main__":
    main()

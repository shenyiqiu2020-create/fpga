"""Build and score an experimental 320-channel full EfficientAD projection.

The three frozen 384-channel networks remain the source. A seeded orthogonal
matrix projects the *last convolution* of teacher, both student halves, and
autoencoder to 320 channels. Teacher normalization is folded into its final
convolution. The projected model still has all three EfficientAD branches;
its four map quantiles and image threshold must be recalibrated with normal
validation crops. No source weights, default inference profile, or Release
are modified.

Run from the repository root with the isolated EfficientAD Python environment::

    python -B -m sim.efficientad_projected_candidate build --validation-dir build/work/data/tie_mount_20261026_v2/development_prepared/tie_mount/validation/good --output-dir build/work/results/tie_mount_projection320_seed20261030

    python -B -m sim.efficientad_projected_candidate score-crops --bundle-dir build/work/results/tie_mount_projection320_seed20261030 --images-dir build/work/data/tie_mount_20261026_v2/holdout_crops_v2

The second command prints per-image scores; it is not an independent accuracy
evaluation because these older images helped choose the method. Keep any new
physical-part blind test entirely out of calibration and model selection.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.nn import functional as F

from sim.model_bundle import (MODEL_NAMES, create_model_bundle, sha256_file,
                              verify_model_bundle)


SOURCE_CHANNELS = 384
PROJECTED_CHANNELS = 320
PROJECTION_SEED = 20261030
SOURCE_ROOT = Path("build/work/results/tie_mount_20261026_3000step")
SOURCE_WEIGHTS = SOURCE_ROOT / "trainings/mvtec_loco/tie_mount"
SOURCE_NORMALIZATION = SOURCE_ROOT / "components_dedup_validation/normalization.npz"
SOURCE_SUMMARY = SOURCE_ROOT / "components_dedup_validation/summary.json"
SOURCE_MANIFEST = Path("sim/model_bundles/tie_mount_20261026_3000step_dedupval.json")
EXTERNAL_REPO = Path("build/work/external/efficientad")


def projector(width: int = PROJECTED_CHANNELS) -> torch.Tensor:
    """Return a reproducible matrix with orthonormal rows, shape [width,384]."""
    if not 0 < width <= SOURCE_CHANNELS:
        raise ValueError("projected width must be between 1 and 384")
    rng = np.random.default_rng(PROJECTION_SEED)
    random_matrix = rng.normal(size=(SOURCE_CHANNELS, width))
    q, r = np.linalg.qr(random_matrix, mode="reduced")
    # QR signs may differ across LAPACK implementations; fix that ambiguity.
    q *= np.where(np.diag(r) < 0, -1.0, 1.0)
    return torch.from_numpy(np.asarray(q.T, dtype=np.float32).copy())


def _replace_final_conv(original: nn.Conv2d, weight: torch.Tensor,
                        bias: torch.Tensor) -> nn.Conv2d:
    if original.groups != 1 or original.bias is None:
        raise ValueError("expected an ungrouped final convolution with bias")
    replacement = nn.Conv2d(
        original.in_channels, weight.shape[0], original.kernel_size,
        stride=original.stride, padding=original.padding,
        dilation=original.dilation, bias=True,
    ).to(device=original.weight.device, dtype=original.weight.dtype)
    with torch.no_grad():
        replacement.weight.copy_(weight)
        replacement.bias.copy_(bias)
    return replacement


def project_models(full_models: tuple[nn.Module, nn.Module, nn.Module],
                   projection: torch.Tensor, teacher_mean: np.ndarray,
                   teacher_std: np.ndarray) -> tuple[nn.Module, nn.Module, nn.Module]:
    """Fold normalization and projection into the three final convolutions."""
    if projection.shape != (PROJECTED_CHANNELS, SOURCE_CHANNELS):
        raise ValueError("expected a 320x384 projection matrix")
    if not torch.isfinite(projection).all():
        raise ValueError("projection matrix must be finite")
    mean = torch.as_tensor(np.asarray(teacher_mean).copy(), dtype=torch.float32).flatten()
    std = torch.as_tensor(np.asarray(teacher_std).copy(), dtype=torch.float32).flatten()
    if (mean.shape != (SOURCE_CHANNELS,) or std.shape != (SOURCE_CHANNELS,)
            or not torch.isfinite(mean).all() or not torch.isfinite(std).all()
            or not torch.all(std > 0)):
        raise ValueError("invalid source teacher normalization")
    teacher, student, autoencoder = copy.deepcopy(full_models)
    t_final, s_final, a_final = teacher[-1], student[-1], autoencoder[-1]
    if (not all(isinstance(layer, nn.Conv2d)
                for layer in (t_final, s_final, a_final))
            or t_final.out_channels != SOURCE_CHANNELS
            or s_final.out_channels != 2 * SOURCE_CHANNELS
            or a_final.out_channels != SOURCE_CHANNELS):
        raise ValueError("source networks do not have the expected final channels")
    p = projection.to(dtype=t_final.weight.dtype, device=t_final.weight.device)
    mean = mean.to(p.device)
    std = std.to(p.device)

    teacher_weight = torch.einsum("kc,cihw->kihw", p,
                                  t_final.weight.detach() / std[:, None, None, None])
    teacher_bias = p @ ((t_final.bias.detach() - mean) / std)
    teacher[-1] = _replace_final_conv(t_final, teacher_weight, teacher_bias)

    student_weight = torch.cat([
        torch.einsum("kc,cihw->kihw", p, half)
        for half in s_final.weight.detach().split(SOURCE_CHANNELS, dim=0)
    ])
    student_bias = torch.cat([
        p @ half for half in s_final.bias.detach().split(SOURCE_CHANNELS)
    ])
    student[-1] = _replace_final_conv(s_final, student_weight, student_bias)

    ae_weight = torch.einsum("kc,cihw->kihw", p, a_final.weight.detach())
    ae_bias = p @ a_final.bias.detach()
    autoencoder[-1] = _replace_final_conv(a_final, ae_weight, ae_bias)
    return teacher, student, autoencoder


@torch.inference_mode()
def raw_maps(image: torch.Tensor,
             models: tuple[nn.Module, nn.Module, nn.Module]) -> tuple[torch.Tensor, torch.Tensor]:
    """Return the uncalibrated student-teacher and AE maps for one image."""
    teacher, student, autoencoder = models
    teacher_output = teacher(image)
    student_output = student(image)
    ae_output = autoencoder(image)
    if (teacher_output.shape[1] != PROJECTED_CHANNELS
            or student_output.shape[1] != 2 * PROJECTED_CHANNELS
            or ae_output.shape != teacher_output.shape):
        raise ValueError("projected network feature shapes do not match")
    map_st = ((teacher_output - student_output[:, :PROJECTED_CHANNELS]) ** 2).mean(
        dim=1, keepdim=True)
    map_ae = ((ae_output - student_output[:, PROJECTED_CHANNELS:]) ** 2).mean(
        dim=1, keepdim=True)
    return map_st, map_ae


def calibration_from_maps(raw_pairs: list[tuple[torch.Tensor, torch.Tensor]]) -> tuple[float, float, float, float]:
    """Use only supplied normal validation maps to determine four quantiles."""
    if not raw_pairs:
        raise ValueError("normal validation maps are required")
    st_maps = torch.cat([st for st, _ in raw_pairs])
    ae_maps = torch.cat([ae for _, ae in raw_pairs])
    quantiles = tuple(float(value) for value in (
        torch.quantile(st_maps, 0.9), torch.quantile(st_maps, 0.995),
        torch.quantile(ae_maps, 0.9), torch.quantile(ae_maps, 0.995),
    ))
    if (not all(np.isfinite(value) for value in quantiles)
            or quantiles[1] <= quantiles[0]
            or quantiles[3] <= quantiles[2]):
        raise ValueError("validation maps did not produce usable quantiles")
    return quantiles


def score_from_maps(map_st: torch.Tensor, map_ae: torch.Tensor,
                    quantiles: tuple[float, float, float, float]) -> float:
    """Match the original EfficientAD fused-map padding and 256px peak score."""
    st_start, st_end, ae_start, ae_end = quantiles
    if st_end <= st_start or ae_end <= ae_start:
        raise ValueError("quantile ranges must be positive")
    combined = 0.05 * ((map_st - st_start) / (st_end - st_start)
                       + (map_ae - ae_start) / (ae_end - ae_start))
    expanded = F.interpolate(F.pad(combined, (4, 4, 4, 4)),
                             size=(256, 256), mode="bilinear")
    score = float(expanded.amax())
    if not np.isfinite(score):
        raise ValueError("nonfinite EfficientAD score")
    return score


def _candidate_module(external_repo: Path):
    if not (external_repo / "efficientad.py").is_file():
        raise FileNotFoundError(external_repo / "efficientad.py")
    sys.path.insert(0, str(external_repo.resolve()))
    return importlib.import_module("efficientad")


def _load_models(weights_dir: Path, candidate, width: int):
    models = (
        candidate.get_pdn_small(width),
        candidate.get_pdn_small(2 * width),
        candidate.get_autoencoder(width),
    )
    for model, name in zip(models, MODEL_NAMES):
        saved = torch.load(weights_dir / name, map_location="cpu")
        model.load_state_dict(saved.state_dict())
        model.eval()
    return models


def _normal_validation_crops(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    paths = sorted(directory.glob("*.png"))
    if not paths:
        raise ValueError("normal validation directory contains no PNG crops")
    return paths


def _image_tensor(path: Path, candidate, device: torch.device) -> torch.Tensor:
    with Image.open(path) as image:
        if image.size != (256, 256):
            raise ValueError(f"expected a 256x256 crop: {path}")
        return candidate.default_transform(image.convert("RGB"))[None].to(device)


def _device(name: str) -> torch.device:
    if name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    return torch.device("cuda" if name == "auto" and torch.cuda.is_available()
                        else "cpu" if name == "auto" else name)


def build(args: argparse.Namespace) -> dict:
    """Create a separate projected bundle; source bundle remains untouched."""
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    source = verify_model_bundle(args.source_manifest, args.source_weights,
                                 args.source_normalization, args.source_summary)
    paths = _normal_validation_crops(args.validation_dir)
    candidate = _candidate_module(args.external_repo)
    source_models = _load_models(args.source_weights, candidate, SOURCE_CHANNELS)
    with np.load(args.source_normalization) as calibration:
        mean = calibration["teacher_mean"].copy()
        std = calibration["teacher_std"].copy()
    p = projector()
    models = project_models(source_models, p, mean, std)
    device = _device(args.device)
    models = tuple(model.to(device).eval() for model in models)
    raw_pairs = [raw_maps(_image_tensor(path, candidate, device), models)
                 for path in paths]
    q = calibration_from_maps(raw_pairs)
    scores = [score_from_maps(st, ae, q) for st, ae in raw_pairs]
    threshold = max(scores)
    bundle_id = f"{source['bundle_id']}_projected320_seed{PROJECTION_SEED}"
    summary = {
        "status": "experimental_no_independent_test",
        "bundle_id": bundle_id,
        "source_bundle_id": source["bundle_id"],
        "source_bundle_manifest_sha256": sha256_file(args.source_manifest),
        "projected_channels": PROJECTED_CHANNELS,
        "projection_seed": PROJECTION_SEED,
        "projection_matrix_sha256": hashlib.sha256(p.numpy().tobytes()).hexdigest(),
        "device_used_for_calibration": str(device),
        "q_st_start": q[0], "q_st_end": q[1],
        "q_ae_start": q[2], "q_ae_end": q[3],
        "threshold": threshold,
        "threshold_rule": "maximum 256x256 fused-map peak on normal validation crops",
        "normal_validation": [
            {"file": path.name, "sha256": sha256_file(path), "score": score}
            for path, score in zip(paths, scores)
        ],
    }
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".projection320-",
                                     dir=args.output_dir.parent) as temporary:
        root = Path(temporary)
        weights = root / "weights"
        weights.mkdir()
        for model, name in zip(models, MODEL_NAMES):
            torch.save(model.cpu(), weights / name)
        np.savez(root / "normalization.npz",
                 teacher_mean=np.zeros((1, PROJECTED_CHANNELS, 1, 1), dtype=np.float32),
                 teacher_std=np.ones((1, PROJECTED_CHANNELS, 1, 1), dtype=np.float32),
                 q_st_start=np.float32(q[0]), q_st_end=np.float32(q[1]),
                 q_ae_start=np.float32(q[2]), q_ae_end=np.float32(q[3]))
        (root / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest = create_model_bundle(bundle_id, weights,
                                       root / "normalization.npz", root / "summary.json")
        manifest.update({
            "status": summary["status"],
            "source_bundle_id": source["bundle_id"],
            "projection_seed": PROJECTION_SEED,
            "projected_channels": PROJECTED_CHANNELS,
            "projection_matrix_sha256": summary["projection_matrix_sha256"],
        })
        (root / "model_bundle.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        verify_model_bundle(root / "model_bundle.json", weights,
                            root / "normalization.npz", root / "summary.json")
        root.rename(args.output_dir)
    return {"output_dir": str(args.output_dir.resolve()),
            "bundle_id": bundle_id, "normal_validation_count": len(paths),
            "threshold": threshold, "device": str(device)}


def score_crops(args: argparse.Namespace) -> dict:
    """Score 256px PNG crops from a previously built projected bundle."""
    root = args.bundle_dir
    bundle = verify_model_bundle(root / "model_bundle.json", root / "weights",
                                 root / "normalization.npz", root / "summary.json")
    if (bundle.get("projected_channels") != PROJECTED_CHANNELS
            or bundle.get("projection_seed") != PROJECTION_SEED):
        raise ValueError("bundle is not this projected candidate")
    with np.load(root / "normalization.npz") as calibration:
        if (not np.array_equal(calibration["teacher_mean"],
                               np.zeros((1, PROJECTED_CHANNELS, 1, 1)))
                or not np.array_equal(calibration["teacher_std"],
                                      np.ones((1, PROJECTED_CHANNELS, 1, 1)))):
            raise ValueError("expected folded teacher normalization")
        q = tuple(float(calibration[key]) for key in
                  ("q_st_start", "q_st_end", "q_ae_start", "q_ae_end"))
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    threshold = float(summary["threshold"])
    candidate = _candidate_module(args.external_repo)
    device = _device(args.device)
    models = tuple(model.to(device).eval() for model in
                   _load_models(root / "weights", candidate, PROJECTED_CHANNELS))
    if not args.images_dir.is_dir():
        raise FileNotFoundError(args.images_dir)
    paths = sorted(args.images_dir.rglob("*.png"))
    if not paths:
        raise ValueError("images directory contains no PNG crops")
    rows = []
    for path in paths:
        st, ae = raw_maps(_image_tensor(path, candidate, device), models)
        score = score_from_maps(st, ae, q)
        rows.append({"file": path.name, "sha256": sha256_file(path),
                     "score": score, "predicted_defect": score > threshold})
    return {"status": summary["status"], "bundle_id": bundle["bundle_id"],
            "threshold": threshold, "device": str(device), "images": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build", help="project and recalibrate a separate bundle")
    build_parser.add_argument("--external-repo", type=Path, default=EXTERNAL_REPO)
    build_parser.add_argument("--source-weights", type=Path, default=SOURCE_WEIGHTS)
    build_parser.add_argument("--source-normalization", type=Path, default=SOURCE_NORMALIZATION)
    build_parser.add_argument("--source-summary", type=Path, default=SOURCE_SUMMARY)
    build_parser.add_argument("--source-manifest", type=Path, default=SOURCE_MANIFEST)
    build_parser.add_argument("--validation-dir", required=True, type=Path,
                              help="normal 256px validation crops only; never use the test set")
    build_parser.add_argument("--output-dir", required=True, type=Path)
    build_parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    score_parser = commands.add_parser("score-crops", help="score PNG crops with a built bundle")
    score_parser.add_argument("--external-repo", type=Path, default=EXTERNAL_REPO)
    score_parser.add_argument("--bundle-dir", required=True, type=Path)
    score_parser.add_argument("--images-dir", required=True, type=Path)
    score_parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()
    print(json.dumps(build(args) if args.command == "build" else score_crops(args),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

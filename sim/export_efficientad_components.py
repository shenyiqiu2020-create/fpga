"""Export separate EfficientAD maps and calibrate an image threshold.

Run in the isolated Python 3.10 environment used by the external candidate.
The existing trained weights and MVTec AD images are read-only inputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

import numpy as np
import tifffile
import torch
from PIL import Image
from torch.utils.data import DataLoader
from torchvision import transforms

from sim.evaluate_efficientad_maps import (
    checked_reference_difference,
    classify_with_normal_validation,
    image_auc,
)


def full_size_map(map_tensor: torch.Tensor, height: int, width: int) -> np.ndarray:
    """Use the candidate's padding and interpolation before image scoring."""
    result = torch.nn.functional.pad(map_tensor, (4, 4, 4, 4))
    result = torch.nn.functional.interpolate(result, (height, width), mode="bilinear")
    return result[0, 0].cpu().numpy()


def save_maps(output_root: Path, split: str, category: str, stem: str,
              maps: tuple[np.ndarray, np.ndarray, np.ndarray]) -> None:
    for name, array in zip(("combined", "student_teacher", "autoencoder"), maps):
        if not np.isfinite(array).all():
            raise ValueError(f"non-finite {name} map: {split}/{category}/{stem}")
        destination = output_root / "maps" / split / name / category
        destination.mkdir(parents=True, exist_ok=True)
        tifffile.imwrite(destination / f"{stem}.tiff", array)


def export(args: argparse.Namespace) -> dict:
    if args.output_dir.exists():
        raise FileExistsError(f"choose a new output directory: {args.output_dir}")
    if not args.class_root.is_dir() or not args.reference_maps_root.is_dir():
        raise FileNotFoundError("dataset or reference anomaly maps are missing")
    training_files = ("teacher_final.pth", "student_final.pth", "autoencoder_final.pth")
    for name in training_files:
        if not (args.trainings_dir / name).is_file():
            raise FileNotFoundError(args.trainings_dir / name)

    sys.path.insert(0, str(args.external_repo.resolve()))
    import efficientad as candidate  # noqa: E402 - external code pinned in report

    torch.manual_seed(candidate.seed)
    np.random.seed(candidate.seed)
    random.seed(candidate.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Instantiate in the same order as candidate.main() to reproduce RNG state.
    teacher = candidate.get_pdn_small(candidate.out_channels)
    student = candidate.get_pdn_small(2 * candidate.out_channels)
    autoencoder = candidate.get_autoencoder(candidate.out_channels)
    for module, name in zip((teacher, student, autoencoder), training_files):
        saved = torch.load(args.trainings_dir / name, map_location="cpu")
        module.load_state_dict(saved.state_dict())
        module.eval().to(device)

    full_train = candidate.ImageFolderWithoutTarget(
        str(args.class_root / "train"),
        transform=transforms.Lambda(candidate.train_transform),
    )
    train_size = int(0.9 * len(full_train))
    train_set, validation_set = torch.utils.data.random_split(
        full_train, [train_size, len(full_train) - train_size],
        torch.Generator().manual_seed(candidate.seed),
    )
    train_loader = DataLoader(train_set, batch_size=1, shuffle=True,
                              num_workers=4, pin_memory=True)
    validation_loader = DataLoader(validation_set, batch_size=1)
    teacher_mean, teacher_std = candidate.teacher_normalization(teacher, train_loader)
    quantiles = candidate.map_normalization(
        validation_loader, teacher, student, autoencoder, teacher_mean, teacher_std,
    )

    args.output_dir.mkdir(parents=True)
    np.savez(args.output_dir / "normalization.npz",
             teacher_mean=teacher_mean.cpu().numpy(),
             teacher_std=teacher_std.cpu().numpy(),
             q_st_start=quantiles[0].cpu().numpy(),
             q_st_end=quantiles[1].cpu().numpy(),
             q_ae_start=quantiles[2].cpu().numpy(),
             q_ae_end=quantiles[3].cpu().numpy())

    def predict_image(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        with Image.open(path) as image:
            width, height = image.size
            tensor = candidate.default_transform(image)[None].to(device)
        with torch.no_grad():
            maps = candidate.predict(tensor, teacher, student, autoencoder,
                                     teacher_mean, teacher_std, *quantiles)
            return tuple(full_size_map(value, height, width) for value in maps)

    validation_rows = []
    for index in validation_set.indices:
        path = Path(full_train.samples[index][0])
        maps = predict_image(path)
        save_maps(args.output_dir, "validation", "good", path.stem, maps)
        validation_rows.append({"image": path.name, "score_max": float(maps[0].max())})

    test_rows = []
    max_reference_difference = 0.0
    test_files = sorted((args.class_root / "test").glob("*/*.png"))
    reference_files = set(args.reference_maps_root.glob("*/*.tiff"))
    if len(test_files) != len(reference_files):
        raise ValueError("reference map count differs from test image count")
    for path in test_files:
        maps = predict_image(path)
        reference_path = args.reference_maps_root / path.parent.name / f"{path.stem}.tiff"
        if reference_path not in reference_files:
            raise FileNotFoundError(reference_path)
        reference = tifffile.imread(reference_path)
        difference = checked_reference_difference(reference, maps[0])
        max_reference_difference = max(max_reference_difference, difference)
        save_maps(args.output_dir, "test", path.parent.name, path.stem, maps)
        test_rows.append({"class": path.parent.name, "image": path.name,
                          "label": int(path.parent.name != "good"),
                          "score_max": float(maps[0].max()),
                          "reference_max_abs_diff": difference})

    threshold, confusion = classify_with_normal_validation(
        [row["score_max"] for row in validation_rows], test_rows
    )
    for name, rows in (("validation_scores.csv", validation_rows),
                       ("test_predictions.csv", test_rows)):
        with (args.output_dir / name).open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    summary = {
        "threshold_rule": "max of 21 normal validation image scores; defect if score > threshold",
        "threshold": threshold,
        "validation_normal_count": len(validation_rows),
        "test_image_count": len(test_rows),
        "test_image_auroc_percent": 100.0 * image_auc(
            [row["label"] for row in test_rows],
            [row["score_max"] for row in test_rows],
        ),
        "test_confusion": confusion,
        "max_abs_difference_from_prior_fused_map": max_reference_difference,
        "device": str(device),
        "input_size": [candidate.image_size, candidate.image_size],
        "pixel_localization_metric": None,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-repo", type=Path, required=True)
    parser.add_argument("--class-root", type=Path, required=True)
    parser.add_argument("--trainings-dir", type=Path, required=True)
    parser.add_argument("--reference-maps-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

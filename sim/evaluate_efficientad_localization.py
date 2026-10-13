"""Evaluate pixel ranking of saved EfficientAD maps on MVTec AD defects.

The reported value is the mean of per-defect-image pixel ROC AUCs. It is not
the original paper's complete benchmark, a binary segmentation score, or an
estimate of performance on the team's proposed physical part.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from sim.evaluate_efficientad_maps import pixel_auc


MAP_NAMES = ("combined", "student_teacher", "autoencoder")


def load_map(path: Path, shape: tuple[int, int]) -> np.ndarray:
    with Image.open(path) as image:
        score_map = np.asarray(image, dtype=np.float32)
    if score_map.shape != shape or not np.isfinite(score_map).all():
        raise ValueError(f"map size or values are invalid: {path}")
    return score_map


def render_failure(source: Path, mask: np.ndarray | None, score_map: np.ndarray,
                   score: float, threshold: float, destination: Path) -> None:
    """Create a local visual review sheet; heat colors scale per image."""
    size = (360, 360)
    with Image.open(source) as image:
        original = image.convert("RGB").resize(size)
    if mask is None:
        annotated = original.copy()
    else:
        overlay = Image.new("RGB", size, (255, 35, 35))
        alpha = Image.fromarray(mask.astype(np.uint8) * 110).resize(size)
        annotated = Image.composite(overlay, original, alpha)
    low, high = float(np.min(score_map)), float(np.max(score_map))
    normalized = np.zeros_like(score_map, dtype=np.uint8)
    if high > low:
        normalized = np.clip((score_map - low) * (255.0 / (high - low)), 0, 255).astype(np.uint8)
    heat = ImageOps.colorize(Image.fromarray(normalized).resize(size),
                             black=(8, 8, 36), white=(255, 100, 0))
    canvas = Image.new("RGB", (1080, 400), "white")
    for index, panel in enumerate((original, annotated, heat)):
        canvas.paste(panel, (index * 360, 40))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 8), f"Input: {source.parent.name}/{source.name}", fill="black")
    draw.text((368, 8), "Ground truth mask" if mask is not None else "Ground truth: normal",
              fill="black")
    draw.text((728, 8), f"Fused heat (own scale); score={score:.4f}; limit={threshold:.4f}",
              fill="black")
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination)


def evaluate(class_root: Path, maps_root: Path, predictions_csv: Path,
             output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"choose a new output directory: {output_dir}")
    test_images = sorted((class_root / "test").glob("*/*.png"))
    if not test_images:
        raise ValueError("no test images found")
    for name in MAP_NAMES:
        expected = {maps_root / name / p.parent.name / f"{p.stem}.tiff"
                    for p in test_images}
        actual = set((maps_root / name).glob("*/*.tiff"))
        if expected != actual:
            raise ValueError(f"{name}: {len(expected - actual)} missing and "
                             f"{len(actual - expected)} extra maps")

    with predictions_csv.open(encoding="utf-8", newline="") as file:
        predictions = {(r["class"], r["image"]): r for r in csv.DictReader(file)}
    if len(predictions) != len(test_images):
        raise ValueError("prediction count differs from test image count")
    threshold = None
    # Image-level threshold is provided by the neighboring summary, never by GT masks.
    with (predictions_csv.parent / "summary.json").open(encoding="utf-8") as file:
        threshold = float(json.load(file)["threshold"])

    output_dir.mkdir(parents=True)
    rows = []
    scores_by_class = defaultdict(lambda: defaultdict(list))
    for source in test_images:
        if source.parent.name == "good":
            continue
        mask_path = (class_root / "ground_truth" / source.parent.name
                     / f"{source.stem}_mask.png")
        with Image.open(mask_path) as image:
            mask = np.asarray(image) > 0
        with Image.open(source) as image:
            width, height = image.size
        if mask.shape != (height, width):
            raise ValueError(f"mask size differs from image: {mask_path}")
        row = {"class": source.parent.name, "image": source.name,
               "defect_pixel_fraction": float(mask.mean())}
        for name in MAP_NAMES:
            path = maps_root / name / source.parent.name / f"{source.stem}.tiff"
            value = pixel_auc(mask, load_map(path, mask.shape))
            row[f"{name}_pixel_auc"] = value
            scores_by_class[source.parent.name][name].append(value)
        rows.append(row)

    with (output_dir / "per_defect_image.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    failures = []
    for source in test_images:
        key = (source.parent.name, source.name)
        prediction = predictions.get(key)
        if prediction is None:
            raise ValueError(f"prediction missing: {key}")
        if prediction["correct"] != "0":
            continue
        mask = None
        if source.parent.name != "good":
            with Image.open(class_root / "ground_truth" / source.parent.name
                            / f"{source.stem}_mask.png") as image:
                mask = np.asarray(image) > 0
        with Image.open(source) as image:
            shape = (image.height, image.width)
        fused = load_map(maps_root / "combined" / source.parent.name
                         / f"{source.stem}.tiff", shape)
        preview = output_dir / "failure_previews" / f"{source.parent.name}_{source.stem}.png"
        render_failure(source, mask, fused, float(prediction["score_max"]),
                       threshold, preview)
        failures.append({"class": source.parent.name, "image": source.name,
                         "score_max": float(prediction["score_max"]),
                         "kind": "false_positive" if mask is None else "false_negative",
                         "preview": str(preview)})

    summary = {
        "metric": "macro mean of exact pixel ROC AUC over 63 anomalous images",
        "defect_image_count": len(rows),
        "macro_pixel_auc_percent": {
            name: 100.0 * float(np.mean([row[f"{name}_pixel_auc"] for row in rows]))
            for name in MAP_NAMES
        },
        "per_class_pixel_auc_percent": {
            category: {name: 100.0 * float(np.mean(values[name])) for name in MAP_NAMES}
            for category, values in sorted(scores_by_class.items())
        },
        "failure_count": len(failures),
        "failures": failures,
        "pixel_segmentation_threshold": None,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-root", type=Path, required=True)
    parser.add_argument("--maps-root", type=Path, required=True)
    parser.add_argument("--predictions-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.class_root, args.maps_root, args.predictions_csv,
                              args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

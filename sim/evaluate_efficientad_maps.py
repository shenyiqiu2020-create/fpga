"""Summarize saved EfficientAD anomaly maps against an MVTec AD test split.

This evaluates image ranking only. It does not choose a decision threshold or
measure pixel-level localization accuracy.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image


def image_auc(labels: list[int], scores: list[float]) -> float:
    """Return image AUROC using average ranks for tied scores."""
    if len(labels) != len(scores) or not labels:
        raise ValueError("labels and scores must have the same nonzero length")
    y = np.asarray(labels, dtype=np.int8)
    s = np.asarray(scores, dtype=np.float64)
    if not np.isin(y, (0, 1)).all() or not np.isfinite(s).all():
        raise ValueError("labels must be binary and scores finite")
    positives = int(y.sum())
    negatives = len(y) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("both normal and anomalous images are required")

    order = np.argsort(s, kind="stable")
    sorted_scores = s[order]
    ranks = np.empty(len(s), dtype=np.float64)
    start = 0
    while start < len(s):
        end = start + 1
        while end < len(s) and sorted_scores[end] == sorted_scores[start]:
            end += 1
        ranks[order[start:end]] = (start + 1 + end) / 2.0
        start = end
    return float((ranks[y == 1].sum() - positives * (positives + 1) / 2)
                 / (positives * negatives))


def pixel_auc(mask: np.ndarray, score_map: np.ndarray) -> float:
    """Exact ROC AUC for one defect image, with average ranks for ties."""
    if mask.shape != score_map.shape or mask.ndim != 2:
        raise ValueError("mask and score map must be matching 2D arrays")
    labels = np.asarray(mask, dtype=bool).ravel()
    scores = np.asarray(score_map, dtype=np.float32).ravel()
    if not np.isfinite(scores).all():
        raise ValueError("score map contains non-finite values")
    positives = int(labels.sum())
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("mask must include defect and background pixels")
    order = np.argsort(scores, kind="stable")
    sorted_scores = scores[order]
    starts = np.r_[0, np.flatnonzero(np.diff(sorted_scores) != 0) + 1]
    ends = np.r_[starts[1:], len(scores)]
    average_ranks = np.repeat((starts + 1 + ends) / 2.0, ends - starts)
    positive_rank_sum = float(average_ranks[labels[order]].sum())
    return (positive_rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def classify_with_normal_validation(validation_scores: list[float],
                                    test_rows: list[dict]) -> tuple[float, dict]:
    """Use the highest normal validation score as a strict test threshold."""
    if not validation_scores or not np.isfinite(validation_scores).all():
        raise ValueError("normal validation scores are missing or non-finite")
    threshold = float(max(validation_scores))
    counts = Counter()
    for row in test_rows:
        predicted = int(float(row["score_max"]) > threshold)
        row["predicted_defect"] = predicted
        row["correct"] = int(predicted == row["label"])
        if row["label"] == 1:
            counts["tp" if predicted else "fn"] += 1
        else:
            counts["fp" if predicted else "tn"] += 1
    return threshold, {key: counts[key] for key in ("tp", "fn", "tn", "fp")}


def checked_reference_difference(reference: np.ndarray, current: np.ndarray,
                                 tolerance: float = 1e-4) -> float:
    """Reject a reconstructed map that disagrees with the saved baseline."""
    if reference.shape != current.shape or not np.isfinite(reference).all():
        raise ValueError("reference map size or values are invalid")
    difference = float(np.max(np.abs(reference - current)))
    if not np.isfinite(difference) or difference > tolerance:
        raise ValueError(f"reconstructed map differs from reference: {difference}")
    return difference


def evaluate(class_root: Path, maps_root: Path) -> tuple[list[dict], dict]:
    test_root = class_root / "test"
    if not test_root.is_dir() or not maps_root.is_dir():
        raise FileNotFoundError("test images or anomaly maps directory is missing")

    images = sorted(test_root.glob("*/*.png"))
    if not images:
        raise ValueError("no test PNG images found")
    expected_maps = {maps_root / p.parent.name / f"{p.stem}.tiff" for p in images}
    actual_maps = set(maps_root.glob("*/*.tiff"))
    missing = expected_maps - actual_maps
    extra = actual_maps - expected_maps
    if missing or extra:
        raise ValueError(f"map mismatch: {len(missing)} missing, {len(extra)} extra")

    rows = []
    for source in images:
        map_path = maps_root / source.parent.name / f"{source.stem}.tiff"
        with Image.open(source) as image:
            width, height = image.size
        with Image.open(map_path) as image:
            anomaly_map = np.asarray(image, dtype=np.float32)
        if anomaly_map.shape != (height, width):
            raise ValueError(f"map size differs from input: {map_path}")
        if not np.isfinite(anomaly_map).all():
            raise ValueError(f"non-finite map values: {map_path}")
        rows.append({
            "class": source.parent.name,
            "image": source.name,
            "label": 0 if source.parent.name == "good" else 1,
            "score_max": float(anomaly_map.max()),
            "score_mean": float(anomaly_map.mean()),
            "map_min": float(anomaly_map.min()),
            "map_max": float(anomaly_map.max()),
        })

    counts = {name: sum(row["class"] == name for row in rows)
              for name in sorted({row["class"] for row in rows})}
    summary = {
        "metric": "image AUROC; score=max of full-resolution fused map",
        "image_auroc_percent": 100.0 * image_auc(
            [row["label"] for row in rows],
            [row["score_max"] for row in rows],
        ),
        "test_image_count": len(rows),
        "counts_by_class": counts,
        "decision_threshold": None,
        "pixel_localization_metric": None,
    }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-root", type=Path, required=True)
    parser.add_argument("--maps-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    rows, summary = evaluate(args.class_root, args.maps_root)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "per_image.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Audit frozen image-level defect decisions, keeping photos grouped by part.

Input CSV columns: image, object_group, label (good or defect), score, threshold.
The script never chooses a threshold from the evaluated photos.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def confusion(rows: list[tuple[bool, bool]]) -> dict[str, int]:
    return {
        "tp": sum(truth and predicted for truth, predicted in rows),
        "fn": sum(truth and not predicted for truth, predicted in rows),
        "tn": sum(not truth and not predicted for truth, predicted in rows),
        "fp": sum(not truth and predicted for truth, predicted in rows),
    }


def evaluate(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("no photos to evaluate")
    required = {"image", "object_group", "label", "score", "threshold"}
    if not required.issubset(rows[0]):
        raise ValueError(f"missing columns: {sorted(required - set(rows[0]))}")

    photos = []
    parts: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    thresholds = set()
    seen_images = set()
    for row in rows:
        image = row["image"]
        group = row["object_group"]
        if not image or not group or image in seen_images:
            raise ValueError(f"missing group/image or duplicate image: {image}")
        seen_images.add(image)
        if row["label"] not in {"good", "defect"}:
            raise ValueError(f"unknown label: {row['label']}")
        score = float(row["score"])
        threshold = float(row["threshold"])
        if not (-float("inf") < score < float("inf")
                and -float("inf") < threshold < float("inf")):
            raise ValueError("nonfinite score or threshold")
        thresholds.add(threshold)
        truth = row["label"] == "defect"
        predicted = score > threshold
        photos.append((truth, predicted))
        parts[group].append((truth, predicted))
    if len(thresholds) != 1:
        raise ValueError("mixed frozen thresholds")

    part_decisions = []
    for group, observations in parts.items():
        truths = {truth for truth, _ in observations}
        if len(truths) != 1:
            raise ValueError(f"conflicting labels for part {group}")
        # A photographed part is flagged if any of its available views is flagged.
        part_decisions.append((observations[0][0], any(pred for _, pred in observations)))
    return {
        "threshold": thresholds.pop(),
        "photos": {"count": len(photos), **confusion(photos)},
        "parts_any_view": {"count": len(parts), **confusion(part_decisions)},
        "part_view_counts": {group: len(observations)
                             for group, observations in sorted(parts.items())},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scores", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.scores), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

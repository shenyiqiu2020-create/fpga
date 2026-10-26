"""Join frozen source identities to model scores and report grouped accuracy.

The threshold must already be frozen in the model bundle. Rejected crops and
duplicate source files remain visible in the denominator audit.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from sim.evaluate_tie_mount_binary import confusion


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"empty CSV: {path}")
    return rows


def summarize(source_map: Path, predictions: Path, role: str) -> tuple[list[dict], dict]:
    sources = [row for row in _read_csv(source_map) if row["role"] == role]
    if not sources:
        raise ValueError(f"no {role} source photos")
    scores = _read_csv(predictions)
    by_image = {row["image"]: row for row in scores}
    if len(by_image) != len(scores):
        raise ValueError("duplicate prediction image")
    output: list[dict] = []
    used: set[str] = set()
    photo_decisions: list[tuple[bool, bool]] = []
    groups: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    thresholds: set[float] = set()
    statuses: dict[str, int] = defaultdict(int)
    for source in sources:
        if source["label"] not in ("good", "defect"):
            raise ValueError(f"unexpected source label: {source['label']}")
        status = source["crop_status"]
        statuses[status] += 1
        row = {name: source[name] for name in ("folder", "filename", "object_group",
                                                   "leakage_cluster", "label", "role", "sha256",
                                                   "duplicate_of", "crop_status", "crop_error", "output")}
        row.update({"image": "", "crop_sha256": "", "score_max": "", "threshold": "",
                    "predicted_defect": "", "correct": ""})
        if status == "accepted":
            image = Path(source["output"]).name
            if image in used or image not in by_image:
                raise ValueError(f"missing or repeated prediction: {image}")
            used.add(image)
            score_row = by_image[image]
            score = float(score_row["score_max"])
            threshold = float(score_row["threshold"])
            if not math.isfinite(score) or not math.isfinite(threshold):
                raise ValueError(f"nonfinite prediction: {image}")
            predicted = score > threshold
            if str(predicted).lower() != score_row["predicted_defect"].lower():
                raise ValueError(f"inconsistent decision: {image}")
            crop_path = source_map.parent / source["output"]
            digest = hashlib.sha256(crop_path.read_bytes()).hexdigest()
            if digest != score_row["crop_sha256"]:
                raise ValueError(f"prediction crop hash mismatch: {image}")
            truth = source["label"] == "defect"
            thresholds.add(threshold)
            photo_decisions.append((truth, predicted))
            groups[source["object_group"]].append((truth, predicted))
            row.update({"image": image, "crop_sha256": digest, "score_max": score,
                        "threshold": threshold, "predicted_defect": predicted,
                        "correct": truth == predicted})
        elif status not in ("rejected", "skipped_duplicate"):
            raise ValueError(f"unexpected crop status: {status}")
        output.append(row)
    if set(by_image) != used or len(thresholds) != 1:
        raise ValueError("extra predictions or mixed thresholds")
    part_decisions = []
    for observations in groups.values():
        truths = {truth for truth, _ in observations}
        if len(truths) != 1:
            raise ValueError("one part has conflicting labels")
        part_decisions.append((observations[0][0], any(pred for _, pred in observations)))
    photos = confusion(photo_decisions)
    parts = confusion(part_decisions)
    photo_recall = photos["tp"] / (photos["tp"] + photos["fn"])
    photo_specificity = photos["tn"] / (photos["tn"] + photos["fp"])
    part_recall = parts["tp"] / (parts["tp"] + parts["fn"])
    part_specificity = parts["tn"] / (parts["tn"] + parts["fp"])
    summary = {"role": role, "threshold": thresholds.pop(),
               "source_photos": len(sources),
               "source_parts": len({row["object_group"] for row in sources}),
               "scored_parts": len(groups), "crop_status": dict(statuses),
               "photos": {"count": len(photo_decisions), **photos,
                          "accuracy": (photos["tp"] + photos["tn"]) / len(photo_decisions),
                          "balanced_accuracy": (photo_recall + photo_specificity) / 2,
                          "defect_recall": photo_recall,
                          "normal_specificity": photo_specificity},
               "parts_any_view": {"count": len(part_decisions), **parts,
                                  "accuracy": (parts["tp"] + parts["tn"]) / len(part_decisions),
                                  "balanced_accuracy": (part_recall + part_specificity) / 2,
                                  "defect_recall": part_recall,
                                  "normal_specificity": part_specificity},
               "wrong_images": [row["image"] for row in output if row["correct"] is False]}
    return output, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-map", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--role", choices=("development", "holdout"), required=True)
    parser.add_argument("--output-csv", required=True, type=Path)
    parser.add_argument("--summary-json", required=True, type=Path)
    args = parser.parse_args()
    rows, summary = summarize(args.source_map, args.predictions, args.role)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    args.summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

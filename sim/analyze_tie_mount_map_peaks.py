"""Locate EfficientAD score peaks relative to the photographed white part.

This is an error-analysis report, not a defect classifier.  A missing corner
can score outside the observed foreground, so an outside peak is not by itself
proof of a false positive or a bad localization.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

from src.tie_mount_crop import white_foreground_mask


FIELDS = ("split", "class", "image", "object_group", "score_max",
          "peak_x", "peak_y", "peak_rgb", "peak_on_white_mask",
          "peak_distance_to_white_px", "foreground_score_max",
          "background_score_max", "white_mask_fraction")


def inspect_one(image_path: Path, map_path: Path, split: str, label: str) -> dict:
    with Image.open(image_path) as opened:
        image = opened.convert("RGB")
    pixels = np.asarray(image)
    mask = white_foreground_mask(image)
    score_map = tifffile.imread(map_path)
    if score_map.shape != mask.shape or not np.isfinite(score_map).all():
        raise ValueError(f"invalid score map for {image_path}")
    if not mask.any() or mask.all():
        raise ValueError(f"white foreground is ambiguous in {image_path}")
    peak_y, peak_x = np.unravel_index(int(np.argmax(score_map)), score_map.shape)
    if mask[peak_y, peak_x]:
        distance = 0.0
    else:
        ys, xs = np.nonzero(mask)
        distance = float(np.sqrt(np.min(
            (xs.astype(np.int32) - peak_x) ** 2
            + (ys.astype(np.int32) - peak_y) ** 2)))
    return {
        "split": split,
        "class": label,
        "image": image_path.name,
        "object_group": image_path.stem.split("_", 1)[-1],
        "score_max": float(score_map[peak_y, peak_x]),
        "peak_x": int(peak_x),
        "peak_y": int(peak_y),
        "peak_rgb": "/".join(map(str, pixels[peak_y, peak_x].tolist())),
        "peak_on_white_mask": bool(mask[peak_y, peak_x]),
        "peak_distance_to_white_px": round(distance, 2),
        "foreground_score_max": float(score_map[mask].max()),
        "background_score_max": float(score_map[~mask].max()),
        "white_mask_fraction": round(float(mask.mean()), 4),
    }


def analyze(class_root: Path, maps_root: Path, output: Path) -> list[dict]:
    rows = []
    for split in ("validation", "test"):
        for image_path in sorted((class_root / split).glob("*/*.png")):
            label = image_path.parent.name
            map_path = maps_root / split / "combined" / label / f"{image_path.stem}.tiff"
            if not map_path.is_file():
                raise FileNotFoundError(map_path)
            rows.append(inspect_one(image_path, map_path, split, label))
    if not rows:
        raise ValueError("no validation or test images found")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-root", required=True, type=Path)
    parser.add_argument("--maps-root", required=True, type=Path,
                        help="components/maps directory from the EfficientAD exporter")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = analyze(args.class_root, args.maps_root, args.output)
    outside = sum(row["peak_on_white_mask"] is False for row in rows)
    print(f"Analyzed {len(rows)} images; {outside} global peaks outside the white mask. "
          f"Report: {args.output}")


if __name__ == "__main__":
    main()

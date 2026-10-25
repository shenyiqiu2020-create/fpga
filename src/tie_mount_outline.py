"""Rotation-tolerant outline check for visible corner/edge loss.

This geometric baseline complements, but does not replace, the EfficientAD
candidate. It is meant for full, near-overhead views of a white square part on
a contrasting background. A score is not a validated probability.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from src.tie_mount_crop import crop_mount, white_foreground_mask


def corner_loss_score(mask: np.ndarray) -> dict:
    """Compare the least occupied corner with the other three after alignment.

    A square has four equivalent planar orientations. Searching 0..90 degrees
    for the smallest enclosing rectangle therefore avoids requiring the user
    to place it upright. This does not correct perspective or camera tilt.
    """
    if mask.ndim != 2 or mask.dtype != bool:
        raise ValueError("mask must be a 2-D boolean array")
    y, x = np.nonzero(mask)
    if len(x) < 500:
        raise ValueError("too few foreground pixels to measure the outline")
    x, y = x.astype(np.float32), y.astype(np.float32)
    best: tuple[float, float, float, float, float, float] | None = None
    for angle in np.arange(0.0, 90.0, 0.5):
        radians = np.deg2rad(angle)
        cosine, sine = np.cos(radians), np.sin(radians)
        u = x * cosine + y * sine
        v = -x * sine + y * cosine
        u0, u1 = float(u.min()), float(u.max())
        v0, v1 = float(v.min()), float(v.max())
        area = (u1 - u0) * (v1 - v0)
        if best is None or area < best[0]:
            best = (area, float(angle), u0, u1, v0, v1)
    assert best is not None
    _, angle, u0, u1, v0, v1 = best
    if min(u1 - u0, v1 - v0) < 20:
        raise ValueError("part outline is too small")
    radians = np.deg2rad(angle)
    cosine, sine = np.cos(radians), np.sin(radians)
    u = (x * cosine + y * sine - u0) / (u1 - u0)
    v = (-x * sine + y * cosine - v0) / (v1 - v0)
    corner_counts = []
    for low_u in (True, False):
        for low_v in (True, False):
            in_u = (u < 0.18) if low_u else (u > 0.82)
            in_v = (v < 0.18) if low_v else (v > 0.82)
            corner_counts.append(int(np.count_nonzero(in_u & in_v)))
    weakest = int(np.argmin(corner_counts))
    reference = float(np.median([count for i, count in enumerate(corner_counts)
                                 if i != weakest]))
    if reference < 100:
        raise ValueError("corner regions could not be measured reliably")
    corner_ratio = corner_counts[weakest] / reference
    raw_u = u0 if weakest < 2 else u1
    raw_v = v0 if weakest % 2 == 0 else v1
    corner_x = raw_u * cosine - raw_v * sine
    corner_y = raw_u * sine + raw_v * cosine
    return {"angle_mod_90_degrees": angle,
            "corner_occupancy": corner_counts,
            "weakest_corner": weakest,
            "weakest_corner_xy": [round(float(corner_x), 1), round(float(corner_y), 1)],
            "corner_ratio": round(float(corner_ratio), 4),
            "corner_loss_score": round(float(1.0 - corner_ratio), 4)}


def analyze_photo(path: Path, threshold: float = 0.35) -> dict:
    """Return a provisional outline verdict plus a position in the source photo."""
    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be between 0 and 1")
    cropped, crop = crop_mount(path, size=256)
    mask = white_foreground_mask(cropped)
    foreground_fraction = float(mask.mean())
    if not 0.15 <= foreground_fraction <= 0.8:
        raise ValueError("foreground segmentation needs visual review")
    result = corner_loss_score(mask)
    box = crop["crop_box"]
    side = box[2] - box[0]
    point = result["weakest_corner_xy"]
    result["weakest_corner_xy_source"] = [round(box[0] + point[0] * side / 256, 1),
                                           round(box[1] + point[1] * side / 256, 1)]
    result.update({"source": str(path), "crop_box": box,
                   "foreground_fraction": round(foreground_fraction, 4),
                   "threshold": threshold,
                   "provisional_verdict": "corner_or_edge_loss" if result["corner_loss_score"] > threshold else "no_outline_loss"})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--threshold", type=float, default=0.35,
                        help="provisional score cutoff; validate on independent parts")
    args = parser.parse_args()
    for path in args.images:
        try:
            print(json.dumps(analyze_photo(path, args.threshold), ensure_ascii=False))
        except ValueError as error:
            print(json.dumps({"source": str(path), "error": str(error)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

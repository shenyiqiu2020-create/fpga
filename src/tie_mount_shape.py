"""Provisional outer-contour loss candidate on an existing 256x256 crop.

This independent geometry diagnostic leaves EfficientAD's image decision and
fused anomaly map untouched. It is limited to a complete overhead view of a
light tie mount on the photographed green/brown backgrounds. The development
cutoff and confidence words below are not calibrated probabilities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from src.tie_mount_crop import tinted_white_foreground_mask


SIZE = 256
SIDE_BINS = 64
DEPTH_THRESHOLD = 0.12  # provisional value chosen on development parts only


def _largest_component(mask: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int, int]]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    best: list[tuple[int, int]] = []
    best_box = (0, 0, 0, 0, 0)
    for start_y, start_x in zip(*np.nonzero(mask)):
        sy, sx = int(start_y), int(start_x)
        if visited[sy, sx]:
            continue
        queue = deque([(sy, sx)])
        visited[sy, sx] = True
        pixels = []
        left = right = sx
        top = bottom = sy
        while queue:
            y, x = queue.popleft()
            pixels.append((y, x))
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if (0 <= ny < height and 0 <= nx < width
                        and mask[ny, nx] and not visited[ny, nx]):
                    visited[ny, nx] = True
                    queue.append((ny, nx))
        if len(pixels) > len(best):
            best = pixels
            best_box = (len(pixels), left, top, right + 1, bottom + 1)
    result = np.zeros_like(mask, dtype=bool)
    for y, x in best:
        result[y, x] = True
    return result, best_box


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """Treat the mounting holes as material for an external-outline check."""
    height, width = mask.shape
    exterior = np.zeros_like(mask, dtype=bool)
    queue = deque()
    for y in range(height):
        for x in (0, width - 1):
            if not mask[y, x] and not exterior[y, x]:
                exterior[y, x] = True
                queue.append((y, x))
    for x in range(width):
        for y in (0, height - 1):
            if not mask[y, x] and not exterior[y, x]:
                exterior[y, x] = True
                queue.append((y, x))
    while queue:
        y, x = queue.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if (0 <= ny < height and 0 <= nx < width
                    and not mask[ny, nx] and not exterior[ny, nx]):
                exterior[ny, nx] = True
                queue.append((ny, nx))
    return ~exterior


def _foreground(crop: Image.Image) -> tuple[np.ndarray, dict]:
    if crop.size != (SIZE, SIZE):
        raise ValueError("expected a 256x256 crop")
    raw = tinted_white_foreground_mask(crop)
    component, (area, left, top, right, bottom) = _largest_component(raw)
    width, height = right - left, bottom - top
    fraction = area / (SIZE * SIZE)
    compactness = area / max(1, width * height)
    if not (0.06 < fraction < 0.75 and width >= 70 and height >= 70
            and 0.45 < width / height < 2.2 and compactness > 0.25):
        raise ValueError("light part was not isolated from the background")
    border_gap = min(left, top, SIZE - right, SIZE - bottom)
    if border_gap < 2:
        raise ValueError("selected foreground touches the crop boundary")
    # Close small streaks from gloss without bridging a macroscopic edge notch.
    image = Image.fromarray(np.uint8(component) * 255, mode="L")
    closed = image.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    filled = _fill_holes(np.asarray(closed) > 0)
    filled, _ = _largest_component(filled)
    return filled, {
        "method": "tinted-white RGB mask, largest component, 5px close, hole fill",
        "foreground_fraction": round(fraction, 4),
        "bbox_xyxy": [left, top, right, bottom],
        "bbox_fill_fraction": round(compactness, 4),
        "border_gap_px": int(border_gap),
    }


def _minimum_rectangle(x: np.ndarray, y: np.ndarray) -> dict:
    best = None
    for angle in np.arange(0.0, 90.0, 0.5):
        radians = np.deg2rad(angle)
        cosine, sine = float(np.cos(radians)), float(np.sin(radians))
        u = x * cosine + y * sine
        v = -x * sine + y * cosine
        u0, u1 = float(u.min()), float(u.max())
        v0, v1 = float(v.min()), float(v.max())
        area = (u1 - u0) * (v1 - v0)
        if best is None or area < best[0]:
            best = (area, float(angle), cosine, sine, u0, u1, v0, v1)
    assert best is not None
    _, angle, cosine, sine, u0, u1, v0, v1 = best
    if min(u1 - u0, v1 - v0) < 70:
        raise ValueError("foreground outline is too small")

    def inverse(u: float, v: float) -> list[float]:
        return [round(u * cosine - v * sine, 2),
                round(u * sine + v * cosine, 2)]

    corners = [inverse(u0, v0), inverse(u1, v0),
               inverse(u1, v1), inverse(u0, v1)]
    if any(not (-2 <= px <= SIZE + 1 and -2 <= py <= SIZE + 1)
           for px, py in corners):
        raise ValueError("expected outer rectangle extends beyond the crop")
    return {"angle_mod_90_degrees": angle, "cosine": cosine, "sine": sine,
            "u0": u0, "u1": u1, "v0": v0, "v1": v1,
            "corners_xy": corners,
            "side_lengths_px": [round(u1 - u0, 2), round(v1 - v0, 2)]}


def _side_profile(t: np.ndarray, depth: np.ndarray, side_length: float) -> tuple[float, int, float]:
    bins = np.floor(t * SIDE_BINS).astype(np.int32)
    usable = ((0 <= bins) & (bins < SIDE_BINS)
              & (depth >= -3) & (depth < 0.4 * side_length))
    nearest = np.full(SIDE_BINS, 0.4 * side_length, dtype=np.float64)
    np.minimum.at(nearest, bins[usable], np.maximum(0, depth[usable]))
    smoothed = np.convolve(nearest, np.ones(5) / 5, mode="same")
    baseline = float(np.quantile(nearest[4:60], 0.2))
    peak_bin = int(np.argmax(smoothed[3:61]) + 3)
    excess = max(0.0, float(smoothed[peak_bin] - baseline))
    return excess / side_length, peak_bin, float(smoothed[peak_bin])


def _analyze_valid_image(crop: Image.Image, threshold: float) -> dict:
    foreground, segmentation = _foreground(crop.convert("RGB"))
    y, x = np.nonzero(foreground)
    x, y = x.astype(np.float32), y.astype(np.float32)
    rect = _minimum_rectangle(x, y)
    cosine, sine = rect["cosine"], rect["sine"]
    u = x * cosine + y * sine
    v = -x * sine + y * cosine
    u0, u1, v0, v1 = (rect[key] for key in ("u0", "u1", "v0", "v1"))
    side_u, side_v = u1 - u0, v1 - v0
    # The four sides include both middle-edge gaps and missing corners.
    profiles = (
        ((v - v0) / side_v, u - u0, side_v),
        ((v - v0) / side_v, u1 - u, side_v),
        ((u - u0) / side_u, v - v0, side_u),
        ((u - u0) / side_u, v1 - v, side_u),
    )
    side_results = [_side_profile(*profile) for profile in profiles]
    side = int(np.argmax([item[0] for item in side_results]))
    score, peak_bin, inward_depth = side_results[side]
    position = (peak_bin + 0.5) / SIDE_BINS
    if side == 0:
        expected_u, expected_v = u0, v0 + position * side_v
        observed_u, observed_v = expected_u + inward_depth, expected_v
    elif side == 1:
        expected_u, expected_v = u1, v0 + position * side_v
        observed_u, observed_v = expected_u - inward_depth, expected_v
    elif side == 2:
        expected_u, expected_v = u0 + position * side_u, v0
        observed_u, observed_v = expected_u, expected_v + inward_depth
    else:
        expected_u, expected_v = u0 + position * side_u, v1
        observed_u, observed_v = expected_u, expected_v - inward_depth

    def inverse(u_value: float, v_value: float) -> list[float]:
        return [round(u_value * cosine - v_value * sine, 1),
                round(u_value * sine + v_value * cosine, 1)]

    candidate = {
        "expected_edge_xy": inverse(expected_u, expected_v),
        "observed_inward_xy": inverse(observed_u, observed_v),
        "side_index": side,
        "side_fraction": round(position, 4),
        "inward_depth_px": round(inward_depth, 2),
    }
    is_candidate = score > threshold
    return {
        "status": "candidate" if is_candidate else "uncertain",
        "purpose": "provisional outer-contour diagnostic; not an EfficientAD verdict",
        "relative_depth_score": round(score, 4),
        "development_threshold": threshold,
        "confidence": "moderate" if is_candidate else "low",
        "confidence_is_calibrated_probability": False,
        "candidate": candidate if is_candidate else None,
        "segmentation": segmentation,
        "geometry": {"angle_mod_90_degrees": rect["angle_mod_90_degrees"],
                     "expected_corners_xy": rect["corners_xy"],
                     "side_lengths_px": rect["side_lengths_px"],
                     "per_side_relative_depth": [round(item[0], 4)
                                                 for item in side_results]},
        "validated_location": False,
        "location_accuracy_metric": None,
    }


def analyze_image(crop: Image.Image, threshold: float = DEPTH_THRESHOLD) -> dict:
    """Measure outline evidence, returning unavailable on a geometry failure.

    ``uncertain`` means only that this outline check found too little evidence;
    it must never be interpreted as an EfficientAD normal verdict.
    """
    if crop.size != (SIZE, SIZE):
        raise ValueError("expected a 256x256 crop")
    if not 0.0 < threshold < 0.4:
        raise ValueError("threshold must be between 0 and 0.4")
    try:
        return _analyze_valid_image(crop, threshold)
    except ValueError as error:
        return {"status": "unavailable", "reason": str(error),
                "purpose": "provisional outer-contour diagnostic; not an EfficientAD verdict",
                "candidate": None, "confidence": "none",
                "confidence_is_calibrated_probability": False,
                "validated_location": False, "location_accuracy_metric": None}


def analyze_crop(path: Path, output_dir: Path | None = None,
                 threshold: float = DEPTH_THRESHOLD) -> dict:
    with Image.open(path) as source:
        crop = source.convert("RGB")
    result = analyze_image(crop, threshold)
    result["crop_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    if output_dir is not None:
        if output_dir.exists():
            raise FileExistsError(output_dir)
        output_dir.mkdir(parents=True)
        if result["candidate"] is not None:
            preview = crop.copy()
            draw = ImageDraw.Draw(preview)
            corners = [tuple(point) for point in result["geometry"]["expected_corners_xy"]]
            draw.line(corners + [corners[0]], fill=(255, 220, 0), width=2)
            px, py = result["candidate"]["expected_edge_xy"]
            draw.ellipse((px - 6, py - 6, px + 6, py + 6),
                         outline=(255, 0, 0), width=3)
            preview.save(output_dir / "preview.png")
        (output_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("crop", type=Path, help="existing 256x256 cropped PNG")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--threshold", type=float, default=DEPTH_THRESHOLD,
                        help="development-only provisional cutoff")
    args = parser.parse_args()
    print(json.dumps(analyze_crop(args.crop, args.output_dir, args.threshold),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

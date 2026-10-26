"""Suggest an outer-edge location from a frozen EfficientAD fused map.

This is a display/diagnostic postprocessor, not a new defect decision.  It fits
the smallest rotated rectangle around the largest white foreground component
and searches the *expected* rectangle's inner edge band.  Missing white pixels
remain inside that expected shape, so a cut corner or a notch midway along an
edge can both be searched.  The geometry is intentionally fixed; it must not
be tuned against test defects or substituted for EfficientAD's full map/score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from src.tie_mount_crop import white_foreground_mask


SIZE = 256
EDGE_BAND_FRACTION = 0.18


def _largest_component(mask: np.ndarray) -> np.ndarray:
    """Keep one connected part rather than isolated bright background pixels."""
    visited = np.zeros(mask.shape, dtype=bool)
    best: list[tuple[int, int]] = []
    height, width = mask.shape
    for start_y, start_x in zip(*np.nonzero(mask)):
        sy, sx = int(start_y), int(start_x)
        if visited[sy, sx]:
            continue
        visited[sy, sx] = True
        queue = deque([(sy, sx)])
        component = []
        while queue:
            y, x = queue.popleft()
            component.append((y, x))
            for ny, nx in ((y - 1, x), (y + 1, x),
                           (y, x - 1), (y, x + 1)):
                if (0 <= ny < height and 0 <= nx < width
                        and mask[ny, nx] and not visited[ny, nx]):
                    visited[ny, nx] = True
                    queue.append((ny, nx))
        if len(component) > len(best):
            best = component
    result = np.zeros(mask.shape, dtype=bool)
    if best:
        yy, xx = np.array(best).T
        result[yy, xx] = True
    return result


def expected_edge_band(crop: Image.Image) -> tuple[np.ndarray, dict]:
    """Return a fixed band inside the expected square, including missing areas."""
    if crop.size != (SIZE, SIZE):
        raise ValueError("expected a 256x256 crop")
    foreground = _largest_component(white_foreground_mask(crop))
    count = int(foreground.sum())
    if not 2500 <= count <= int(0.75 * SIZE * SIZE):
        raise ValueError("white part was not isolated reliably")
    if (foreground[:2].any() or foreground[-2:].any()
            or foreground[:, :2].any() or foreground[:, -2:].any()):
        raise ValueError("part touches the crop boundary")

    y, x = np.nonzero(foreground)
    x, y = x.astype(np.float32), y.astype(np.float32)
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
    side_u, side_v = u1 - u0, v1 - v0
    if not (80 <= min(side_u, side_v) <= max(side_u, side_v) <= 250
            and max(side_u, side_v) / min(side_u, side_v) <= 1.35):
        raise ValueError("foreground does not fit a full square-like part")

    yy, xx = np.indices((SIZE, SIZE), dtype=np.float32)
    uu = xx * cosine + yy * sine
    vv = -xx * sine + yy * cosine
    inside = (u0 <= uu) & (uu <= u1) & (v0 <= vv) & (vv <= v1)
    distance_to_edge = np.minimum.reduce((uu - u0, u1 - uu,
                                          vv - v0, v1 - vv))
    band = inside & (distance_to_edge <= EDGE_BAND_FRACTION * min(side_u, side_v))
    if int(band.sum()) < 500:
        raise ValueError("expected edge band is empty or too small")

    corners = []
    for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1)):
        corners.append([round(u * cosine - v * sine, 2),
                        round(u * sine + v * cosine, 2)])
    if any(not (-2 <= px <= SIZE + 1 and -2 <= py <= SIZE + 1)
           for px, py in corners):
        raise ValueError("expected part extends beyond the crop")
    geometry = {
        "angle_mod_90_degrees": angle,
        "expected_corners_xy": corners,
        "side_lengths_px": [round(side_u, 2), round(side_v, 2)],
        "foreground_pixels": count,
        "edge_band_pixels": int(band.sum()),
        "edge_band_fraction_of_side": EDGE_BAND_FRACTION,
    }
    return band, geometry


def _peak(score_map: np.ndarray, mask: np.ndarray | None = None) -> dict:
    if mask is None:
        index = int(np.argmax(score_map))
    else:
        index = int(np.argmax(np.where(mask, score_map, -np.inf)))
    y, x = np.unravel_index(index, score_map.shape)
    return {"x": int(x), "y": int(y), "score": float(score_map[y, x])}


def localize(crop_path: Path, fused_map_path: Path, output_dir: Path) -> dict:
    """Write a reproducible candidate point, expected-band mask and preview."""
    if output_dir.exists():
        raise FileExistsError(f"choose a new output directory: {output_dir}")
    with Image.open(crop_path) as source:
        crop = source.convert("RGB")
    with Image.open(fused_map_path) as source:
        if source.format != "TIFF" or getattr(source, "n_frames", 1) != 1:
            raise ValueError("fused map must be a single-page TIFF")
        score_map = np.asarray(source).copy()
    if score_map.shape != (SIZE, SIZE) or not np.issubdtype(score_map.dtype, np.number):
        raise ValueError("fused map must be a numeric 256x256 TIFF")
    if not np.isfinite(score_map).all():
        raise ValueError("fused map contains nonfinite values")
    band, geometry = expected_edge_band(crop)
    raw = _peak(score_map)
    candidate = _peak(score_map, band)

    preview = crop.copy()
    draw = ImageDraw.Draw(preview)
    corners = [tuple(point) for point in geometry["expected_corners_xy"]]
    draw.line(corners + [corners[0]], fill=(255, 220, 0), width=2)
    x, y = raw["x"], raw["y"]
    draw.line((x - 6, y, x + 6, y), fill=(200, 0, 200), width=2)
    draw.line((x, y - 6, x, y + 6), fill=(200, 0, 200), width=2)
    x, y = candidate["x"], candidate["y"]
    draw.ellipse((x - 6, y - 6, x + 6, y + 6), outline=(255, 0, 0), width=3)

    result = {
        "schema_version": 1,
        "purpose": "candidate outer-edge localization, not a defect verdict",
        "crop_sha256": hashlib.sha256(crop_path.read_bytes()).hexdigest(),
        "fused_map_sha256": hashlib.sha256(fused_map_path.read_bytes()).hexdigest(),
        "raw_global_peak_xy_score": raw,
        "expected_edge_peak_xy_score": candidate,
        "raw_peak_in_expected_edge_band": bool(band[raw["y"], raw["x"]]),
        "geometry": geometry,
        "preview_legend": "yellow=expected outer rectangle, magenta=raw peak, red=edge candidate",
    }
    output_dir.mkdir(parents=True)
    preview.save(output_dir / "preview.png")
    Image.fromarray(np.uint8(band) * 255, mode="L").save(output_dir / "expected_edge_band.png")
    (output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("crop", type=Path, help="existing 256x256 cropped PNG")
    parser.add_argument("fused_map", type=Path, help="matching combined-map TIFF")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(localize(args.crop, args.fused_map, args.output_dir),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

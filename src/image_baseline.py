"""Fixed-camera pixel-template baseline; this is not a trained model."""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

from src.score_map import score_map_float


def load_gray(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L"), dtype=np.float32) / 255.0


def find_regions(mask: np.ndarray, min_area: int) -> tuple[np.ndarray, list[dict[str, int]]]:
    """Keep four-connected regions; boxes use exclusive right/bottom edges."""
    if min_area < 1:
        raise ValueError("min_area must be at least 1")
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    kept = np.zeros_like(mask, dtype=bool)
    regions = []
    for row, col in np.argwhere(mask):
        row, col = int(row), int(col)
        if visited[row, col]:
            continue
        visited[row, col] = True
        queue = deque([(row, col)])
        pixels = []
        while queue:
            y, x = queue.popleft()
            pixels.append((y, x))
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((ny, nx))
        if len(pixels) >= min_area:
            ys, xs = zip(*pixels)
            kept[ys, xs] = True
            regions.append({"area_pixels": len(pixels), "left": min(xs), "top": min(ys),
                            "right": max(xs) + 1, "bottom": max(ys) + 1})
    return kept, regions


def detect(reference: np.ndarray, target: np.ndarray, threshold: float = 0.25,
           min_area: int = 9) -> tuple[np.ndarray, np.ndarray, list[dict[str, int]]]:
    if reference.ndim != 2 or target.ndim != 2 or reference.shape != target.shape:
        raise ValueError("reference and target must be same-size grayscale images")
    if not 0 < threshold <= 1:
        raise ValueError("threshold must be in (0, 1]")
    if not np.isfinite(reference).all() or not np.isfinite(target).all():
        raise ValueError("images must contain only finite values")
    if np.any((reference < 0) | (reference > 1)) or np.any((target < 0) | (target > 1)):
        raise ValueError("image values must be normalized to [0, 1]")
    score = score_map_float(reference[None, :, :], target[None, :, :])
    mask, regions = find_regions(score >= threshold, min_area)
    return score, mask, regions


def run(reference_path: Path, target_path: Path, output_dir: Path,
        threshold: float = 0.25, min_area: int = 9) -> dict:
    reference = load_gray(reference_path)
    target = load_gray(target_path)
    score, mask, regions = detect(reference, target, threshold, min_area)
    output_dir.mkdir(parents=True, exist_ok=True)
    np.save(output_dir / "score.npy", score)
    Image.fromarray(np.uint8(np.clip(score, 0, 1) * 255), mode="L").save(output_dir / "score.png")
    Image.fromarray(np.uint8(mask) * 255, mode="L").save(output_dir / "mask.png")
    with Image.open(target_path) as image:
        overlay = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
    overlay[mask] = (255, 0, 0)
    Image.fromarray(overlay, mode="RGB").save(output_dir / "overlay.png")
    result = {
        "method": "fixed_camera_grayscale_pixel_template",
        "reference": str(reference_path), "target": str(target_path),
        "image_size": [int(target.shape[1]), int(target.shape[0])],
        "threshold_squared_normalized": threshold, "min_area_pixels": min_area,
        "verdict": "defect" if regions else "normal",
        "region_count": len(regions), "defect_pixels": int(mask.sum()),
        "regions": regions,
    }
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path, help="normal reference image")
    parser.add_argument("target", type=Path, help="image to inspect; same size and aligned")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.25)
    parser.add_argument("--min-area", type=int, default=9)
    args = parser.parse_args()
    print(json.dumps(run(args.reference, args.target, args.output_dir,
                         args.threshold, args.min_area), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

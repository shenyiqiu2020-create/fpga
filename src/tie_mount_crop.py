"""Locate and crop one white tie mount from an overhead photograph.

The current locator is a measured first step for the photographed green,
brown and wood backgrounds. It rejects ambiguous images instead of claiming
to support arbitrary backgrounds or camera angles.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


def _largest_component(mask: np.ndarray) -> tuple[int, int, int, int, int]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    best = (0, 0, 0, 0, 0)
    for start_y, start_x in zip(*np.nonzero(mask)):
        if visited[start_y, start_x]:
            continue
        queue = deque([(int(start_y), int(start_x))])
        visited[start_y, start_x] = True
        area = 0
        left = right = int(start_x)
        top = bottom = int(start_y)
        while queue:
            y, x = queue.popleft()
            area += 1
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if (0 <= ny < height and 0 <= nx < width
                        and mask[ny, nx] and not visited[ny, nx]):
                    visited[ny, nx] = True
                    queue.append((ny, nx))
        if area > best[0]:
            best = (area, left, top, right + 1, bottom + 1)
    return best


def locate_mount(image: Image.Image) -> tuple[int, int, int, int]:
    """Return a square crop in original coordinates, or reject the image."""
    original_width, original_height = image.size
    if min(image.size) < 128:
        raise ValueError("image is too small to locate the part")
    preview = image.copy()
    preview.thumbnail((512, 512), Image.Resampling.BILINEAR)
    pixels = np.asarray(preview.convert("RGB"), dtype=np.float32)
    height, width = pixels.shape[:2]
    edge = max(4, min(width, height) // 25)
    border = np.concatenate((pixels[:edge].reshape(-1, 3),
                             pixels[-edge:].reshape(-1, 3),
                             pixels[:, :edge].reshape(-1, 3),
                             pixels[:, -edge:].reshape(-1, 3)))
    background = np.median(border, axis=0)
    brightness = pixels.mean(axis=2)
    chroma = pixels.max(axis=2) - pixels.min(axis=2)
    distance = np.linalg.norm(pixels - background, axis=2)
    mask = ((brightness > max(130.0, float(background.mean()) + 15.0))
            & (chroma < 30.0) & (distance > 35.0))
    # A visible run of white at the frame edge means the contour may be cut off.
    # Check this before component search; otherwise a clipped close-up can pass.
    if any(np.count_nonzero(edge_pixels) >= 3 for edge_pixels in
           (mask[0], mask[-1], mask[:, 0], mask[:, -1])):
        raise ValueError("part touches the image boundary")
    area, left, top, right, bottom = _largest_component(mask)
    fraction = area / (width * height)
    bbox_width, bbox_height = right - left, bottom - top
    if not (0.01 <= fraction <= 0.6 and bbox_width >= 20 and bbox_height >= 20):
        raise ValueError("white part was not isolated from the background")
    aspect = bbox_width / bbox_height
    if not 0.55 <= aspect <= 1.8:
        raise ValueError("detected region does not resemble the square part")
    # A little context preserves the external contour, including a missing corner.
    scale_x, scale_y = original_width / width, original_height / height
    cx = (left + right) * scale_x / 2
    cy = (top + bottom) * scale_y / 2
    side = max(bbox_width * scale_x, bbox_height * scale_y) * 1.22
    # Keep all of a rotated part when the requested 22% context cannot fit in
    # the shorter frame dimension. The detected contour must still fit.
    side = min(int(np.ceil(side)), original_width, original_height)
    crop_left = round(cx - side / 2)
    crop_top = round(cy - side / 2)
    crop_left = max(0, min(original_width - side, crop_left))
    crop_top = max(0, min(original_height - side, crop_top))
    margin = max(1, round(side * 0.01))
    if not (crop_left + margin <= left * scale_x
            and right * scale_x <= crop_left + side - margin
            and crop_top + margin <= top * scale_y
            and bottom * scale_y <= crop_top + side - margin):
        raise ValueError("part is too close to the image boundary")
    return crop_left, crop_top, crop_left + side, crop_top + side


def crop_mount(path: Path, size: int = 256) -> tuple[Image.Image, dict]:
    if size <= 0:
        raise ValueError("size must be positive")
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    box = locate_mount(image)
    cropped = image.crop(box).resize((size, size), Image.Resampling.LANCZOS)
    return cropped, {"source": str(path), "source_size": list(image.size),
                     "crop_box": list(box), "output_size": [size, size]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--size", type=int, default=256)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise ValueError("output directory must be empty")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index, path in enumerate(args.images, 1):
        image, record = crop_mount(path, args.size)
        output = args.output_dir / f"{index:03d}_{path.stem}.png"
        image.save(output)
        record["output"] = str(output)
        records.append(record)
    (args.output_dir / "crops.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Cropped {len(records)} images into {args.output_dir}")


if __name__ == "__main__":
    main()

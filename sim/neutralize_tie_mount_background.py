"""Prepare a controlled EfficientAD input variant with a neutral background.

The same transform must be applied to training, validation, and test images.
The white mask is a limited candidate segmenter; the generated images are for
an exploratory comparison and do not establish arbitrary-background support.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from src.tie_mount_crop import white_foreground_mask


def prepare(class_root: Path, output_root: Path, background: int = 128) -> list[dict]:
    if not 0 <= background <= 255:
        raise ValueError("background must be an 8-bit intensity")
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("output root must be empty")
    files = sorted(class_root.glob("*/*/*.png"))
    if not files:
        raise ValueError("no prepared crop images found")
    records = []
    for path in files:
        with Image.open(path) as opened:
            image = opened.convert("RGB")
        if image.size != (256, 256):
            raise ValueError(f"expected 256x256 crop: {path}")
        mask = white_foreground_mask(image)
        fraction = float(mask.mean())
        if not 0.1 <= fraction <= 0.8:
            raise ValueError(f"ambiguous white mask: {path}: {fraction:.3f}")
        pixels = np.asarray(image)
        neutral = np.full_like(pixels, background)
        neutral[mask] = pixels[mask]
        relative = path.relative_to(class_root)
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(neutral).save(target)
        records.append({
            "source": str(path),
            "output": str(target),
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "white_mask_fraction": round(fraction, 4),
            "background_rgb": [background] * 3,
        })
    (output_root.parent / "neutral_background_manifest.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--background", type=int, default=128)
    args = parser.parse_args()
    records = prepare(args.class_root, args.output_root, args.background)
    print(f"Neutralized {len(records)} images into {args.output_root}")


if __name__ == "__main__":
    main()

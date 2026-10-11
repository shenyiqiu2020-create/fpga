"""Generate self-contained synthetic workpiece images for software smoke tests."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def generate(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    normal = np.full((128, 128), 255, dtype=np.uint8)
    normal[24:104, 24:104] = 40
    normal[45:57, 45:57] = 255
    normal[71:83, 71:83] = 255
    missing_corner = normal.copy()
    missing_corner[24:40, 24:40] = 255
    missing_hole = normal.copy()
    missing_hole[71:83, 71:83] = 40
    for name, image in (("normal", normal), ("missing_corner", missing_corner),
                        ("missing_hole", missing_hole)):
        Image.fromarray(image, mode="L").save(output_dir / f"{name}.png")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    generate(args.output_dir)
    print(f"Wrote synthetic images to {args.output_dir}")


if __name__ == "__main__":
    main()

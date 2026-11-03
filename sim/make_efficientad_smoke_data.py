"""Build a tiny artificial MVTec-style folder tree for pipeline smoke checks.

Images are copied from ``sim.make_demo_images``. Repeated normal images and
two invented defects make this unsuitable for training or accuracy claims.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from shutil import copyfile

from sim.make_demo_images import generate as make_demo_images


def generate(output_dir: Path) -> Path:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Output directory is not empty: {output_dir}")

    source_dir = output_dir / "source"
    make_demo_images(source_dir)
    category_dir = output_dir / "dataset" / "bottle"
    train_dir = category_dir / "train" / "good"
    good_dir = category_dir / "test" / "good"
    broken_dir = category_dir / "test" / "broken"
    for directory in (train_dir, good_dir, broken_dir):
        directory.mkdir(parents=True, exist_ok=True)

    normal = source_dir / "normal.png"
    for index in range(10):
        copyfile(normal, train_dir / f"normal_{index}.png")
    copyfile(normal, good_dir / "normal.png")
    copyfile(source_dir / "missing_corner.png", broken_dir / "corner.png")
    copyfile(source_dir / "missing_hole.png", broken_dir / "hole.png")
    return output_dir / "dataset"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    dataset_dir = generate(args.output_dir)
    print(f"Wrote artificial smoke data to {dataset_dir}")
    print("Do not use this data for training metrics or accuracy claims.")


if __name__ == "__main__":
    main()

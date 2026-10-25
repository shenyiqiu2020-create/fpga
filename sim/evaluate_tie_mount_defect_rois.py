"""Audit EfficientAD map peaks against manually reviewed visible-defect boxes.

The boxes are coarse regions in the 256x256 prepared crops, not pixel masks.
This is a post-hoc diagnostic on existing test images, not an unbiased
localization accuracy estimate or a replacement for EfficientAD.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image, ImageDraw


COMPONENTS = ("combined", "student_teacher", "autoencoder")
FIELDS = ("image", "object_group", "component", "peak_x", "peak_y",
          "global_max", "peak_in_roi", "roi_max", "roi_area_fraction")


def load_boxes(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("no defect regions supplied")
    seen = set()
    for row in rows:
        name = row["image"]
        if name in seen:
            raise ValueError(f"duplicate defect region: {name}")
        seen.add(name)
        box = tuple(int(row[field]) for field in ("x0", "y0", "x1", "y1"))
        if not (0 <= box[0] < box[2] <= 256 and
                0 <= box[1] < box[3] <= 256):
            raise ValueError(f"invalid 256x256 defect region: {name}: {box}")
        row["box"] = box
    return rows


def audit(class_root: Path, maps_root: Path, annotations: Path,
          output: Path, overlay_dir: Path | None = None,
          flat: bool = False) -> list[dict]:
    rows = []
    for annotation in load_boxes(annotations):
        name = annotation["image"]
        group = annotation["object_group"]
        if flat:
            if not name.startswith(f"{group}_"):
                raise ValueError(f"image and object group disagree: {name}, {group}")
            image_path = class_root / name
        else:
            if not name.endswith(f"_{group}.png"):
                raise ValueError(f"image and object group disagree: {name}, {group}")
            image_path = class_root / "test" / "corner_or_edge_loss" / name
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
        x0, y0, x1, y1 = annotation["box"]
        for component in COMPONENTS:
            if flat:
                map_path = maps_root / component / f"{Path(name).stem}.tiff"
            else:
                map_path = (maps_root / "test" / component /
                            "corner_or_edge_loss" / f"{Path(name).stem}.tiff")
            score_map = tifffile.imread(map_path)
            if score_map.shape != (256, 256) or not np.isfinite(score_map).all():
                raise ValueError(f"invalid score map: {map_path}")
            y, x = np.unravel_index(int(np.argmax(score_map)), score_map.shape)
            rows.append({
                "image": name,
                "object_group": group,
                "component": component,
                "peak_x": int(x),
                "peak_y": int(y),
                "global_max": float(score_map[y, x]),
                "peak_in_roi": x0 <= x < x1 and y0 <= y < y1,
                "roi_max": float(score_map[y0:y1, x0:x1].max()),
                "roi_area_fraction": round((x1 - x0) * (y1 - y0) / 256**2, 4),
            })
            if overlay_dir is not None and component == "combined":
                with Image.open(image_path) as source:
                    overlay = source.convert("RGB")
                draw = ImageDraw.Draw(overlay)
                draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline="yellow", width=2)
                draw.ellipse((x - 4, y - 4, x + 4, y + 4),
                             outline="red", width=2)
                overlay_dir.mkdir(parents=True, exist_ok=True)
                overlay.save(overlay_dir / name)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-root", type=Path, required=True)
    parser.add_argument("--maps-root", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overlay-dir", type=Path)
    parser.add_argument("--flat", action="store_true",
                        help="read flat image and map directories for frozen holdout inference")
    args = parser.parse_args()
    rows = audit(args.class_root, args.maps_root, args.annotations,
                 args.output, args.overlay_dir, args.flat)
    fused = [row for row in rows if row["component"] == "combined"]
    hits = sum(row["peak_in_roi"] for row in fused)
    print(f"Fused-map global peak in reviewed defect box: {hits}/{len(fused)} "
          f"images. Detail: {args.output}")


if __name__ == "__main__":
    main()

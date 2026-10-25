"""Prepare grouped tie-mount photos for the EfficientAD candidate loader.

Input CSV columns: file, object_group, split, label, background, angle, light.
Only the first four columns are required. ``object_group`` is a data-record
identifier for one physical part; nothing needs to be written on the part.
All output is local and should be placed under Git-ignored build/work/.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import tempfile
from pathlib import Path

from src.tie_mount_crop import crop_mount


REQUIRED = ("file", "object_group", "split", "label")
SPLITS = {"train", "validation", "test"}
IDENTIFIER = re.compile(r"^[a-zA-Z0-9_-]+$")


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or any(name not in reader.fieldnames for name in REQUIRED):
            raise ValueError(f"manifest needs columns: {', '.join(REQUIRED)}")
        rows = list(reader)
    if not rows:
        raise ValueError("manifest is empty")
    seen_files: set[Path] = set()
    groups: dict[str, tuple[str, str]] = {}
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        name, group = row["file"].strip(), row["object_group"].strip()
        split, label = row["split"].strip(), row["label"].strip()
        if not name or not IDENTIFIER.fullmatch(group) or not IDENTIFIER.fullmatch(label):
            raise ValueError("file, object_group and label must be nonempty; IDs use letters, digits, _ or -")
        if split not in SPLITS or (split != "test" and label != "good"):
            raise ValueError("train/validation only accept good photos; split must be train/validation/test")
        source = (path.parent / name).resolve()
        if not source.is_file() or source in seen_files:
            raise ValueError(f"missing or duplicate image: {source}")
        seen_files.add(source)
        previous = groups.setdefault(group, (split, label))
        if previous != (split, label):
            raise ValueError(f"physical part {group} crosses data splits or labels")
        row["file"] = str(source)
        row["object_group"] = group
        row["split"] = split
        row["label"] = label
        counts[(split, label)] = counts.get((split, label), 0) + 1
    for key in (("train", "good"), ("validation", "good"), ("test", "good")):
        if counts.get(key, 0) == 0:
            raise ValueError(f"missing required group: {key[0]}/{key[1]}")
    if not any(split == "test" and label != "good" for split, label in counts):
        raise ValueError("test needs at least one defective photo")
    return rows


def prepare(manifest: Path, output_dir: Path) -> dict:
    rows = read_manifest(manifest)
    if output_dir.exists():
        raise FileExistsError(f"choose a new output directory: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tie_mount_prepare_", dir=output_dir.parent) as temporary:
        staging = Path(temporary) / "dataset"
        class_root = staging / "tie_mount"
        records = []
        for index, row in enumerate(rows, 1):
            source = Path(row["file"])
            image, crop = crop_mount(source)
            target = class_root / row["split"] / row["label"] / f"{index:04d}_{row['object_group']}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(target)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            records.append({**row, "source_sha256": digest,
                            "output": str(target.relative_to(staging)),
                            "source_size": crop["source_size"],
                            "crop_box": crop["crop_box"]})
        (staging / "prepared_manifest.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        staging.rename(output_dir)
    return {"images": len(rows), "physical_parts": len({row["object_group"] for row in rows}),
            "class_root": str(output_dir / "tie_mount")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.manifest, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Freeze the 2026-10-26 photo groups before EfficientAD experiments.

Exact duplicate photos within one data role are kept only once; duplicates
between distinct training parts are allowed only when both are normal. Holdout
sources are indexed but kept out of training data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from PIL import Image

from sim.prepare_tie_mount_dataset import prepare


def group_plan(folder: str) -> tuple[str, str, str]:
    if folder.startswith("正常") or folder.startswith("正"):
        number = int(folder.removeprefix("正常").removeprefix("正"))
        if not 1 <= number <= 20:
            raise ValueError(f"unexpected normal folder: {folder}")
        if number in (5, 16):
            role = "development"
        elif number in (14, 15):
            role = "validation"
        elif number >= 17:
            role = "holdout"
        else:
            role = "train"
        return f"N{number:02d}", "good", role
    if folder.startswith("do"):
        number = int(folder[2:])
        if not 1 <= number <= 20:
            raise ValueError(f"unexpected defect folder: {folder}")
        # D04..D06 are earlier parts outside these user folders.
        group = f"D{number if number <= 3 else number + 3:02d}"
        role = "excluded_prior" if number <= 5 else ("development" if number <= 15 else "holdout")
        label = "internal_rib_loss" if number == 3 else "outer_edge_loss"
        return group, label, role
    raise ValueError(f"unexpected folder: {folder}")


def snapshot(source_root: Path, output_root: Path) -> dict:
    if output_root.exists():
        raise FileExistsError(output_root)
    folders = sorted((path for path in source_root.iterdir() if path.is_dir()),
                     key=lambda path: (not path.name.startswith("do"),
                                       int("".join(ch for ch in path.name if ch.isdigit()))))
    if len(folders) != 40:
        raise ValueError(f"expected 40 physical-part folders, found {len(folders)}")
    inventory: list[dict] = []
    hashes: dict[str, list[dict]] = defaultdict(list)
    for folder in folders:
        group, label, role = group_plan(folder.name)
        images = sorted(path for path in folder.iterdir() if path.is_file()
                        and path.suffix.lower() in (".jpg", ".jpeg", ".png"))
        if not images:
            raise ValueError(f"no photos in {folder}")
        for path in images:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with Image.open(path) as image:
                image.verify()
            row = {"folder": folder.name, "filename": path.name, "object_group": group,
                   "label": label, "role": role, "sha256": digest, "duplicate_of": ""}
            inventory.append(row)
            hashes[digest].append(row)
    duplicates = [[row["folder"] + "/" + row["filename"] for row in rows]
                  for rows in hashes.values() if len(rows) > 1]
    for rows in hashes.values():
        included = [row for row in rows if not row["role"].startswith("excluded")]
        if len(included) <= 1:
            continue
        assignments = {(row["role"], row["label"]) for row in included}
        if len(assignments) != 1 or (len({row["object_group"] for row in included}) > 1
                                     and assignments != {("train", "good")}):
            raise ValueError(f"duplicate crosses a protected split or label: {rows}")
        first = included[0]
        for row in included[1:]:
            row["duplicate_of"] = first["folder"] + "/" + first["filename"]

    output_root.mkdir(parents=True)
    with (output_root / "inventory.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=inventory[0])
        writer.writeheader()
        writer.writerows(inventory)
    development = []
    holdout = []
    for row in inventory:
        if row["role"].startswith("excluded") or row["duplicate_of"]:
            continue
        source = source_root / row["folder"] / row["filename"]
        if row["role"] == "holdout":
            holdout.append({**row, "file": str(source)})
        else:
            split = row["role"] if row["role"] in ("train", "validation") else "test"
            development.append({"file": str(source), "object_group": row["object_group"],
                                "split": split, "label": row["label"],
                                "source_sha256": row["sha256"]})
    for filename, rows in (("development.csv", development), ("holdout.csv", holdout)):
        with (output_root / filename).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
    result = {"source_root": str(source_root.resolve()), "photo_count": len(inventory),
              "development_photos": len(development), "holdout_photos": len(holdout),
              "duplicate_file_sets": duplicates,
              "skipped_duplicate_photos": sum(bool(row["duplicate_of"]) for row in inventory),
              "groups_by_role": {role: sorted({row["object_group"] for row in inventory
                                                if row["role"] == role})
                                 for role in sorted({row["role"] for row in inventory})}}
    (output_root / "snapshot.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["prepared"] = prepare(output_root / "development.csv", output_root / "development_prepared")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.source_root, args.output_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

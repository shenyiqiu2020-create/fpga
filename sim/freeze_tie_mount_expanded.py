"""Freeze the expanded tie-mount photos by physical part before experiments.

``freeze`` hashes and fully decodes the original photos. It writes an immutable
source inventory plus separate development and holdout manifests; it does not
crop or train. ``prepare`` is a later, explicit step that crops the two sets
into separate directories and records every accepted or rejected source photo.
Keep both output directories under Git-ignored build/work/.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable

from PIL import Image


EXPECTED_FOLDERS = tuple(f"do{i}" for i in range(1, 43)) + tuple(
    f"正常{i}" for i in range(1, 51)
)
EXPECTED_PHOTOS = 347
NORMAL_HOLDOUT = {42, 45, 46, 47}
NORMAL_DEVELOPMENT = {40, 41, 43, 44, 48, 49, 50}
# A copied photo was removed from each of these five directory pairs. The
# owner says the folders are different parts. Keep separate object_group IDs,
# while tying their split roles as a precaution against photo leakage.
# do30/do31 also look similar in the available views; their identity remains
# unverified, so this script does not silently merge their object IDs.
LEAKAGE_CLUSTERS = {
    "do30": "pair_do30_do31", "do31": "pair_do30_do31",
    "正常33": "pair_N33_N34", "正常34": "pair_N33_N34",
    "正常38": "pair_N38_N39", "正常39": "pair_N38_N39",
    "正常43": "pair_N43_N44", "正常44": "pair_N43_N44",
    "正常49": "pair_N49_N50", "正常50": "pair_N49_N50",
}
INVENTORY_FIELDS = ("file", "folder", "filename", "object_group", "leakage_cluster", "label",
                    "role", "sha256", "duplicate_of", "crop_status", "crop_error")
PREPARE_FIELDS = ("file", "object_group", "leakage_cluster", "split", "label", "source_sha256",
                  "folder", "filename")
AUDIT_FIELDS = INVENTORY_FIELDS + ("output", "source_size", "crop_box")


def _numbered_folder(folder: str) -> tuple[str, int]:
    if folder.startswith("正常") and folder[2:].isdigit():
        return "normal", int(folder[2:])
    if folder.startswith("do") and folder[2:].isdigit():
        return "defect", int(folder[2:])
    raise ValueError(f"unexpected folder: {folder}")


def group_plan(folder: str) -> tuple[str, str, str]:
    kind, number = _numbered_folder(folder)
    if kind == "normal":
        if not 1 <= number <= 50:
            raise ValueError(f"unexpected normal folder: {folder}")
        if number <= 34:
            role = "train"
        elif number <= 39:
            role = "validation"
        elif number in NORMAL_HOLDOUT:
            role = "holdout"
        elif number in NORMAL_DEVELOPMENT:
            role = "development"
        else:
            raise AssertionError(f"normal folder has no role: {folder}")
        return f"N{number:02d}", "good", role
    if not 1 <= number <= 42:
        raise ValueError(f"unexpected defect folder: {folder}")
    # D04..D06 were earlier chat-photo parts, not folders in this collection.
    group_number = number if number <= 3 else number + 3
    return f"D{group_number:02d}", "defect", ("development" if number <= 34 else "holdout")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_text(rows: list[dict], fields: tuple[str, ...]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _read_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(fields):
            raise ValueError(f"unexpected manifest columns: {path}")
        return list(reader)


def _split(role: str) -> str:
    return "test" if role == "development" else role


def scan_sources(source_root: Path, expected_folders: tuple[str, ...] = EXPECTED_FOLDERS,
                 expected_photos: int = EXPECTED_PHOTOS) -> list[dict[str, str]]:
    """Return a deterministic manifest after verifying every source image."""
    source_root = source_root.resolve()
    if not source_root.is_dir():
        raise ValueError(f"source directory does not exist: {source_root}")
    actual_folders = {path.name for path in source_root.iterdir() if path.is_dir()}
    if actual_folders != set(expected_folders):
        raise ValueError(f"folder mismatch: missing={sorted(set(expected_folders)-actual_folders)}, "
                         f"unexpected={sorted(actual_folders-set(expected_folders))}")
    rows: list[dict[str, str]] = []
    hashes: dict[str, list[dict[str, str]]] = defaultdict(list)
    for folder in expected_folders:
        directory = source_root / folder
        files = sorted(path for path in directory.iterdir() if path.is_file())
        if not files or any(path.suffix.lower() not in (".jpg", ".jpeg", ".png") for path in files):
            raise ValueError(f"empty folder or unexpected file type: {directory}")
        group, label, role = group_plan(folder)
        leakage_cluster = LEAKAGE_CLUSTERS.get(folder, group)
        for path in files:
            # load() forces pixel decoding; verify() alone can miss truncated JPEG data.
            with Image.open(path) as image:
                image.load()
                if image.width <= 0 or image.height <= 0:
                    raise ValueError(f"invalid image dimensions: {path}")
            digest = _sha256(path)
            row = {"file": str(path.resolve()), "folder": folder, "filename": path.name,
                   "object_group": group, "leakage_cluster": leakage_cluster,
                   "label": label, "role": role,
                   "sha256": digest, "duplicate_of": "", "crop_status": "pending",
                   "crop_error": ""}
            rows.append(row)
            hashes[digest].append(row)
    if len(rows) != expected_photos:
        raise ValueError(f"expected {expected_photos} photos, found {len(rows)}")
    for same_bytes in hashes.values():
        if len(same_bytes) < 2:
            continue
        assignments = {(row["leakage_cluster"], row["label"], row["role"])
                       for row in same_bytes}
        if len(assignments) != 1:
            raise ValueError(f"duplicate crosses a leakage cluster, label or role: {same_bytes}")
        first = same_bytes[0]
        for row in same_bytes[1:]:
            row["duplicate_of"] = f"{first['folder']}/{first['filename']}"
            row["crop_status"] = "skipped_duplicate"
    return rows


def freeze(source_root: Path, output_root: Path, tracked_inventory: Path,
           expected_folders: tuple[str, ...] = EXPECTED_FOLDERS,
           expected_photos: int = EXPECTED_PHOTOS) -> dict:
    """Write a source-only snapshot; refuse to overwrite a frozen inventory."""
    output_root = output_root.resolve()
    tracked_inventory = tracked_inventory.resolve()
    if output_root.exists():
        raise FileExistsError(output_root)
    rows = scan_sources(source_root, expected_folders, expected_photos)
    inventory_text = _csv_text(rows, INVENTORY_FIELDS)
    if tracked_inventory.exists() and tracked_inventory.read_text(encoding="utf-8") != inventory_text:
        raise ValueError(f"tracked inventory differs from current original photos: {tracked_inventory}")
    clusters: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        clusters[row["leakage_cluster"]].add(row["role"])
    if any(len(roles) != 1 for roles in clusters.values()):
        raise ValueError("leakage cluster crosses data roles")
    development = [
        {"file": row["file"], "object_group": row["object_group"],
         "leakage_cluster": row["leakage_cluster"],
         "split": _split(row["role"]), "label": row["label"],
         "source_sha256": row["sha256"], "folder": row["folder"],
         "filename": row["filename"]}
        for row in rows if row["role"] != "holdout" and not row["duplicate_of"]
    ]
    holdout = [
        {"file": row["file"], "object_group": row["object_group"],
         "leakage_cluster": row["leakage_cluster"],
         "split": "holdout", "label": row["label"],
         "source_sha256": row["sha256"], "folder": row["folder"],
         "filename": row["filename"]}
        for row in rows if row["role"] == "holdout" and not row["duplicate_of"]
    ]
    groups = {role: sorted({row["object_group"] for row in rows if row["role"] == role})
              for role in ("train", "validation", "development", "holdout")}
    summary = {"source_root": str(source_root.resolve()), "photos": len(rows),
               "unique_photos": len(rows) - sum(bool(row["duplicate_of"]) for row in rows),
               "development_photos": len(development), "holdout_photos": len(holdout),
               "groups_by_role": groups,
               "leakage_clusters_by_role": {
                   role: sorted({row["leakage_cluster"] for row in rows if row["role"] == role})
                   for role in groups},
               "photos_by_role": dict(sorted(Counter(row["role"] for row in rows).items())),
               "duplicate_photos": [f"{row['folder']}/{row['filename']}" for row in rows
                                    if row["duplicate_of"]]}
    output_root.mkdir(parents=True)
    (output_root / "inventory.csv").write_text(inventory_text, encoding="utf-8")
    (output_root / "development.csv").write_text(_csv_text(development, PREPARE_FIELDS),
                                                   encoding="utf-8")
    (output_root / "holdout.csv").write_text(_csv_text(holdout, PREPARE_FIELDS),
                                               encoding="utf-8")
    (output_root / "snapshot.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not tracked_inventory.exists():
        tracked_inventory.parent.mkdir(parents=True, exist_ok=True)
        tracked_inventory.write_text(inventory_text, encoding="utf-8")
    return summary


def prepare_frozen(snapshot_root: Path, development_output: Path, holdout_output: Path,
                   cropper: Callable | None = None) -> dict:
    """Crop explicitly after freezing; keep blind holdout outside trainer test/."""
    snapshot_root = snapshot_root.resolve()
    development_output = development_output.resolve()
    holdout_output = holdout_output.resolve()
    if development_output == holdout_output or development_output.exists() or holdout_output.exists():
        raise FileExistsError("choose distinct, unused development and holdout output directories")
    rows = _read_csv(snapshot_root / "inventory.csv", INVENTORY_FIELDS)
    if not rows:
        raise ValueError("frozen inventory is empty")
    if cropper is None:
        from src.tie_mount_crop import crop_mount
        cropper = crop_mount
    development_output.parent.mkdir(parents=True, exist_ok=True)
    holdout_output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tie_mount_dev_", dir=development_output.parent) as dev_tmp, \
         tempfile.TemporaryDirectory(prefix="tie_mount_holdout_", dir=holdout_output.parent) as hold_tmp:
        dev_stage, hold_stage = Path(dev_tmp) / "dataset", Path(hold_tmp) / "dataset"
        dev_stage.mkdir()
        hold_stage.mkdir()
        audit: list[dict] = []
        accepted = Counter()
        indices = Counter()
        for row in rows:
            source = Path(row["file"])
            if not source.is_file() or _sha256(source) != row["sha256"]:
                raise ValueError(f"original photo changed after freeze: {source}")
            record = {**row, "output": "", "source_size": "", "crop_box": ""}
            if row["duplicate_of"]:
                record["crop_status"] = "skipped_duplicate"
                audit.append(record)
                continue
            is_holdout = row["role"] == "holdout"
            indices["holdout" if is_holdout else "development"] += 1
            filename = f"{indices['holdout' if is_holdout else 'development']:04d}_{row['object_group']}.png"
            if is_holdout:
                target = hold_stage / "crops" / filename
            else:
                target = dev_stage / "tie_mount" / _split(row["role"]) / row["label"] / filename
            try:
                image, crop = cropper(source, size=256)
            except ValueError as error:
                record["crop_status"] = "rejected"
                record["crop_error"] = str(error)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                image.save(target)
                record["crop_status"] = "accepted"
                record["crop_error"] = ""
                record["output"] = str(target.relative_to(hold_stage if is_holdout else dev_stage))
                record["source_size"] = json.dumps(crop["source_size"])
                record["crop_box"] = json.dumps(crop["crop_box"])
                accepted[row["role"]] += 1
            audit.append(record)
        for role in ("train", "validation", "development", "holdout"):
            if accepted[role] == 0:
                raise ValueError(f"no accepted photos for {role}")
        dev_audit = [row for row in audit if row["role"] != "holdout"]
        hold_audit = [row for row in audit if row["role"] == "holdout"]
        (dev_stage / "source_map.csv").write_text(_csv_text(dev_audit, AUDIT_FIELDS), encoding="utf-8")
        (hold_stage / "source_map.csv").write_text(_csv_text(hold_audit, AUDIT_FIELDS), encoding="utf-8")
        result = {"accepted_by_role": dict(sorted(accepted.items())),
                  "rejected": [f"{row['folder']}/{row['filename']}: {row['crop_error']}"
                               for row in audit if row["crop_status"] == "rejected"],
                  "skipped_duplicate_photos": sum(row["crop_status"] == "skipped_duplicate"
                                                  for row in audit),
                  "development_class_root": str(development_output / "tie_mount"),
                  "holdout_crops": str(holdout_output / "crops")}
        (dev_stage / "preparation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        dev_stage.rename(development_output)
        hold_stage.rename(holdout_output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze_cmd = commands.add_parser("freeze", help="hash originals and freeze roles without cropping")
    freeze_cmd.add_argument("--source-root", required=True, type=Path)
    freeze_cmd.add_argument("--output-root", required=True, type=Path)
    freeze_cmd.add_argument("--tracked-inventory", required=True, type=Path)
    prepare_cmd = commands.add_parser("prepare", help="crop later into separate development and holdout outputs")
    prepare_cmd.add_argument("--snapshot-root", required=True, type=Path)
    prepare_cmd.add_argument("--development-output", required=True, type=Path)
    prepare_cmd.add_argument("--holdout-output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        result = freeze(args.source_root, args.output_root, args.tracked_inventory)
    else:
        result = prepare_frozen(args.snapshot_root, args.development_output, args.holdout_output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

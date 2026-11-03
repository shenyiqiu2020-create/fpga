"""Two-route experimental outline classifier for visible missing material.

Route 1 uses a strict GrabCut contour and may recrop the original photo wider.
Only when that route cannot measure a trustworthy contour, route 2 uses a
separately trained relaxed-border GrabCut forest. Both forests are fitted and
cross-validated by leakage_cluster; EfficientAD remains intact and separate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from sim.train_tie_mount_shape_rf import CV, OUT_OF_SCOPE, PARAMS, THRESHOLD, UNCERTAIN_INTERVAL
from src.tie_mount_shape_rf import (FEATURE_NAMES, MODEL_FORMAT, SEGMENTATION_SPEC,
                                    ShapeUnavailable, classify_photo_cascade,
                                    export_forest, extract_relaxed_with_fallback,
                                    extract_strict_with_relocation, probability)
from src.tie_mount_relocate import PAD_FRACTION

PIPELINE_FORMAT = "tie_mount_shape_cascade_v2"
RELOCATION_SPEC = {"method": "tinted_white_original_with_background_border",
                   "pad_fraction_of_source_width": PAD_FRACTION,
                   "trigger": "strict primary and wider original crop both fail"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(source_map: Path, root: Path, expected_roles: set[str], source_name: str) -> tuple[list[dict], list[dict]]:
    with source_map.open(encoding="utf-8", newline="") as handle:
        source_rows = [r for r in csv.DictReader(handle) if r["output"]]
    if not source_rows or any(r["role"] not in expected_roles for r in source_rows):
        raise ValueError(f"unexpected roles in {source_name} source map")
    root = root.resolve()
    rows = []
    out_of_scope = []
    for row in source_rows:
        crop = (root / row["output"]).resolve()
        if not crop.is_relative_to(root) or not crop.is_file():
            raise ValueError(f"missing/outside frozen crop: {row['output']}")
        if row["object_group"] in OUT_OF_SCOPE:
            out_of_scope.append({"source": source_name, "output": row["output"],
                                 "reason": OUT_OF_SCOPE[row["object_group"]]})
            continue
        if row["label"] not in {"good", "defect"}:
            raise ValueError(f"invalid label: {row['label']}")
        rows.append({**row, "_crop": crop, "_source_name": source_name})
    return rows, out_of_scope


def extract_rows(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    strict = np.full((len(rows), len(FEATURE_NAMES)), np.nan)
    relaxed = np.full_like(strict, np.nan)
    strict_ok = np.zeros(len(rows), dtype=bool)
    relaxed_ok = np.zeros(len(rows), dtype=bool)
    qualities = []
    for index, row in enumerate(rows):
        with Image.open(row["_crop"]) as source:
            image = source.convert("RGB")
        photo = Path(row["file"])
        if not photo.is_file() or sha256(photo) != row["sha256"]:
            raise ValueError(f"original photo changed since frozen source map: {row['output']}")
        box = tuple(json.loads(row["crop_box"]))
        strict_quality = None
        relaxed_quality = None
        strict_error = ""
        relaxed_error = ""
        try:
            vector, strict_quality = extract_strict_with_relocation(image, photo, box, row["sha256"])
            strict[index] = vector
            strict_ok[index] = True
        except (OSError, ShapeUnavailable) as exc:
            strict_error = str(exc)
        # The two routes measure identical pixels when the original crop passes
        # strict quality checks; reuse the exact vector in that common case.
        if strict_quality is not None and strict_quality["crop_variant"] == "frozen_primary":
            relaxed[index] = strict[index]
            relaxed_ok[index] = True
            relaxed_quality = {**strict_quality, "crop_variant": "frozen_primary_relaxed"}
        else:
            try:
                vector, relaxed_quality = extract_relaxed_with_fallback(image, photo, box, row["sha256"])
                relaxed[index] = vector
                relaxed_ok[index] = True
            except (OSError, ShapeUnavailable) as exc:
                relaxed_error = str(exc)
        qualities.append({"strict_variant": strict_quality["crop_variant"] if strict_quality else "",
                          "relaxed_variant": relaxed_quality["crop_variant"] if relaxed_quality else "",
                          "strict_error": strict_error, "relaxed_error": relaxed_error})
    return strict, relaxed, strict_ok, relaxed_ok, qualities


def input_set_sha256(rows: list[dict]) -> str:
    """Bind the source rows to the exact prepared crop bytes used for fitting."""
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: (item["_source_name"], item["output"])):
        digest.update(row["_source_name"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(row["output"].replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(row["sha256"].encode("ascii"))
        digest.update(b"\0")
        digest.update(sha256(row["_crop"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def confusion(y: np.ndarray, p: np.ndarray) -> dict:
    valid = np.isfinite(p)
    verdict = p[valid] >= THRESHOLD
    truth = y[valid]
    tn = int(np.sum((truth == 0) & ~verdict))
    fp = int(np.sum((truth == 0) & verdict))
    fn = int(np.sum((truth == 1) & ~verdict))
    tp = int(np.sum((truth == 1) & verdict))
    return {"TN": tn, "FP": fp, "FN": fn, "TP": tp,
            "unavailable": int((~valid).sum()),
            "balanced_accuracy_on_measurable": ((tn / (tn + fp) + tp / (tp + fn)) / 2)
            if (tn + fp) and (tp + fn) else None}


def cv_probabilities(y: np.ndarray, groups: np.ndarray, strict: np.ndarray,
                     relaxed: np.ndarray, strict_ok: np.ndarray,
                     relaxed_ok: np.ndarray, seed: int) -> np.ndarray:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import StratifiedGroupKFold

    p = np.full(len(y), np.nan)
    folds = StratifiedGroupKFold(n_splits=CV["n_splits"], shuffle=True, random_state=seed)
    for train_index, test_index in folds.split(relaxed, y, groups):
        if set(groups[train_index]) & set(groups[test_index]):
            raise AssertionError("leakage cluster crossed a CV fold")
        strict_train = train_index[strict_ok[train_index]]
        strict_test = test_index[strict_ok[test_index]]
        primary = RandomForestClassifier(**PARAMS)
        primary.fit(strict[strict_train], y[strict_train])
        p[strict_test] = primary.predict_proba(strict[strict_test])[:, 1]
        relaxed_train = train_index[relaxed_ok[train_index]]
        relaxed_test = test_index[(~strict_ok[test_index]) & relaxed_ok[test_index]]
        if len(relaxed_test):
            secondary = RandomForestClassifier(**PARAMS)
            secondary.fit(relaxed[relaxed_train], y[relaxed_train])
            p[relaxed_test] = secondary.predict_proba(relaxed[relaxed_test])[:, 1]
    return p


def metrics(rows: list[dict], p: np.ndarray, strict_ok: np.ndarray,
            qualities: list[dict]) -> dict:
    y = np.asarray([int(r["label"] == "defect") for r in rows])
    secondary = ~strict_ok
    relocated = np.asarray([q["strict_variant"] == "relocated_padded_original" for q in qualities])
    part = defaultdict(list)
    for index, row in enumerate(rows):
        part[row["object_group"]].append(index)
    part_truth = np.asarray([y[indexes[0]] for indexes in part.values()])
    part_prob = np.asarray([np.mean(p[indexes]) if np.isfinite(p[indexes]).all() else np.nan
                            for indexes in part.values()])
    low_probability_confidence = (p >= UNCERTAIN_INTERVAL[0]) & (p <= UNCERTAIN_INTERVAL[1])
    return {"photo": confusion(y, p),
            "strict_route": confusion(y[strict_ok], p[strict_ok]),
            "relocated_strict_subset": confusion(y[relocated], p[relocated]),
            "secondary_route": confusion(y[secondary], p[secondary]),
            "part_mean_probability": confusion(part_truth, part_prob),
            "photo_review_recommended": int(np.sum(secondary | relocated | low_probability_confidence)),
            "relocated_photos": int(relocated.sum()),
            "secondary_photos": int(secondary.sum()),
            "objects": len(part)}


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_predictions(path: Path, rows: list[dict], p: np.ndarray, strict_ok: np.ndarray,
                      qualities: list[dict]) -> None:
    output = []
    for index, (row, quality) in enumerate(zip(rows, qualities)):
        value = p[index]
        route = ("strict_relocated" if quality["strict_variant"] == "relocated_padded_original" else
                 "strict" if strict_ok[index] else "relaxed_border_contact")
        uncertain = np.isfinite(value) and UNCERTAIN_INTERVAL[0] <= value <= UNCERTAIN_INTERVAL[1]
        output.append({"source": row["_source_name"], "output": row["output"],
                       "object_group": row["object_group"],
                       "leakage_cluster": row["leakage_cluster"], "label": row["label"],
                       "defect_probability": repr(float(value)) if np.isfinite(value) else "",
                       "predicted_label": "defect" if value >= THRESHOLD else "good" if np.isfinite(value) else "unavailable",
                       "route": route if np.isfinite(value) else "unavailable",
                       "low_quality": bool(route != "strict" or uncertain),
                       "review_recommended": bool(route != "strict" or uncertain),
                       "crop_variant": quality["strict_variant"] if strict_ok[index] else quality["relaxed_variant"]})
    write_csv(path, output, ["source", "output", "object_group", "leakage_cluster", "label",
                             "defect_probability", "predicted_label", "route", "low_quality",
                             "review_recommended", "crop_variant"])


def export_pair(output_dir: Path, rows: list[dict], strict: np.ndarray, relaxed: np.ndarray,
                strict_ok: np.ndarray, relaxed_ok: np.ndarray, metadata: dict) -> dict:
    from sklearn.ensemble import RandomForestClassifier
    import sklearn
    import cv2

    if output_dir.exists():
        raise FileExistsError("choose a fresh cascade artifact directory")
    y = np.asarray([int(r["label"] == "defect") for r in rows])
    primary = RandomForestClassifier(**PARAMS)
    secondary = RandomForestClassifier(**PARAMS)
    primary.fit(strict[strict_ok], y[strict_ok])
    secondary.fit(relaxed[relaxed_ok], y[relaxed_ok])
    output_dir.mkdir(parents=True)
    first = output_dir / "strict_model.json"
    second = output_dir / "relaxed_model.json"
    first.write_text(json.dumps(export_forest(primary), separators=(",", ":")), encoding="utf-8")
    second.write_text(json.dumps(export_forest(secondary), separators=(",", ":")), encoding="utf-8")
    manifest = {"format": MODEL_FORMAT, "pipeline_format": PIPELINE_FORMAT,
                "strict_model_sha256": sha256(first), "relaxed_model_sha256": sha256(second),
                "feature_names": list(FEATURE_NAMES), "segmentation": SEGMENTATION_SPEC,
                "relocation": RELOCATION_SPEC,
                "threshold": THRESHOLD, "low_confidence_interval": list(UNCERTAIN_INTERVAL),
                "rf_parameters": {k: v for k, v in PARAMS.items() if k != "n_jobs"},
                "training_counts": {"in_scope": len(rows),
                                    "strict_measurable": int(strict_ok.sum()),
                                    "strict_relocated": sum(q["strict_variant"] == "relocated_padded_original" for q in metadata["_qualities"]),
                                    "secondary_needed": int((~strict_ok).sum()),
                                    "secondary_measurable": int(((~strict_ok) & relaxed_ok).sum()),
                                    "truly_unavailable": int((~strict_ok & ~relaxed_ok).sum())},
                "capture_assumptions": "part centered in 256x256 crop; solid contrasting background; 9px border background and 36x36 center part",
                "runtime": {"sklearn": sklearn.__version__, "opencv": cv2.__version__,
                            "numpy": np.__version__},
                **{k: v for k, v in metadata.items() if k != "_qualities"}}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    return manifest


def load_pair(strict_model: Path, relaxed_model: Path, manifest_path: Path) -> tuple[dict, dict, dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("format") != MODEL_FORMAT or manifest.get("pipeline_format") != PIPELINE_FORMAT or
            manifest.get("segmentation") != SEGMENTATION_SPEC or
            manifest.get("relocation") != RELOCATION_SPEC or
            manifest.get("feature_names") != list(FEATURE_NAMES)):
        raise ValueError("unsupported shape cascade manifest")
    if (sha256(strict_model) != manifest.get("strict_model_sha256") or
            sha256(relaxed_model) != manifest.get("relaxed_model_sha256")):
        raise ValueError("shape cascade model hash mismatch")
    first = json.loads(strict_model.read_text(encoding="utf-8"))
    second = json.loads(relaxed_model.read_text(encoding="utf-8"))
    for model in (first, second):
        if (model.get("format") != MODEL_FORMAT or model.get("segmentation") != SEGMENTATION_SPEC or
                model.get("feature_names") != list(FEATURE_NAMES)):
            raise ValueError("shape cascade feature schema mismatch")
    return first, second, manifest


def evaluate_pair(rows: list[dict], strict: np.ndarray, relaxed: np.ndarray,
                  strict_ok: np.ndarray, relaxed_ok: np.ndarray,
                  first: dict, second: dict) -> np.ndarray:
    p = np.full(len(rows), np.nan)
    for index in range(len(rows)):
        if strict_ok[index]:
            p[index] = probability(strict[index], first)
        elif relaxed_ok[index]:
            p[index] = probability(relaxed[index], second)
    return p


def run_development(source_map: Path, root: Path, output_dir: Path) -> dict:
    rows, excluded = read_rows(source_map, root, {"train", "validation", "development"}, "development")
    strict, relaxed, strict_ok, relaxed_ok, qualities = extract_rows(rows)
    if not relaxed_ok.all():
        raise ValueError("a current development photo has no second-route feature")
    y = np.asarray([int(r["label"] == "defect") for r in rows])
    groups = np.asarray([r["leakage_cluster"] for r in rows])
    by_seed = {}
    chosen = None
    for seed in (11, 42, 2026):
        p = cv_probabilities(y, groups, strict, relaxed, strict_ok, relaxed_ok, seed)
        by_seed[str(seed)] = metrics(rows, p, strict_ok, qualities)
        if seed == 42:
            chosen = p
    metadata = {"artifact_id": "shape_cascade_development_v2",
                "status": "experimental_development_only",
                "source_map_sha256": sha256(source_map),
                "training_input_set_sha256": input_set_sha256(rows),
                "out_of_scope_photos": len(excluded),
                "training_leakage_clusters": sorted(set(groups)),
                "_qualities": qualities,
                "grouped_oof": {"independent": False,
                                "note": "internal grouped CV during method development",
                                "by_seed": by_seed}}
    manifest = export_pair(output_dir, rows, strict, relaxed, strict_ok, relaxed_ok, metadata)
    write_predictions(output_dir / "oof_predictions.csv", rows, chosen, strict_ok, qualities)
    write_csv(output_dir / "out_of_scope.csv", excluded, ["source", "output", "reason"])
    return manifest


def run_diagnostic(source_map: Path, root: Path, strict_model: Path,
                   relaxed_model: Path, manifest_path: Path, output_dir: Path) -> dict:
    first, second, model_manifest = load_pair(strict_model, relaxed_model, manifest_path)
    if model_manifest["status"] != "experimental_development_only":
        raise ValueError("diagnostic requires frozen development-only model")
    rows, excluded = read_rows(source_map, root, {"holdout"}, "seen_holdout")
    if excluded:
        raise ValueError("unexpected out-of-scope old holdout photo")
    if set(r["leakage_cluster"] for r in rows) & set(model_manifest["training_leakage_clusters"]):
        raise ValueError("old holdout overlaps development leakage groups")
    strict, relaxed, strict_ok, relaxed_ok, qualities = extract_rows(rows)
    p = evaluate_pair(rows, strict, relaxed, strict_ok, relaxed_ok, first, second)
    if output_dir.exists():
        raise FileExistsError("choose a new diagnostic directory")
    output_dir.mkdir(parents=True)
    write_predictions(output_dir / "predictions.csv", rows, p, strict_ok, qualities)
    report = {"kind": "already_seen_holdout_cascade_diagnostic", "independent": False,
              "reason": "the method was developed after earlier inspection of these photos",
              "source_map_sha256": sha256(source_map),
              "development_strict_model_sha256": model_manifest["strict_model_sha256"],
              "development_relaxed_model_sha256": model_manifest["relaxed_model_sha256"],
              "metrics": metrics(rows, p, strict_ok, qualities)}
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    return report


def run_full_current(development_map: Path, development_root: Path,
                     seen_map: Path, seen_root: Path, diagnostic_report: Path,
                     output_dir: Path) -> dict:
    report = json.loads(diagnostic_report.read_text(encoding="utf-8"))
    if (report.get("kind") != "already_seen_holdout_cascade_diagnostic" or
            report.get("independent") is not False or
            report.get("source_map_sha256") != sha256(seen_map)):
        raise ValueError("refit requires the frozen old-holdout cascade diagnostic")
    development, excluded = read_rows(development_map, development_root,
                                      {"train", "validation", "development"}, "development")
    seen, other_excluded = read_rows(seen_map, seen_root, {"holdout"}, "seen_holdout")
    if other_excluded or set(r["leakage_cluster"] for r in development) & set(r["leakage_cluster"] for r in seen):
        raise ValueError("seen holdout overlaps development groups or scope")
    rows = development + seen
    strict, relaxed, strict_ok, relaxed_ok, qualities = extract_rows(rows)
    if not relaxed_ok.all():
        raise ValueError("a current photo has no second-route feature")
    y = np.asarray([int(r["label"] == "defect") for r in rows])
    groups = np.asarray([r["leakage_cluster"] for r in rows])
    retrospective = {}
    chosen = None
    for seed in (11, 42, 2026):
        p = cv_probabilities(y, groups, strict, relaxed, strict_ok, relaxed_ok, seed)
        retrospective[str(seed)] = metrics(rows, p, strict_ok, qualities)
        if seed == 42:
            chosen = p
    metadata = {"artifact_id": "shape_cascade_full_current_v2",
                "status": "experimental_full_current_no_independent_test",
                "training_input_set_sha256": input_set_sha256(rows),
                "training_source_map_sha256": {"development": sha256(development_map),
                                               "seen_holdout": sha256(seen_map)},
                "prior_diagnostic_report_sha256": sha256(diagnostic_report),
                "seen_holdout_in_training": True,
                "out_of_scope_photos": len(excluded),
                "training_leakage_clusters": sorted(set(groups)),
                "_qualities": qualities,
                "retrospective_grouped_oof": {"independent": False,
                    "note": "method was selected after inspecting old holdout; new parts needed for validation",
                    "by_seed": retrospective}}
    manifest = export_pair(output_dir, rows, strict, relaxed, strict_ok, relaxed_ok, metadata)
    write_predictions(output_dir / "retrospective_oof_predictions.csv", rows, chosen, strict_ok, qualities)
    write_csv(output_dir / "out_of_scope.csv", excluded, ["source", "output", "reason"])
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    dev = commands.add_parser("train-development")
    dev.add_argument("--source-map", type=Path, required=True)
    dev.add_argument("--prepared-root", type=Path, required=True)
    dev.add_argument("--output-dir", type=Path, required=True)
    diagnostic = commands.add_parser("diagnostic")
    diagnostic.add_argument("--source-map", type=Path, required=True)
    diagnostic.add_argument("--prepared-root", type=Path, required=True)
    diagnostic.add_argument("--strict-model", type=Path, required=True)
    diagnostic.add_argument("--relaxed-model", type=Path, required=True)
    diagnostic.add_argument("--manifest", type=Path, required=True)
    diagnostic.add_argument("--output-dir", type=Path, required=True)
    full = commands.add_parser("refit-current")
    full.add_argument("--development-map", type=Path, required=True)
    full.add_argument("--development-root", type=Path, required=True)
    full.add_argument("--seen-holdout-map", type=Path, required=True)
    full.add_argument("--seen-holdout-root", type=Path, required=True)
    full.add_argument("--diagnostic-report", type=Path, required=True)
    full.add_argument("--output-dir", type=Path, required=True)
    infer = commands.add_parser("infer-photo")
    infer.add_argument("--photo", type=Path, required=True)
    infer.add_argument("--strict-model", type=Path, required=True)
    infer.add_argument("--relaxed-model", type=Path, required=True)
    infer.add_argument("--manifest", type=Path, required=True)
    infer.add_argument("--used-crop-output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "train-development":
        result = run_development(args.source_map, args.prepared_root, args.output_dir)
    elif args.command == "diagnostic":
        result = run_diagnostic(args.source_map, args.prepared_root, args.strict_model,
                                args.relaxed_model, args.manifest, args.output_dir)
    elif args.command == "refit-current":
        result = run_full_current(args.development_map, args.development_root,
                                  args.seen_holdout_map, args.seen_holdout_root,
                                  args.diagnostic_report, args.output_dir)
    else:
        first, second, manifest = load_pair(args.strict_model, args.relaxed_model, args.manifest)
        result = classify_photo_cascade(args.photo, first, second, manifest["threshold"],
                                        tuple(manifest["low_confidence_interval"]),
                                        args.used_crop_output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

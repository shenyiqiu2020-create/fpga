"""Group-CV training and safe inference for the experimental outline RF.

The frozen holdout is intentionally outside this CLI. Use only the prepared
development source_map for training and model selection.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from src.tie_mount_shape_rf import (FEATURE_NAMES, MODEL_FORMAT, SEGMENTATION_SPEC, ShapeUnavailable,
                                    classify_crop, classify_photo, export_forest, extract_with_fallback,
                                    load_forest, probability)

PARAMS = {"n_estimators": 400, "max_depth": 5, "min_samples_leaf": 3,
          "class_weight": "balanced", "random_state": 42, "n_jobs": -1}
CV = {"n_splits": 5, "shuffle": True, "random_state": 42,
      "group_column": "leakage_cluster"}
THRESHOLD = 0.5
UNCERTAIN_INTERVAL = (0.4, 0.6)
OUT_OF_SCOPE = {"D03": "internal rib break, not visible outer-edge material loss"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _crop_digest(rows: list[dict], root: Path) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda entry: entry["output"]):
        crop = (root / row["output"]).resolve()
        if not crop.is_relative_to(root.resolve()):
            raise ValueError("crop path outside prepared root")
        digest.update(row["output"].replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha(crop).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _confusion(y: np.ndarray, p: np.ndarray) -> dict:
    pred = p >= THRESHOLD
    tp = int(np.sum((y == 1) & pred))
    tn = int(np.sum((y == 0) & ~pred))
    fp = int(np.sum((y == 0) & pred))
    fn = int(np.sum((y == 1) & ~pred))
    return {"TN": tn, "FP": fp, "FN": fn, "TP": tp,
            "balanced_accuracy": (tp / (tp + fn) + tn / (tn + fp)) / 2}


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _uncertain_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    decisive = (p < UNCERTAIN_INTERVAL[0]) | (p > UNCERTAIN_INTERVAL[1])
    return {"decisive": int(decisive.sum()), "uncertain": int((~decisive).sum()),
            "decisive_coverage": float(decisive.mean()),
            "decisive_confusion": _confusion(y[decisive], p[decisive])
            if len(set(y[decisive])) == 2 else None}


def train(source_map: Path, prepared_root: Path, output_dir: Path) -> dict:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedGroupKFold
    import sklearn

    if output_dir.exists():
        raise FileExistsError("choose a new output directory; model experiments are immutable")
    with source_map.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or any(r["role"] == "holdout" for r in rows):
        raise ValueError("training source_map must contain only development-side rows")
    if any(r["role"] not in {"train", "validation", "development"} for r in rows):
        raise ValueError("unexpected source role")
    base = prepared_root.resolve()
    accepted = []
    unavailable = []
    out_of_scope = []
    for row in rows:
        if not row["output"]:
            continue  # frozen duplicate; never use it twice
        if row["object_group"] in OUT_OF_SCOPE:
            out_of_scope.append({"output": row["output"], "object_group": row["object_group"],
                                 "reason": OUT_OF_SCOPE[row["object_group"]]})
            continue
        crop = (base / row["output"]).resolve()
        if not crop.is_relative_to(base) or not crop.is_file():
            raise ValueError(f"missing/outside prepared crop: {row['output']}")
        try:
            with Image.open(crop) as image:
                vector, quality = extract_with_fallback(image.convert("RGB"),
                                                        Path(row["file"]),
                                                        tuple(json.loads(row["crop_box"])),
                                                        row["sha256"])
        except (OSError, ShapeUnavailable) as exc:
            unavailable.append({"output": row["output"], "object_group": row["object_group"],
                                "label": row["label"], "reason": str(exc)})
            continue
        if row["label"] not in {"good", "defect"}:
            raise ValueError("unexpected label")
        accepted.append((row, vector, quality))
    if len(accepted) < 10:
        raise ValueError("too few measurable development crops")
    X = np.stack([v for _, v, _ in accepted])
    y = np.asarray([int(row["label"] == "defect") for row, _, _ in accepted])
    groups = np.asarray([row["leakage_cluster"] for row, _, _ in accepted])
    if len(set(groups)) < CV["n_splits"]:
        raise ValueError("too few independent leakage groups")
    label_by_group = defaultdict(set)
    for label, group in zip(y, groups):
        label_by_group[group].add(int(label))
    if any(len(labels) != 1 for labels in label_by_group.values()):
        raise ValueError("a leakage cluster has conflicting labels")
    part = defaultdict(list)
    for index, (row, _, _) in enumerate(accepted):
        part[row["object_group"]].append(index)
    part_labels = np.asarray([y[indices[0]] for indices in part.values()])
    by_seed = {}
    chosen_probabilities = None
    chosen_folds = None
    for seed in (11, 42, 2026):
        folds = StratifiedGroupKFold(n_splits=CV["n_splits"], shuffle=True,
                                     random_state=seed)
        probabilities = np.full(len(y), np.nan)
        fold_ids = np.full(len(y), -1)
        for fold_id, (train_index, test_index) in enumerate(folds.split(X, y, groups)):
            if set(groups[train_index]) & set(groups[test_index]):
                raise AssertionError("leakage cluster crossed a CV fold")
            model = RandomForestClassifier(**PARAMS)
            model.fit(X[train_index], y[train_index])
            probabilities[test_index] = model.predict_proba(X[test_index])[:, 1]
            fold_ids[test_index] = fold_id
        if not np.isfinite(probabilities).all() or (fold_ids < 0).any():
            raise AssertionError("incomplete OOF predictions")
        part_prob = np.asarray([np.mean(probabilities[indices]) for indices in part.values()])
        by_seed[str(seed)] = {
            "photo": _confusion(y, probabilities),
            "photo_auc": float(roc_auc_score(y, probabilities)),
            "part_mean_probability": _confusion(part_labels, part_prob),
            "part_auc": float(roc_auc_score(part_labels, part_prob)),
            "photo_uncertain_0p4_to_0p6": _uncertain_metrics(y, probabilities),
            "part_uncertain_0p4_to_0p6": _uncertain_metrics(part_labels, part_prob),
            "part_errors": [group for (group, indices), p in zip(part.items(), part_prob)
                            if (p >= THRESHOLD) != bool(y[indices[0]])],
        }
        if seed == CV["random_state"]:
            chosen_probabilities, chosen_folds = probabilities, fold_ids
    probabilities, fold_ids = chosen_probabilities, chosen_folds
    metrics = {"by_seed": by_seed, "measurable": len(accepted),
               "primary_measurable": sum(q["crop_variant"] == "frozen_primary" for _, _, q in accepted),
               "wider_fallback_measurable": sum(q["crop_variant"] == "wider_original_photo" for _, _, q in accepted),
               "unavailable": len(unavailable), "out_of_scope": len(out_of_scope),
               "in_scope_coverage": len(accepted) / (len(accepted) + len(unavailable)),
               "unavailable_by_label": {label: sum(r["label"] == label for r in unavailable)
                                        for label in ("good", "defect")},
               "leakage_clusters": len(set(groups)), "object_groups": len(part)}
    model = RandomForestClassifier(**PARAMS)
    model.fit(X, y)
    forest = export_forest(model)
    output_dir.mkdir(parents=True)
    model_path = output_dir / "shape_rf_model.json"
    model_path.write_text(json.dumps(forest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    oof = []
    for index, (row, _, quality) in enumerate(accepted):
        oof.append({"output": row["output"], "object_group": row["object_group"],
                    "leakage_cluster": row["leakage_cluster"], "role": row["role"],
                    "label": row["label"], "fold": int(fold_ids[index]),
                    "defect_probability": repr(float(probabilities[index])),
                    "verdict": "defect" if probabilities[index] >= THRESHOLD else "good",
                    "cautious_verdict": ("uncertain" if UNCERTAIN_INTERVAL[0] <= probabilities[index] <= UNCERTAIN_INTERVAL[1]
                                         else ("defect" if probabilities[index] >= THRESHOLD else "good")),
                    "mask": quality["mask"], "crop_variant": quality["crop_variant"]})
    _write_csv(output_dir / "oof_predictions.csv", oof,
               ["output", "object_group", "leakage_cluster", "role", "label",
                "fold", "defect_probability", "verdict", "cautious_verdict", "mask", "crop_variant"])
    _write_csv(output_dir / "unavailable.csv", unavailable,
               ["output", "object_group", "label", "reason"])
    _write_csv(output_dir / "out_of_scope.csv", out_of_scope,
               ["output", "object_group", "reason"])
    manifest = {"format": MODEL_FORMAT, "status": "experimental_not_validated_for_deployment",
                "task": "visible_outer_edge_material_loss",
                "segmentation": SEGMENTATION_SPEC,
                "capture_assumptions": "white part centered in 256x256 crop; 9px image border is background; center 36x36 is part; solid contrasting background",
                "source_map_sha256": _sha(source_map), "model_sha256": _sha(model_path),
                "accepted_crop_set_sha256": _crop_digest([r for r, _, _ in accepted], base),
                "training_leakage_clusters": sorted(set(groups)),
                "frozen_unique_photos": sum(bool(r["output"]) for r in rows),
                "feature_names": list(FEATURE_NAMES), "threshold": THRESHOLD,
                "uncertain_interval": list(UNCERTAIN_INTERVAL),
                "out_of_scope_groups": OUT_OF_SCOPE,
                "rf_parameters": {k: v for k, v in PARAMS.items() if k != "n_jobs"},
                "cross_validation": CV, "metrics": metrics,
                "runtime": {"sklearn": sklearn.__version__, "opencv": cv2.__version__,
                            "numpy": np.__version__},
                "caution": "OOF estimates on existing physical parts are exploratory; test on new parts and lighting before promotion."}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def evaluate_seen_holdout(source_map: Path, prepared_root: Path, model_path: Path,
                          manifest_path: Path, output_dir: Path) -> dict:
    """Diagnostic only: this set was seen during development of the method."""
    if output_dir.exists():
        raise FileExistsError("choose a new diagnostic output directory")
    forest, manifest = load_forest(model_path, manifest_path)
    if manifest.get("status") != "experimental_not_validated_for_deployment":
        raise ValueError("evaluation requires the development-only candidate model")
    with source_map.open(encoding="utf-8", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r["output"]]
    if not rows or any(r["role"] != "holdout" for r in rows):
        raise ValueError("diagnostic source_map must contain only old holdout photos")
    if set(r["leakage_cluster"] for r in rows) & set(manifest["training_leakage_clusters"]):
        raise ValueError("evaluation leakage group intersects model training")
    root = prepared_root.resolve()
    predictions = []
    for row in rows:
        crop = (root / row["output"]).resolve()
        if not crop.is_relative_to(root) or not crop.is_file():
            raise ValueError(f"missing/outside old holdout crop: {row['output']}")
        try:
            with Image.open(crop) as image:
                vector, quality = extract_with_fallback(image.convert("RGB"), Path(row["file"]),
                                                        tuple(json.loads(row["crop_box"])), row["sha256"])
            p = probability(vector, forest)
            outcome = {"verdict": "defect" if p >= manifest["threshold"] else "good",
                       "defect_probability": p, "quality": quality}
        except (OSError, ShapeUnavailable) as exc:
            outcome = {"verdict": "unavailable", "reason": str(exc)}
        p = outcome.get("defect_probability")
        cautious = ("unavailable" if p is None else
                    "uncertain" if UNCERTAIN_INTERVAL[0] <= p <= UNCERTAIN_INTERVAL[1] else
                    outcome["verdict"])
        predictions.append({"output": row["output"], "object_group": row["object_group"],
                            "label": row["label"], "crop_sha256": _sha(crop),
                            "defect_probability": "" if p is None else repr(p),
                            "verdict": outcome["verdict"], "cautious_verdict": cautious,
                            "crop_variant": outcome.get("quality", {}).get("crop_variant", ""),
                            "reason": outcome.get("reason", "")})
    measurable = [r for r in predictions if r["defect_probability"]]
    y = np.asarray([int(r["label"] == "defect") for r in measurable])
    p = np.asarray([float(r["defect_probability"]) for r in measurable])
    part = defaultdict(list)
    for row in measurable:
        part[row["object_group"]].append(row)
    part_y = np.asarray([int(group_rows[0]["label"] == "defect") for group_rows in part.values()])
    part_p = np.asarray([np.mean([float(r["defect_probability"]) for r in group_rows])
                         for group_rows in part.values()])
    metrics = {"total": len(rows), "measurable": len(measurable),
               "wider_fallback_measurable": sum(r["crop_variant"] == "wider_original_photo" for r in measurable),
               "unavailable": len(rows) - len(measurable),
               "photo": _confusion(y, p),
               "photo_uncertain_0p4_to_0p6": _uncertain_metrics(y, p),
               "part_mean_probability": _confusion(part_y, part_p),
               "part_uncertain_0p4_to_0p6": _uncertain_metrics(part_y, part_p),
               "measurable_parts": len(part),
               "unavailable_parts": len({r["object_group"] for r in rows} - set(part))}
    output_dir.mkdir(parents=True)
    _write_csv(output_dir / "diagnostic_predictions.csv", predictions,
               ["output", "object_group", "label", "crop_sha256", "defect_probability",
                "verdict", "cautious_verdict", "crop_variant", "reason"])
    report = {"kind": "already_seen_holdout_diagnostic", "independent": False,
              "reason": "the method was selected after earlier inspection of these photos",
              "source_map_sha256": _sha(source_map),
              "crop_set_sha256": _crop_digest(rows, root),
              "development_model_sha256": manifest["model_sha256"],
              "metrics": metrics}
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                             encoding="utf-8")
    return report


def refit_current(development_map: Path, development_root: Path,
                  seen_holdout_map: Path, seen_holdout_root: Path,
                  exploratory_report: Path, output_dir: Path) -> dict:
    """Use every measurable current photo; leave future new parts for testing."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import StratifiedGroupKFold
    import sklearn

    if output_dir.exists():
        raise FileExistsError("choose a new full-current artifact directory")
    report = json.loads(exploratory_report.read_text(encoding="utf-8"))
    if report.get("kind") != "already_seen_holdout_diagnostic" or report.get("independent") is not False:
        raise ValueError("refit requires the prior diagnostic report")
    if report.get("source_map_sha256") != _sha(seen_holdout_map):
        raise ValueError("seen holdout source_map changed after diagnostic")
    sources = (("development", development_map, development_root.resolve()),
               ("seen_holdout", seen_holdout_map, seen_holdout_root.resolve()))
    accepted = []
    unavailable = []
    out_of_scope = []
    all_groups = set()
    development_groups = set()
    input_info = []
    for source_name, source_map, root in sources:
        with source_map.open(encoding="utf-8", newline="") as handle:
            rows = [r for r in csv.DictReader(handle) if r["output"]]
        expected_roles = {"train", "validation", "development"} if source_name == "development" else {"holdout"}
        if not rows or any(r["role"] not in expected_roles for r in rows):
            raise ValueError(f"unexpected roles in {source_name} source_map")
        input_info.append({"source": source_name, "source_map_sha256": _sha(source_map),
                           "all_crop_set_sha256": _crop_digest(rows, root),
                           "frozen_unique_photos": len(rows)})
        for row in rows:
            group = row["leakage_cluster"]
            if source_name == "seen_holdout" and group in development_groups:
                raise ValueError("seen holdout leakage cluster intersects development")
            all_groups.add(group)
            if source_name == "development":
                development_groups.add(group)
            if row["object_group"] in OUT_OF_SCOPE:
                out_of_scope.append({"source": source_name, "output": row["output"],
                                     "reason": OUT_OF_SCOPE[row["object_group"]]})
                continue
            crop = (root / row["output"]).resolve()
            if not crop.is_relative_to(root) or not crop.is_file():
                raise ValueError(f"missing/outside crop: {row['output']}")
            try:
                with Image.open(crop) as image:
                    vector, quality = extract_with_fallback(image.convert("RGB"),
                                                            Path(row["file"]),
                                                            tuple(json.loads(row["crop_box"])),
                                                            row["sha256"])
            except (OSError, ShapeUnavailable) as exc:
                unavailable.append({"source": source_name, "output": row["output"],
                                    "label": row["label"], "reason": str(exc)})
                continue
            accepted.append((source_name, row, vector, quality))
    X = np.stack([vector for _, _, vector, _ in accepted])
    y = np.asarray([int(row["label"] == "defect") for _, row, _, _ in accepted])
    groups = np.asarray([row["leakage_cluster"] for _, row, _, _ in accepted])
    part = defaultdict(list)
    for index, (_, row, _, _) in enumerate(accepted):
        part[row["object_group"]].append(index)
    part_labels = np.asarray([y[indices[0]] for indices in part.values()])
    retrospective = {}
    chosen_retrospective_ps = None
    for seed in (11, 42, 2026):
        ps = np.full(len(y), np.nan)
        folds = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
        for train_index, test_index in folds.split(X, y, groups):
            if set(groups[train_index]) & set(groups[test_index]):
                raise AssertionError("leakage cluster crossed retrospective CV fold")
            cv_model = RandomForestClassifier(**PARAMS)
            cv_model.fit(X[train_index], y[train_index])
            ps[test_index] = cv_model.predict_proba(X[test_index])[:, 1]
        if not np.isfinite(ps).all():
            raise AssertionError("incomplete retrospective CV predictions")
        part_ps = np.asarray([np.mean(ps[indices]) for indices in part.values()])
        retrospective[str(seed)] = {"photo": _confusion(y, ps),
                                    "part_mean_probability": _confusion(part_labels, part_ps),
                                    "photo_uncertain_0p4_to_0p6": _uncertain_metrics(y, ps),
                                    "part_uncertain_0p4_to_0p6": _uncertain_metrics(part_labels, part_ps)}
        if seed == 42:
            chosen_retrospective_ps = ps.copy()
    model = RandomForestClassifier(**PARAMS)
    model.fit(X, y)
    output_dir.mkdir(parents=True)
    model_path = output_dir / "shape_rf_model.json"
    model_path.write_text(json.dumps(export_forest(model), ensure_ascii=False,
                                     separators=(",", ":")), encoding="utf-8")
    _write_csv(output_dir / "unavailable.csv", unavailable,
               ["source", "output", "label", "reason"])
    _write_csv(output_dir / "out_of_scope.csv", out_of_scope,
               ["source", "output", "reason"])
    retrospective_rows = []
    for index, (source_name, row, _, quality) in enumerate(accepted):
        p = float(chosen_retrospective_ps[index])
        retrospective_rows.append({"source": source_name, "output": row["output"],
                                   "object_group": row["object_group"],
                                   "leakage_cluster": row["leakage_cluster"],
                                   "label": row["label"],
                                   "defect_probability": repr(p),
                                   "verdict": "defect" if p >= THRESHOLD else "good",
                                   "cautious_verdict": "uncertain" if UNCERTAIN_INTERVAL[0] <= p <= UNCERTAIN_INTERVAL[1] else
                                   ("defect" if p >= THRESHOLD else "good"),
                                   "crop_variant": quality["crop_variant"]})
    _write_csv(output_dir / "retrospective_oof_predictions.csv", retrospective_rows,
               ["source", "output", "object_group", "leakage_cluster", "label",
                "defect_probability", "verdict", "cautious_verdict", "crop_variant"])
    manifest = {"format": MODEL_FORMAT, "artifact_id": "shape_rf_grabcut_full_current_v1",
                "status": "experimental_full_current_refit_no_independent_test",
                "task": "visible_outer_edge_material_loss",
                "segmentation": SEGMENTATION_SPEC,
                "capture_assumptions": "white part centered in 256x256 crop; 9px image border is background; center 36x36 is part; solid contrasting background",
                "model_sha256": _sha(model_path), "feature_names": list(FEATURE_NAMES),
                "training_inputs": input_info,
                "prior_diagnostic_report_sha256": _sha(exploratory_report),
                "seen_holdout_in_training": True,
                "training_leakage_clusters": sorted(all_groups),
                "rf_parameters": {k: v for k, v in PARAMS.items() if k != "n_jobs"},
                "threshold": THRESHOLD, "uncertain_interval": list(UNCERTAIN_INTERVAL),
                "training_counts": {"measurable": len(accepted),
                                    "primary_measurable": sum(q["crop_variant"] == "frozen_primary" for _, _, _, q in accepted),
                                    "wider_fallback_measurable": sum(q["crop_variant"] == "wider_original_photo" for _, _, _, q in accepted),
                                    "unavailable": len(unavailable),
                                    "out_of_scope": len(out_of_scope)},
                "retrospective_internal_cv": {"independent": False,
                    "reason": "algorithm and hyperparameters were selected after inspecting the old holdout",
                    "group_column": "leakage_cluster", "by_seed": retrospective},
                "runtime": {"sklearn": sklearn.__version__, "opencv": cv2.__version__,
                            "numpy": np.__version__},
                "caution": "All current photos, including the previously seen holdout, are training data. Evaluate only on newly photographed physical parts."}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fitting = commands.add_parser("train", help="fit on frozen development crops only")
    fitting.add_argument("--source-map", required=True, type=Path)
    fitting.add_argument("--prepared-root", required=True, type=Path)
    fitting.add_argument("--output-dir", required=True, type=Path)
    diagnostic = commands.add_parser("diagnostic", help="one exploratory evaluation on previously seen old holdout")
    diagnostic.add_argument("--source-map", required=True, type=Path)
    diagnostic.add_argument("--prepared-root", required=True, type=Path)
    diagnostic.add_argument("--model-json", required=True, type=Path)
    diagnostic.add_argument("--manifest", required=True, type=Path)
    diagnostic.add_argument("--output-dir", required=True, type=Path)
    refit = commands.add_parser("refit-current", help="fit candidate on all measurable already-seen photos")
    refit.add_argument("--development-map", required=True, type=Path)
    refit.add_argument("--development-root", required=True, type=Path)
    refit.add_argument("--seen-holdout-map", required=True, type=Path)
    refit.add_argument("--seen-holdout-root", required=True, type=Path)
    refit.add_argument("--exploratory-report", required=True, type=Path)
    refit.add_argument("--output-dir", required=True, type=Path)
    infer = commands.add_parser("infer", help="classify one already cropped 256x256 photo")
    infer.add_argument("--crop", required=True, type=Path)
    infer.add_argument("--model-json", required=True, type=Path)
    infer.add_argument("--manifest", required=True, type=Path)
    original = commands.add_parser("infer-photo", help="crop an original photo and apply wider fallback if needed")
    original.add_argument("--photo", required=True, type=Path)
    original.add_argument("--used-crop-output", required=True, type=Path)
    original.add_argument("--model-json", required=True, type=Path)
    original.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "train":
        print(json.dumps(train(args.source_map, args.prepared_root, args.output_dir),
                         ensure_ascii=False, indent=2))
    elif args.command == "diagnostic":
        print(json.dumps(evaluate_seen_holdout(args.source_map, args.prepared_root,
                                               args.model_json, args.manifest, args.output_dir),
                         ensure_ascii=False, indent=2))
    elif args.command == "refit-current":
        print(json.dumps(refit_current(args.development_map, args.development_root,
                                       args.seen_holdout_map, args.seen_holdout_root,
                                       args.exploratory_report, args.output_dir),
                         ensure_ascii=False, indent=2))
    elif args.command == "infer-photo":
        forest, manifest = load_forest(args.model_json, args.manifest)
        print(json.dumps(classify_photo(args.photo, forest, manifest["threshold"],
                                        tuple(manifest["uncertain_interval"]),
                                        args.used_crop_output),
                         ensure_ascii=False, indent=2))
    else:
        forest, manifest = load_forest(args.model_json, args.manifest)
        print(json.dumps(classify_crop(args.crop, forest, manifest["threshold"],
                                       tuple(manifest["uncertain_interval"])),
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

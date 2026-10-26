"""Lighting-aware silhouette features for an experimental missing-material check.

This is an auxiliary candidate, not a replacement for full EfficientAD. The
foreground mask is only calibrated for the current white part on contrasting
backgrounds. A failed silhouette must remain ``unavailable``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from src.tie_mount_crop import crop_mount
from src.tie_mount_relocate import relocate_photo

MODEL_FORMAT = "tie_mount_shape_rf_grabcut_v1"
SEGMENTATION_SPEC = {
    "method": "lab_initialized_grabcut",
    "border_background_pixels": 9,
    "center_foreground_square_pixels": 36,
    "probable_foreground_lab_distance": 15,
    "probable_foreground_luminance_margin": 7,
    "iterations": 3,
    "rng_seed": 42,
    "minimum_center_border_lab_distance": 10,
    "morphological_close_kernel": 5,
    "fallback_wider_crop_factor": 1.30,
}
FEATURE_NAMES = (
    "rect_fill", "solidity", "perimeter_ratio", "polygon_vertices_2pct",
    "polygon_vertices_4pct", "hull_vertices_2pct", "aspect_ratio",
    "area_fraction", "raw_mask_fraction", "polygon_vertices_1pct",
    "perimeter_sqrt_area", "sqrt_solidity", "convexity_defect_count",
    "convexity_depth_1", "convexity_depth_2", "convexity_depth_3",
    "convexity_depth_4", "deep_defects_4pct", "deep_defects_8pct",
)


class ShapeUnavailable(ValueError):
    """The part silhouette cannot be measured safely."""


def _grabcut_foreground(image: Image.Image) -> tuple[np.ndarray, float]:
    """Separate a centered part from its border using image-specific Lab cues.

    The center-seed and border assumptions are part of the capture protocol.
    This routine has no class labels or learned color thresholds.
    """
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    margin = 9
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    border = np.concatenate((lab[:margin].reshape(-1, 3),
                             lab[-margin:].reshape(-1, 3),
                             lab[:, :margin].reshape(-1, 3),
                             lab[:, -margin:].reshape(-1, 3)))
    background = np.median(border, axis=0)
    center = np.median(lab[height // 2 - 18:height // 2 + 18,
                           width // 2 - 18:width // 2 + 18].reshape(-1, 3), axis=0)
    contrast = float(np.linalg.norm(center - background))
    if contrast < 10:
        raise ShapeUnavailable("center and background have insufficient color contrast")
    distance = np.linalg.norm(lab - background, axis=2)
    brighter = lab[:, :, 0] > background[0] + 7
    state = np.full((height, width), cv2.GC_PR_BGD, dtype=np.uint8)
    state[(distance > 15) & brighter] = cv2.GC_PR_FGD
    state[:margin] = state[-margin:] = cv2.GC_BGD
    state[:, :margin] = state[:, -margin:] = cv2.GC_BGD
    state[height // 2 - 18:height // 2 + 18,
          width // 2 - 18:width // 2 + 18] = cv2.GC_FGD
    background_model = np.zeros((1, 65), np.float64)
    foreground_model = np.zeros((1, 65), np.float64)
    cv2.setRNGSeed(42)
    try:
        cv2.grabCut(rgb, state, None, background_model, foreground_model,
                    3, cv2.GC_INIT_WITH_MASK)
    except cv2.error as exc:
        raise ShapeUnavailable("foreground segmentation failed") from exc
    return (state == cv2.GC_FGD) | (state == cv2.GC_PR_FGD), contrast


def extract_features(image: Image.Image,
                     require_border_margin: bool = True) -> tuple[np.ndarray, dict[str, float | str]]:
    """Measure the largest white-part outer contour in a 256-pixel crop.

    The broad quality bounds were fixed before looking at the held-out photos.
    They reject empty, clipped, or wildly implausible masks, not hard examples.
    """
    if image.size != (256, 256):
        raise ShapeUnavailable("expected a 256x256 cropped RGB image")
    candidate, contrast = _grabcut_foreground(image)
    raw_fraction = float(candidate.mean())
    if not 0.02 <= raw_fraction <= 0.8:
        raise ShapeUnavailable("foreground mask area is implausible")
    mask = (candidate.astype(np.uint8) * 255)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ShapeUnavailable("no part contour")
    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    if area < 500 or not 0.02 <= area / 65536 <= 0.8:
        raise ShapeUnavailable("part contour area is implausible")
    x, y, w, h = cv2.boundingRect(contour)
    border_contact = x <= 9 or y <= 9 or x + w >= 247 or y + h >= 247
    if require_border_margin and border_contact:
        raise ShapeUnavailable("part contour touches crop boundary")
    if cv2.pointPolygonTest(contour, (128, 128), False) < 0:
        raise ShapeUnavailable("foreground contour does not contain center seed")
    hull = cv2.convexHull(contour)
    hull_indices = cv2.convexHull(contour, returnPoints=False)
    rect = cv2.minAreaRect(contour)
    rw, rh = (float(v) for v in rect[1])
    if min(rw, rh) <= 1 or not 0.45 <= max(rw, rh) / min(rw, rh) <= 2.2:
        raise ShapeUnavailable("part outline aspect ratio is implausible")
    perimeter = float(cv2.arcLength(contour, True))
    hull_area = max(1.0, float(cv2.contourArea(hull)))
    defects = cv2.convexityDefects(contour, hull_indices) if len(hull_indices) >= 4 else None
    depths = (sorted((float(row[3]) / 256 / np.sqrt(area) for row in defects[:, 0]),
                     reverse=True) if defects is not None else [])
    depths = (depths + [0.0] * 8)[:8]
    result = np.asarray((
        area / (rw * rh), area / hull_area, perimeter / (2 * (rw + rh)),
        len(cv2.approxPolyDP(contour, .02 * perimeter, True)),
        len(cv2.approxPolyDP(contour, .04 * perimeter, True)),
        len(cv2.approxPolyDP(hull, .02 * cv2.arcLength(hull, True), True)),
        max(rw, rh) / min(rw, rh), area / 65536, raw_fraction,
        len(cv2.approxPolyDP(contour, .01 * perimeter, True)),
        perimeter / np.sqrt(area), np.sqrt(area / hull_area),
        len(defects) if defects is not None else 0,
        *depths[:4], sum(d > .04 for d in depths), sum(d > .08 for d in depths),
    ), dtype=np.float64)
    if result.shape != (len(FEATURE_NAMES),) or not np.isfinite(result).all():
        raise ShapeUnavailable("nonfinite shape features")
    return result, {"mask": "grabcut_lab_center_border",
                    "center_border_lab_contrast": contrast,
                    "raw_mask_fraction": raw_fraction,
                    "contour_area_fraction": area / 65536,
                    "border_contact": bool(border_contact)}


def wider_crop_with_box(photo_path: Path, original_box: tuple[int, int, int, int]) -> tuple[Image.Image, list[float]]:
    """Reframe a failed crop from the original EXIF-oriented photo."""
    with Image.open(photo_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    left, top, right, bottom = original_box
    if (left < 0 or top < 0 or right > image.width or bottom > image.height or
            right <= left or bottom <= top or right - left != bottom - top):
        raise ShapeUnavailable("invalid original crop box")
    center_x, center_y = (left + right) / 2, (top + bottom) / 2
    side = min((right - left) * 1.30, image.width, image.height)
    x0 = max(0.0, min(image.width - side, center_x - side / 2))
    y0 = max(0.0, min(image.height - side, center_y - side / 2))
    box = [x0, y0, x0 + side, y0 + side]
    return image.crop(tuple(box)).resize((256, 256), Image.Resampling.LANCZOS), box


def wider_crop(photo_path: Path, original_box: tuple[int, int, int, int]) -> Image.Image:
    return wider_crop_with_box(photo_path, original_box)[0]


def extract_with_fallback(crop: Image.Image, source_photo: Path,
                          crop_box: tuple[int, int, int, int],
                          expected_source_sha256: str | None = None) -> tuple[np.ndarray, dict]:
    """Try the frozen crop first, then a wider original-photo view if needed."""
    try:
        vector, quality = extract_features(crop)
        return vector, {**quality, "crop_variant": "frozen_primary",
                        "crop_box_original_xyxy": list(crop_box)}
    except ShapeUnavailable as primary_error:
        if expected_source_sha256 is not None:
            digest = hashlib.sha256(source_photo.read_bytes()).hexdigest()
            if digest != expected_source_sha256:
                raise ShapeUnavailable("original source photo hash mismatch") from None
        try:
            wider, wider_box = wider_crop_with_box(source_photo, crop_box)
            vector, quality = extract_features(wider)
        except (OSError, ShapeUnavailable) as fallback_error:
            raise ShapeUnavailable(f"primary: {primary_error}; wider crop: {fallback_error}") from None
        return vector, {**quality, "crop_variant": "wider_original_photo",
                        "crop_box_original_xyxy": wider_box}


def extract_relaxed_with_fallback(crop: Image.Image, source_photo: Path,
                                  crop_box: tuple[int, int, int, int],
                                  expected_source_sha256: str | None = None) -> tuple[np.ndarray, dict]:
    """Second route after strict failure; flag the border-contact warning."""
    try:
        vector, quality = extract_features(crop, require_border_margin=False)
        return vector, {**quality, "crop_variant": "frozen_primary_relaxed",
                        "crop_box_original_xyxy": list(crop_box)}
    except ShapeUnavailable as primary_error:
        if expected_source_sha256 is not None:
            digest = hashlib.sha256(source_photo.read_bytes()).hexdigest()
            if digest != expected_source_sha256:
                raise ShapeUnavailable("original source photo hash mismatch") from None
        try:
            wider, wider_box = wider_crop_with_box(source_photo, crop_box)
            vector, quality = extract_features(wider, require_border_margin=False)
        except (OSError, ShapeUnavailable) as fallback_error:
            raise ShapeUnavailable(f"secondary primary: {primary_error}; secondary wider: {fallback_error}") from None
        return vector, {**quality, "crop_variant": "wider_original_photo_relaxed",
                        "crop_box_original_xyxy": wider_box}


def extract_strict_with_relocation(crop: Image.Image, source_photo: Path,
                                   crop_box: tuple[int, int, int, int],
                                   expected_source_sha256: str | None = None) -> tuple[np.ndarray, dict]:
    """Keep the established crop; relocate from source only if it fails."""
    try:
        return extract_with_fallback(crop, source_photo, crop_box, expected_source_sha256)
    except (OSError, ShapeUnavailable) as first_error:
        try:
            relocated, record = relocate_photo(source_photo, padded=True,
                                               expected_sha256=expected_source_sha256)
            vector, quality = extract_features(relocated)
        except (OSError, ValueError, ShapeUnavailable) as second_error:
            raise ShapeUnavailable(f"primary and wider: {first_error}; original relocation: {second_error}") from None
        return vector, {**quality, "crop_variant": "relocated_padded_original",
                        "crop_box_original_xyxy": record["crop_box_original_xyxy"],
                        "relocation_method": record["method"],
                        "virtual_border_pixels": record["virtual_border_pixels"]}


def export_forest(model: object) -> dict:
    """Export sklearn RF trees as data so inference never executes pickle."""
    if list(model.classes_) != [0, 1] or model.n_features_in_ != len(FEATURE_NAMES):
        raise ValueError("expected binary RF trained with the 19 shape features")
    trees = []
    for estimator in model.estimators_:
        tree = estimator.tree_
        values = tree.value[:, 0, :]
        probabilities = values[:, 1] / np.maximum(1e-12, values.sum(axis=1))
        trees.append({
            "left": tree.children_left.tolist(), "right": tree.children_right.tolist(),
            "feature": tree.feature.tolist(), "threshold": tree.threshold.tolist(),
            "defect_probability": probabilities.tolist(),
        })
    return {"format": MODEL_FORMAT, "feature_names": list(FEATURE_NAMES),
            "segmentation": SEGMENTATION_SPEC,
            "trees": trees}


def probability(features: np.ndarray, forest: dict) -> float:
    if (forest.get("format") != MODEL_FORMAT or
            forest.get("feature_names") != list(FEATURE_NAMES) or
            forest.get("segmentation") != SEGMENTATION_SPEC):
        raise ValueError("unsupported shape RF model")
    values = np.asarray(features, dtype=np.float64)
    if values.shape != (len(FEATURE_NAMES),) or not np.isfinite(values).all():
        raise ValueError("invalid shape feature vector")
    trees = forest.get("trees")
    if not isinstance(trees, list) or not trees:
        raise ValueError("empty shape RF forest")
    totals = []
    for tree in trees:
        node = 0
        max_steps = len(tree["feature"])
        for _ in range(max_steps):
            fi = tree["feature"][node]
            if fi < 0:
                totals.append(float(tree["defect_probability"][node]))
                break
            node = tree["left"][node] if values[fi] <= tree["threshold"][node] else tree["right"][node]
        else:
            raise ValueError("invalid shape RF tree cycle")
    return float(np.mean(totals))


def load_forest(model_path: Path, manifest_path: Path) -> tuple[dict, dict]:
    """Only load a model whose exact bytes match its local manifest."""
    model_bytes = model_path.read_bytes()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != MODEL_FORMAT or manifest.get("segmentation") != SEGMENTATION_SPEC:
        raise ValueError("unsupported shape RF manifest")
    if hashlib.sha256(model_bytes).hexdigest() != manifest.get("model_sha256"):
        raise ValueError("shape RF model hash mismatch")
    forest = json.loads(model_bytes)
    if (forest.get("format") != MODEL_FORMAT or
            forest.get("feature_names") != list(FEATURE_NAMES) or
            forest.get("segmentation") != SEGMENTATION_SPEC):
        raise ValueError("shape RF feature schema mismatch")
    return forest, manifest


def classify_crop(path: Path, forest: dict, threshold: float = 0.5,
                  uncertain_interval: tuple[float, float] | None = None) -> dict:
    try:
        with Image.open(path) as source:
            features, quality = extract_features(source.convert("RGB"))
    except (OSError, ShapeUnavailable) as exc:
        return {"verdict": "unavailable", "reason": str(exc)}
    p = probability(features, forest)
    uncertain = (uncertain_interval is not None and
                 uncertain_interval[0] <= p <= uncertain_interval[1])
    return {"verdict": "uncertain" if uncertain else ("defect" if p >= threshold else "good"),
            "defect_probability": p, "quality": quality,
            "warning": "experimental outline classifier; requires new-part validation"}


def classify_photo(path: Path, forest: dict, threshold: float = 0.5,
                   uncertain_interval: tuple[float, float] | None = None,
                   used_crop_output: Path | None = None) -> dict:
    """Use the same crop-and-wider-fallback route as full-current training."""
    try:
        crop, record = crop_mount(path, 256)
        features, quality = extract_with_fallback(crop, path, tuple(record["crop_box"]))
    except (OSError, ValueError, ShapeUnavailable) as exc:
        return {"verdict": "unavailable", "reason": str(exc)}
    used = crop if quality["crop_variant"] == "frozen_primary" else wider_crop(path, tuple(record["crop_box"]))
    if used_crop_output is not None:
        if used_crop_output.exists() or used_crop_output.suffix.lower() != ".png":
            raise ValueError("choose a new .png path for the used crop")
        used_crop_output.parent.mkdir(parents=True, exist_ok=True)
        used.save(used_crop_output)
    p = probability(features, forest)
    uncertain = (uncertain_interval is not None and
                 uncertain_interval[0] <= p <= uncertain_interval[1])
    return {"verdict": "uncertain" if uncertain else ("defect" if p >= threshold else "good"),
            "defect_probability": p, "quality": quality,
            "used_crop_path": str(used_crop_output.resolve()) if used_crop_output is not None else None,
            "used_crop_sha256": hashlib.sha256(used_crop_output.read_bytes()).hexdigest()
                                if used_crop_output is not None else None,
            "original_photo_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source_size_exif_oriented": record["source_size"],
            "warning": "experimental outline classifier; requires new-part validation"}


def classify_photo_cascade(path: Path, strict_forest: dict, relaxed_forest: dict,
                           threshold: float = 0.5,
                           low_confidence_interval: tuple[float, float] = (0.4, 0.6),
                           used_crop_output: Path | None = None) -> dict:
    """Always attempt a binary verdict, with a marked lower-quality second route."""
    try:
        crop, record = crop_mount(path, 256)
        try:
            vector, quality = extract_strict_with_relocation(crop, path, tuple(record["crop_box"]))
            forest = strict_forest
            route = "strict_relocated" if quality["crop_variant"] == "relocated_padded_original" else "strict"
        except ShapeUnavailable:
            vector, quality = extract_relaxed_with_fallback(crop, path, tuple(record["crop_box"]))
            forest = relaxed_forest
            route = "relaxed_border_contact"
    except (OSError, ValueError, ShapeUnavailable) as exc:
        return {"verdict": "unavailable", "reason": str(exc),
                "review_recommended": True}
    if quality["crop_variant"].startswith("frozen_primary"):
        used = crop
    elif quality["crop_variant"] == "relocated_padded_original":
        used, _ = relocate_photo(path, padded=True)
    else:
        used = wider_crop(path, tuple(record["crop_box"]))
    if used_crop_output is not None:
        if used_crop_output.exists() or used_crop_output.suffix.lower() != ".png":
            raise ValueError("choose a new .png path for the used crop")
        used_crop_output.parent.mkdir(parents=True, exist_ok=True)
        used.save(used_crop_output)
    p = probability(vector, forest)
    low_probability_confidence = low_confidence_interval[0] <= p <= low_confidence_interval[1]
    low_quality = route != "strict" or low_probability_confidence
    return {"verdict": "defect" if p >= threshold else "good",
            "defect_probability": p, "route": route,
            "low_quality": low_quality, "review_recommended": low_quality,
            "quality": quality,
            "used_crop_path": str(used_crop_output.resolve()) if used_crop_output is not None else None,
            "used_crop_sha256": hashlib.sha256(used_crop_output.read_bytes()).hexdigest()
                                if used_crop_output is not None else None,
            "original_photo_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source_size_exif_oriented": record["source_size"],
            "warning": "experimental two-route outline classifier; requires new-part validation"}

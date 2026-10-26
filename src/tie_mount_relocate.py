"""Second-pass localization of a complete part from its original photo.

Use this only after the established crop fails a downstream silhouette quality
check.  The established crop remains byte-for-byte unchanged when it passes.
The original image is segmented with the colored-light white-part mask; an
optional narrow virtual border supplies context when the part is close to the
original frame.  Returned coordinates refer to the EXIF-oriented original
photo, and can be negative when the crop includes the virtual border.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from src.tie_mount_crop import _box_from_mask, tinted_white_foreground_mask


PAD_FRACTION = 0.05


def _add_background_border(image: Image.Image) -> tuple[Image.Image, int, tuple[int, int, int]]:
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    edge = max(8, min(rgb.shape[:2]) // 50)
    border = np.concatenate((rgb[:edge].reshape(-1, 3),
                             rgb[-edge:].reshape(-1, 3),
                             rgb[:, :edge].reshape(-1, 3),
                             rgb[:, -edge:].reshape(-1, 3)))
    background = tuple(int(value) for value in np.median(border, axis=0))
    pad = round(image.width * PAD_FRACTION)
    padded = Image.new("RGB", (image.width + 2 * pad, image.height + 2 * pad),
                       background)
    padded.paste(image, (pad, pad))
    return padded, pad, background


def relocate_photo(path: Path, *, padded: bool = False,
                   expected_sha256: str | None = None) -> tuple[Image.Image, dict]:
    """Return a second-pass 256-square crop and its source-coordinate record.

    ``padded=False`` tries the full original as photographed. ``padded=True``
    adds five percent of the source width on every side before looking for the
    part. A later silhouette check must still reject a bad crop; this function
    alone does not certify that the full part was recovered.
    """
    source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_sha256 is not None and source_sha256 != expected_sha256:
        raise ValueError("original source photo hash mismatch")
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    source_size = list(image.size)
    pad = 0
    background = None
    if padded:
        image, pad, background = _add_background_border(image)
    preview = image.copy()
    preview.thumbnail((512, 512), Image.Resampling.BILINEAR)
    mask = tinted_white_foreground_mask(preview)
    box = _box_from_mask(image.size, preview.size, mask,
                         edge_gap=max(4, round(min(preview.size) * 0.01)),
                         require_compact=True)
    crop = image.crop(box).resize((256, 256), Image.Resampling.LANCZOS)
    source_box = [coordinate - pad for coordinate in box]
    record = {
        "method": "tinted_white_original_with_background_border" if padded
                  else "tinted_white_original",
        "source": str(path),
        "source_sha256": source_sha256,
        "source_size_exif_oriented": source_size,
        "crop_box_original_xyxy": source_box,
        "virtual_border_pixels": pad,
        "virtual_background_rgb": list(background) if background is not None else None,
        "output_size": [256, 256],
    }
    return crop, record

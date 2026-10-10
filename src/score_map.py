"""Software reference for local teacher-student anomaly scoring.

Input features must already be aligned to the same numeric scale. This module
does not train a network, run inference, choose a threshold or inspect holes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def _check_shapes(teacher: np.ndarray, student: np.ndarray) -> None:
    if teacher.ndim != 3 or teacher.shape != student.shape:
        raise ValueError("teacher and student must have matching [C, H, W] shapes")
    if 0 in teacher.shape:
        raise ValueError("feature dimensions must be nonempty")


def score_map_float(teacher: np.ndarray, student: np.ndarray) -> np.ndarray:
    """Mean squared difference over channels, as a float32 [H, W] map."""
    teacher = np.asarray(teacher)
    student = np.asarray(student)
    _check_shapes(teacher, student)
    if not (np.issubdtype(teacher.dtype, np.number) and
            np.issubdtype(student.dtype, np.number)):
        raise TypeError("features must be numeric")
    teacher = teacher.astype(np.float32)
    student = student.astype(np.float32)
    if not (np.isfinite(teacher).all() and np.isfinite(student).all()):
        raise ValueError("features must contain only finite values")
    diff = teacher - student
    return np.mean(diff * diff, axis=0, dtype=np.float32)


def score_map_int8(teacher: np.ndarray, student: np.ndarray) -> np.ndarray:
    """Return floor(sum_c((T-S)^2)/C) in integer squared-feature units.

    Both inputs must use the same zero point and scale. The caller must check
    this condition: an int8 dtype alone does not establish equal scales.
    """
    teacher = np.asarray(teacher)
    student = np.asarray(student)
    _check_shapes(teacher, student)
    if teacher.dtype != np.int8 or student.dtype != np.int8:
        raise TypeError("quantized inputs must both have dtype int8")
    diff = teacher.astype(np.int16) - student.astype(np.int16)
    squared = diff.astype(np.int32) ** 2
    total = np.sum(squared, axis=0, dtype=np.int64)
    return (total // teacher.shape[0]).astype(np.uint32)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("teacher", type=Path, help="teacher feature tensor .npy [C,H,W]")
    parser.add_argument("student", type=Path, help="student feature tensor .npy [C,H,W]")
    parser.add_argument("--output", type=Path, required=True, help="output score map .npy [H,W]")
    parser.add_argument("--int8", action="store_true", help="compare aligned int8 tensors")
    args = parser.parse_args()

    teacher = np.load(args.teacher, allow_pickle=False)
    student = np.load(args.student, allow_pickle=False)
    score = score_map_int8(teacher, student) if args.int8 else score_map_float(teacher, student)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, score)
    print(f"Saved {score.shape} score map to {args.output}")


if __name__ == "__main__":
    main()

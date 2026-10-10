"""Numerical checks for the reference used by future hardware comparisons."""

import unittest

import numpy as np

from src.score_map import score_map_float, score_map_int8


class ScoreMapTests(unittest.TestCase):
    def test_anomaly_location_and_channel_mean(self) -> None:
        teacher = np.zeros((2, 2, 2), dtype=np.float32)
        student = teacher.copy()
        student[0, 0, 1] = 2
        student[1, 0, 1] = 4
        np.testing.assert_array_equal(
            score_map_float(teacher, student),
            np.array([[0, 10], [0, 0]], dtype=np.float32),
        )

    def test_int8_subtraction_and_square_do_not_overflow(self) -> None:
        teacher = np.full((2, 1, 1), 127, dtype=np.int8)
        student = np.full((2, 1, 1), -128, dtype=np.int8)
        np.testing.assert_array_equal(
            score_map_int8(teacher, student),
            np.array([[65025]], dtype=np.uint32),
        )

    def test_mismatched_shapes_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            score_map_float(np.zeros((2, 2, 2)), np.zeros((2, 3, 2)))


if __name__ == "__main__":
    unittest.main()

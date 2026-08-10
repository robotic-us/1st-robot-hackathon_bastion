#!/usr/bin/env python3

import math
import unittest

from phorce_relative_controller import NUM_AXES, absolute_positions


class AbsolutePositionTest(unittest.TestCase):
    def test_six_axis_relative_zero_mapping(self) -> None:
        axes = [0, 1, 2, 6, 7, 8]
        zero = [-1.316, -3.096, 0.904, 0.0, 0.0, 0.0, 2.296, 1.154, -1.742, 0.0, 0.0, 0.0]
        relative = [0.0] * NUM_AXES
        for axis in axes:
            relative[axis] = math.radians(30.0)

        result = absolute_positions(zero, relative, axes)

        for axis in axes:
            self.assertAlmostEqual(result[axis], zero[axis] + math.radians(30.0))
        for axis in set(range(NUM_AXES)) - set(axes):
            self.assertEqual(result[axis], 0.0)


if __name__ == "__main__":
    unittest.main()

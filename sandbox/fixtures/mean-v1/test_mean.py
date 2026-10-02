import unittest

from mean import mean


class MeanTests(unittest.TestCase):
    def test_arithmetic(self) -> None:
        for values, expected in (([1.0, 2.0], 1.5), ([-2.0, -1.0], -1.5), ([0.25], 0.25)):
            with self.subTest(values=values):
                self.assertEqual(mean(values), expected)
        with self.assertRaises(ValueError):
            mean([])

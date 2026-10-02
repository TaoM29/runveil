import unittest

from clamp import clamp


class ClampTests(unittest.TestCase):
    def test_bounds(self) -> None:
        for value, expected in ((-3, 0), (0, 0), (4, 4), (10, 10), (15, 10)):
            with self.subTest(value=value):
                self.assertEqual(clamp(value, 0, 10), expected)

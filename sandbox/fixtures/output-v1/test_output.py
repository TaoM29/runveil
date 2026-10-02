import os
import unittest


class OutputProbe(unittest.TestCase):
    def test_output(self) -> None:
        while True:
            os.write(1, b"x" * 4096)

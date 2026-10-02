import time
import unittest


class TimeoutProbe(unittest.TestCase):
    def test_timeout(self) -> None:
        time.sleep(60)

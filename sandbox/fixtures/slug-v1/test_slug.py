import unittest

from slug import slug


class SlugTests(unittest.TestCase):
    def test_whitespace(self) -> None:
        for text, expected in (
            ("  Hello   WORLD  ", "hello-world"),
            ("One\tTwo\nThree", "one-two-three"),
            ("", ""),
            (" \t\n ", ""),
            ("Keep.This!", "keep.this!"),
        ):
            with self.subTest(text=text):
                self.assertEqual(slug(text), expected)

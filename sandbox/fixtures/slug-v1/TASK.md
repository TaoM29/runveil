# Normalize whitespace in a slug

Repair slug.py so slug(text) lowercases words and joins them with one hyphen.
Treat runs of whitespace (including tabs and newlines) as separators, and ignore
leading/trailing whitespace. Empty or all-whitespace input produces an empty string.
Preserve punctuation. Do not modify the tests or this task description.

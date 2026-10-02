"""Closed project-owned coding tasks; never a caller-selected repository path."""

from typing import Literal

FixtureName = Literal["clamp-v1", "slug-v1", "mean-v1"]
FixturePath = Literal[
    "TASK.md", "clamp.py", "test_clamp.py", "slug.py", "test_slug.py", "mean.py", "test_mean.py"
]
FIXTURE_PATHS: dict[FixtureName, tuple[FixturePath, FixturePath, FixturePath]] = {
    "clamp-v1": ("TASK.md", "clamp.py", "test_clamp.py"),
    "slug-v1": ("TASK.md", "slug.py", "test_slug.py"),
    "mean-v1": ("TASK.md", "mean.py", "test_mean.py"),
}

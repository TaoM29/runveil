"""Descriptor-owned, bounded reads from an operator-controlled local checkout."""

import hashlib
import json
import os
import stat
from pathlib import Path
from threading import Lock

from runveil_core.tools import ToolError, ToolErrorCode

MAX_FILE_BYTES = 65_536
MAX_SEARCH_BYTES = 1_048_576


def relative_path(value: str) -> str:
    parts = value.split("/")
    if (
        not 1 <= len(value) <= 256
        or "\\" in value
        or ":" in value
        or any(not char.isprintable() for char in value)
        or any(not part or part.startswith(".") for part in parts)
    ):
        raise ValueError("Expected a non-hidden canonical relative file path")
    return value


class RepositoryReader:
    """One root lifetime; calls own their descriptors, including after close."""

    def __init__(self, root: Path) -> None:
        if (
            os.name != "posix"
            or os.open not in os.supports_dir_fd
            or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "O_DIRECTORY")
        ):
            raise ValueError("Repository tools require POSIX descriptor-relative opens")
        self._lock = Lock()
        self._root: int | None = None
        try:
            resolved = root.resolve(strict=True)
            self._root = os.open(resolved, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(self._root)
            self.root_digest = hashlib.sha256(
                json.dumps([str(resolved), info.st_dev, info.st_ino]).encode("utf-8")
            ).hexdigest()
        except (OSError, RuntimeError):
            self.close()
            raise ValueError("Repository root is unavailable") from None

    def close(self) -> None:
        with self._lock:
            if self._root is not None:
                os.close(self._root)
                self._root = None

    def read(self, path: str, limit: int = MAX_FILE_BYTES) -> tuple[str, int]:
        """Called in a worker thread. Never reopen an absolute model-selected path."""
        relative_path(path)
        directory: int | None = None
        file: int | None = None
        try:
            with self._lock:
                if self._root is None:
                    raise ToolError(ToolErrorCode.RESOURCE_UNAVAILABLE)
                directory = os.dup(self._root)
            device = os.fstat(directory).st_dev
            parts = path.split("/")
            for part in parts[:-1]:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                )
                os.close(directory)
                directory = child
                if os.fstat(directory).st_dev != device:
                    raise ToolError(ToolErrorCode.RESOURCE_UNAVAILABLE)
            # Refuse known special files before opening; recheck the opened inode
            # to reject replacement between this inspection and the safe open.
            candidate = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            if (
                not stat.S_ISREG(candidate.st_mode)
                or candidate.st_dev != device
                or candidate.st_nlink != 1
            ):
                raise ToolError(ToolErrorCode.RESOURCE_UNAVAILABLE)
            file = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            before = os.fstat(file)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_ino != candidate.st_ino
                or before.st_dev != device
                or before.st_nlink != 1
            ):
                raise ToolError(ToolErrorCode.RESOURCE_UNAVAILABLE)
            if before.st_size > limit:
                raise ToolError(ToolErrorCode.RESOURCE_LIMIT)
            data = bytearray()
            while len(data) <= limit:
                chunk = os.read(file, min(8192, limit + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) > limit:
                raise ToolError(ToolErrorCode.RESOURCE_LIMIT)
            after = os.fstat(file)
            if (
                before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns
                or after.st_nlink != 1
            ):
                raise ToolError(ToolErrorCode.RESOURCE_UNAVAILABLE)
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError:
                raise ToolError(ToolErrorCode.RESOURCE_INVALID) from None
            if "\x00" in content:
                raise ToolError(ToolErrorCode.RESOURCE_INVALID)
            return content, len(data)
        except OSError:
            raise ToolError(ToolErrorCode.RESOURCE_UNAVAILABLE) from None
        finally:
            if file is not None:
                os.close(file)
            if directory is not None:
                os.close(directory)

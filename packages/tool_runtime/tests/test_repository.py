import asyncio
import json
import os
from pathlib import Path
from threading import Event

import pytest
from pydantic import ValidationError
from runveil_core.agents import JsonValue
from runveil_core.tools import MAX_TOOL_BYTES, Permission, ToolError, ToolPolicy, ToolRegistry
from runveil_tools.filesystem import MAX_FILE_BYTES, MAX_SEARCH_BYTES
from runveil_tools.repository import RepositoryAccess, RepositoryTools

POLICY = ToolPolicy(
    allowed_tools=("repository.read_file", "repository.search"), permissions=(Permission.READ,)
)
pytestmark = pytest.mark.asyncio


async def test_read_offsets_literal_search_and_output_bounds(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("héllo 😀\nneedle.*\nneedle.* again\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("needle.*\nNEEDLE.*\n", encoding="utf-8")
    # Worst-case JSON escaping, including long paths and long lines.
    wide_path = "😀" * 40
    (tmp_path / wide_path).mkdir()
    wide_path += "/" + "😀" * 40
    (tmp_path / wide_path).write_text("😀" * 4097, encoding="utf-8")
    with RepositoryTools(
        tmp_path, access=RepositoryAccess(files=("b.txt", "a.txt", wide_path))
    ) as repository:
        registry = ToolRegistry(repository.bindings())
        first = await registry.dispatch(
            "repository.read_file", {"path": "a.txt", "max_chars": 7}, POLICY, POLICY
        )
        assert first == {"path": "a.txt", "content": "héllo 😀", "next_offset": 7}
        rest = await registry.dispatch(
            "repository.read_file", {"path": "a.txt", "offset": 7}, POLICY, POLICY
        )
        assert rest["content"] == "\nneedle.*\nneedle.* again\n" and rest["next_offset"] is None
        found = await registry.dispatch("repository.search", {"query": "needle.*"}, POLICY, POLICY)
        assert found == {
            "matches": [
                {"path": "a.txt", "line": 2, "excerpt": "needle.*"},
                {"path": "a.txt", "line": 3, "excerpt": "needle.* again"},
                {"path": "b.txt", "line": 1, "excerpt": "needle.*"},
            ],
            "truncated": False,
            "files_scanned": 3,
        }
        limited = await registry.dispatch(
            "repository.search", {"query": "needle.*", "max_matches": 1}, POLICY, POLICY
        )
        assert limited["truncated"] is True and limited["matches"] == [
            {"path": "a.txt", "line": 2, "excerpt": "needle.*"}
        ]
        wide = await registry.dispatch("repository.read_file", {"path": wide_path}, POLICY, POLICY)
        assert wide["next_offset"] == 4096
        assert len(json.dumps(wide).encode()) <= MAX_TOOL_BYTES


async def test_path_and_disclosure_policy_precede_filesystem_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "public.txt").write_text("public", encoding="utf-8")
    (tmp_path / "private.txt").write_text("not-disclosed", encoding="utf-8")
    with RepositoryTools(tmp_path, access=RepositoryAccess(files=("public.txt",))) as repository:
        registry = ToolRegistry(repository.bindings())

        def forbidden_read(*args: object) -> None:
            raise AssertionError("denied input reached filesystem")

        monkeypatch.setattr(repository._reader, "read", forbidden_read)
        for path in (
            "../outside",
            "/etc/passwd",
            "a/../b",
            "a//b",
            "./a",
            "a\\b",
            ".env",
            "a/.git/config",
            "a\x00b",
            "C:drive",
        ):
            with pytest.raises(ValidationError):
                RepositoryAccess(files=(path,))
            with pytest.raises(ToolError, match="^invalid_tool_arguments$"):
                await registry.dispatch("repository.read_file", {"path": path}, POLICY, POLICY)
        with pytest.raises(ToolError, match="^tool_permission_denied$"):
            await registry.dispatch("repository.read_file", {"path": "private.txt"}, POLICY, POLICY)
        with pytest.raises(ToolError, match="^tool_permission_denied$"):
            await registry.dispatch(
                "repository.read_file", {"path": "public.txt"}, POLICY, ToolPolicy()
            )
    with RepositoryTools(tmp_path) as empty:
        result = await ToolRegistry(empty.bindings()).dispatch(
            "repository.search", {"query": "not-disclosed"}, POLICY, POLICY
        )
        assert result == {"matches": [], "truncated": False, "files_scanned": 0}


async def test_symlinks_hardlinks_special_files_and_missing_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside.txt").write_text("not-disclosed", encoding="utf-8")
    (root / "link.txt").symlink_to(tmp_path / "outside.txt")
    (root / "linked-dir").symlink_to(tmp_path, target_is_directory=True)
    os.link(tmp_path / "outside.txt", root / "hard.txt")
    os.mkfifo(root / "pipe")
    (root / "directory").mkdir()
    paths = ("link.txt", "linked-dir/outside.txt", "hard.txt", "pipe", "directory", "missing")
    with RepositoryTools(root, access=RepositoryAccess(files=paths)) as repository:
        registry = ToolRegistry(repository.bindings())
        for path in paths:
            with pytest.raises(ToolError, match="^tool_resource_unavailable$"):
                await registry.dispatch("repository.read_file", {"path": path}, POLICY, POLICY)
        with pytest.raises(ToolError, match="^tool_resource_unavailable$"):
            await registry.dispatch("repository.search", {"query": "not-disclosed"}, POLICY, POLICY)


async def test_text_file_and_search_scan_limits(tmp_path: Path) -> None:
    for name, content, error in (
        ("large", b"x" * (MAX_FILE_BYTES + 1), "tool_resource_limit"),
        ("binary", b"valid\x00text", "tool_resource_invalid"),
        ("encoding", b"\xff", "tool_resource_invalid"),
    ):
        (tmp_path / name).write_bytes(content)
        with RepositoryTools(tmp_path, access=RepositoryAccess(files=(name,))) as repository:
            registry = ToolRegistry(repository.bindings())
            cases: tuple[tuple[str, dict[str, JsonValue]], ...] = (
                ("repository.read_file", {"path": name}),
                ("repository.search", {"query": "x"}),
            )
            for tool, arguments in cases:
                with pytest.raises(ToolError, match=f"^{error}$"):
                    await registry.dispatch(tool, arguments, POLICY, POLICY)
    files = tuple(f"file-{n:02}.txt" for n in range(MAX_SEARCH_BYTES // MAX_FILE_BYTES + 1))
    for name in files:
        (tmp_path / name).write_bytes(b"x" * MAX_FILE_BYTES)
    with RepositoryTools(tmp_path, access=RepositoryAccess(files=files)) as repository:
        with pytest.raises(ToolError, match="^tool_resource_limit$"):
            await ToolRegistry(repository.bindings()).dispatch(
                "repository.search", {"query": "absent"}, POLICY, POLICY
            )


async def test_root_replacement_and_component_swap_cannot_redirect_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src/file.txt").write_text("original", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "file.txt").write_text("not-disclosed", encoding="utf-8")
    with RepositoryTools(root, access=RepositoryAccess(files=("src/file.txt",))) as repository:
        registry = ToolRegistry(repository.bindings())
        moved = tmp_path / "moved"
        root.rename(moved)
        root.symlink_to(outside, target_is_directory=True)
        result = await registry.dispatch(
            "repository.read_file", {"path": "src/file.txt"}, POLICY, POLICY
        )
        assert result["content"] == "original"
        original_open = os.open

        def swap(path: str, flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
            if path == "src":
                (moved / "src").rename(moved / "old-src")
                (moved / "src").symlink_to(outside, target_is_directory=True)
            return original_open(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(os, "open", swap)
        with pytest.raises(ToolError, match="^tool_resource_unavailable$"):
            await registry.dispatch(
                "repository.read_file", {"path": "src/file.txt"}, POLICY, POLICY
            )


async def test_cancelled_read_closes_its_descriptors_after_binding_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "file.txt").write_text("public", encoding="utf-8")
    repository = RepositoryTools(tmp_path, access=RepositoryAccess(files=("file.txt",)))
    registry = ToolRegistry(repository.bindings())
    entered, release, finished = Event(), Event(), Event()
    original_read = os.read
    opened: list[int] = []

    def blocked_read(fd: int, count: int) -> bytes:
        opened.append(fd)
        entered.set()
        if not release.wait(timeout=5):
            raise RuntimeError("test release timed out")
        return original_read(fd, count)

    original = repository._reader.read

    def tracked_read(path: str, limit: int = MAX_FILE_BYTES) -> tuple[str, int]:
        try:
            return original(path, limit)
        finally:
            finished.set()

    monkeypatch.setattr(os, "read", blocked_read)
    monkeypatch.setattr(repository._reader, "read", tracked_read)
    task = asyncio.create_task(
        registry.dispatch("repository.read_file", {"path": "file.txt"}, POLICY, POLICY)
    )
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        repository.close()
        release.set()
        assert await asyncio.to_thread(finished.wait, 5)
        for fd in set(opened):
            with pytest.raises(OSError):
                os.fstat(fd)
        with pytest.raises(ToolError, match="^tool_resource_unavailable$"):
            await registry.dispatch("repository.read_file", {"path": "file.txt"}, POLICY, POLICY)
    finally:
        release.set()
        repository.close()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("grow", [False, True])
async def test_file_changes_during_read_fail_without_partial_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, grow: bool
) -> None:
    path = tmp_path / "changing.txt"
    path.write_text("original", encoding="utf-8")
    original_read = os.read
    changed = False

    def changing_read(fd: int, count: int) -> bytes:
        nonlocal changed
        if not changed:
            changed = True
            path.write_bytes(b"x" * (MAX_FILE_BYTES + 1) if grow else b"changed")
        return original_read(fd, count)

    with RepositoryTools(tmp_path, access=RepositoryAccess(files=(path.name,))) as repository:
        monkeypatch.setattr(os, "read", changing_read)
        code = "tool_resource_limit" if grow else "tool_resource_unavailable"
        with pytest.raises(ToolError, match=f"^{code}$"):
            await ToolRegistry(repository.bindings()).dispatch(
                "repository.read_file", {"path": path.name}, POLICY, POLICY
            )

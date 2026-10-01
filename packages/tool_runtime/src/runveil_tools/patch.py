"""Atomic replacement in an exclusively assigned, trusted local checkout."""

import fcntl
import hashlib
import json
import os
import stat
from pathlib import Path
from uuid import uuid4

from runveil_core.approvals import PatchProposal
from runveil_core.mutations import PatchOutcomeUnknown
from runveil_core.runtime import WorkspaceIdentity
from runveil_core.tools import ToolError, ToolErrorCode

from runveil_tools.filesystem import MAX_FILE_BYTES, relative_path

_IMPLEMENTATION_DIGEST = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def patch_identity(review: WorkspaceIdentity) -> WorkspaceIdentity:
    return review.model_copy(
        update={
            "implementation_digest": hashlib.sha256(
                (review.implementation_digest + _IMPLEMENTATION_DIGEST).encode()
            ).hexdigest()
        }
    )


class SingleFileWriter:
    def __init__(self, root: Path, path: str, workspace: WorkspaceIdentity) -> None:
        relative_path(path)
        if "/" in path:
            raise ValueError("Patch writer accepts only one top-level file")
        self.root = root
        self.path = path
        self.workspace = workspace

    def apply(self, proposal: PatchProposal) -> None:
        # Revalidate even constructed/copied contracts at this final boundary.
        proposal = PatchProposal.model_validate_json(proposal.model_dump_json())
        if proposal.path != self.path:
            raise ToolError(ToolErrorCode.DENIED)
        data = proposal.after.encode("utf-8")
        if len(data) > MAX_FILE_BYTES:
            raise ToolError(ToolErrorCode.RESOURCE_LIMIT)
        directory = original = staged = None
        name: str | None = None
        replacing = False
        try:
            resolved = self.root.resolve(strict=True)
            directory = os.open(resolved, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
            root_info = os.fstat(directory)
            if root_info.st_uid != os.geteuid() or root_info.st_mode & 0o022:
                raise ToolError(ToolErrorCode.RESOURCE_INVALID)
            identity = hashlib.sha256(
                json.dumps([str(resolved), root_info.st_dev, root_info.st_ino]).encode()
            ).hexdigest()
            if identity != self.workspace.root_digest:
                raise ToolError(ToolErrorCode.RESOURCE_INVALID)
            candidate = os.stat(self.path, dir_fd=directory, follow_symlinks=False)
            if (
                not stat.S_ISREG(candidate.st_mode)
                or candidate.st_nlink != 1
                or candidate.st_dev != root_info.st_dev
                or candidate.st_uid != os.geteuid()
                or stat.S_IMODE(candidate.st_mode) not in (0o600, 0o644)
            ):
                raise ToolError(ToolErrorCode.RESOURCE_INVALID)
            original = os.open(
                self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
            )
            before = os.fstat(original)
            if before != candidate or before.st_size > MAX_FILE_BYTES:
                raise ToolError(ToolErrorCode.RESOURCE_INVALID)
            chunks = bytearray()
            while len(chunks) <= MAX_FILE_BYTES:
                chunk = os.read(original, min(8192, MAX_FILE_BYTES + 1 - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
            if bytes(chunks) != proposal.before.encode("utf-8"):
                raise ToolError(ToolErrorCode.RESOURCE_INVALID)
            name = ".runveil-" + uuid4().hex
            staged = os.open(
                name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
            )
            offset = 0
            while offset < len(data):
                written = os.write(staged, data[offset:])
                if written <= 0:
                    raise OSError("short write")
                offset += written
            if os.fstat(staged).st_gid != before.st_gid:
                raise ToolError(ToolErrorCode.RESOURCE_INVALID)
            os.fchmod(staged, stat.S_IMODE(before.st_mode))
            os.fsync(staged)
            stage_info = os.fstat(staged)
            stage_path = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if stage_info.st_nlink != 1 or (stage_path.st_dev, stage_path.st_ino) != (
                stage_info.st_dev,
                stage_info.st_ino,
            ):
                raise ToolError(ToolErrorCode.RESOURCE_INVALID)
            current = os.stat(self.path, dir_fd=directory, follow_symlinks=False)
            current_root = self.root.resolve(strict=True)
            root_now = current_root.stat()

            # Ignore atime, which our own read may update.
            def signature(info: os.stat_result) -> tuple[int, ...]:
                return (
                    info.st_dev,
                    info.st_ino,
                    info.st_mode,
                    info.st_uid,
                    info.st_gid,
                    info.st_nlink,
                    info.st_size,
                    info.st_mtime_ns,
                    info.st_ctime_ns,
                )

            if (
                current_root != resolved
                or signature(current) != signature(before)
                or signature(os.fstat(original)) != signature(before)
                or (root_now.st_dev, root_now.st_ino) != (root_info.st_dev, root_info.st_ino)
            ):
                raise ToolError(ToolErrorCode.RESOURCE_INVALID)
            replacing = True
            os.replace(name, self.path, src_dir_fd=directory, dst_dir_fd=directory)
            name = None
            os.fsync(directory)
        except (OSError, RuntimeError):
            if replacing:
                raise PatchOutcomeUnknown from None
            raise ToolError(ToolErrorCode.RESOURCE_UNAVAILABLE) from None
        finally:
            for descriptor in (staged, original):
                if descriptor is not None:
                    os.close(descriptor)
            if directory is not None:
                try:
                    if name is not None:
                        os.unlink(name, dir_fd=directory)
                finally:
                    os.close(directory)

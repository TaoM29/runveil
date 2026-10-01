import os
from pathlib import Path

import pytest
from runveil_core.approvals import PatchProposal
from runveil_core.mutations import APPLY_TOOL, authorize_patch
from runveil_core.tools import Permission, ToolError, ToolPolicy
from runveil_tools.patch import SingleFileWriter, patch_identity
from runveil_tools.repository import RepositoryAccess, RepositoryTools
from runveil_tools.review import review_identity


def writer(root: Path) -> SingleFileWriter:
    with RepositoryTools(root, access=RepositoryAccess(files=("a.txt",)), snapshot=True) as repo:
        return SingleFileWriter(root, "a.txt", patch_identity(review_identity(repo)))


def test_atomic_replacement_and_preimage_link_mode_boundaries(tmp_path: Path) -> None:
    granted = ToolPolicy(allowed_tools=(APPLY_TOOL,), permissions=(Permission.WRITE,))
    for pinned, operator in ((ToolPolicy(), granted), (granted, ToolPolicy())):
        with pytest.raises(ToolError):
            authorize_patch(pinned, operator)
    target = tmp_path / "a.txt"
    target.write_text("before")
    target.chmod(0o600)
    bound = writer(tmp_path)
    proposal = PatchProposal(path="a.txt", before="before", after="after")
    tmp_path.chmod(0o777)
    with pytest.raises(ToolError):
        bound.apply(proposal)
    tmp_path.chmod(0o700)
    bound.apply(proposal)
    assert target.read_text() == "after" and target.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".runveil-*"))
    with pytest.raises(ToolError):
        bound.apply(proposal)
    assert target.read_text() == "after"
    for kind in ("symlink", "hardlink", "executable", "changed"):
        target.unlink()
        other = tmp_path / "other.txt"
        other.write_text("before")
        if kind == "symlink":
            target.symlink_to(other)
        elif kind == "hardlink":
            os.link(other, target)
        else:
            target.write_text("different" if kind == "changed" else "before")
            if kind == "executable":
                target.chmod(0o755)
        with pytest.raises(ToolError):
            bound.apply(proposal)
        assert other.read_text() == "before"
        assert not list(tmp_path.glob(".runveil-*"))
    with pytest.raises(ValueError):
        SingleFileWriter(tmp_path, "nested/a.txt", bound.workspace)

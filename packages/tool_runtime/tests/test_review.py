from pathlib import Path

import pytest
from runveil_core.approvals import PROPOSAL_TOOL, PatchProposal
from runveil_core.tools import Permission, ToolError, ToolErrorCode, ToolPolicy, ToolRegistry
from runveil_tools.repository import RepositoryAccess, RepositoryTools
from runveil_tools.review import proposal_binding


@pytest.mark.asyncio
async def test_proposal_requires_snapshot_preimage_and_both_grants(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("original")
    policy = ToolPolicy(allowed_tools=(PROPOSAL_TOOL,), permissions=(Permission.READ,))
    proposal = PatchProposal(path="a.txt", before="original", after="changed")
    with RepositoryTools(
        tmp_path, access=RepositoryAccess(files=("a.txt",)), snapshot=True
    ) as repo:
        registry = ToolRegistry((proposal_binding(repo),))
        for pinned, operator in ((policy, ToolPolicy()), (ToolPolicy(), policy)):
            assert registry.offers(pinned, operator) == ()
            with pytest.raises(ToolError) as denied:
                await registry.dispatch(
                    PROPOSAL_TOOL, proposal.model_dump(mode="json"), pinned, operator
                )
            assert denied.value.code == ToolErrorCode.DENIED
        for bad in (
            proposal.model_copy(update={"path": "b.txt"}),
            proposal.model_copy(update={"before": "different"}),
        ):
            with pytest.raises(ToolError):
                await registry.dispatch(PROPOSAL_TOOL, bad.model_dump(mode="json"), policy, policy)
        assert await registry.dispatch(
            PROPOSAL_TOOL, proposal.model_dump(mode="json"), policy, policy
        ) == proposal.model_dump(mode="json")
        assert path.read_text() == "original"
    with RepositoryTools(tmp_path, access=RepositoryAccess(files=("a.txt",))) as live:
        with pytest.raises(ValueError, match="captured"):
            proposal_binding(live)

"""Validate a proposal against a disclosed snapshot; no filesystem writes."""

import hashlib
from pathlib import Path

from runveil_core import approvals
from runveil_core.approvals import PROPOSAL_TOOL, PatchProposal
from runveil_core.runtime import WorkspaceIdentity
from runveil_core.tools import Permission, SideEffect, ToolError, ToolErrorCode, TypedTool

from runveil_tools.repository import ReadFileOutput, RepositoryTools


def _implementation_digest() -> str:
    source = approvals.__file__
    if source is None:
        raise ValueError("Review requires source-backed contracts")
    return hashlib.sha256(Path(__file__).read_bytes() + Path(source).read_bytes()).hexdigest()


# Match the repository adapter: fingerprint installed binding sources once per process.
_IMPLEMENTATION_DIGEST = _implementation_digest()


def review_identity(repository: RepositoryTools) -> WorkspaceIdentity:
    if repository.identity is None or len(repository.files) != 1:
        raise ValueError("Review requires exactly one captured file")
    digest = hashlib.sha256(
        (repository.identity.implementation_digest + _IMPLEMENTATION_DIGEST).encode()
    ).hexdigest()
    return repository.identity.model_copy(update={"implementation_digest": digest})


def proposal_binding(repository: RepositoryTools) -> TypedTool[PatchProposal, PatchProposal]:
    review_identity(repository)
    reader = repository.bindings()[0]

    async def validate(proposal: PatchProposal) -> PatchProposal:
        if proposal.path not in repository.files:
            raise ToolError(ToolErrorCode.DENIED)
        result = ReadFileOutput.model_validate(
            await reader.invoke({"path": proposal.path, "max_chars": 4096})
        )
        if result.next_offset is not None:
            raise ToolError(ToolErrorCode.RESOURCE_LIMIT)
        if proposal.before != result.content:
            raise ToolError(ToolErrorCode.RESOURCE_INVALID)
        return proposal

    return TypedTool(
        name=PROPOSAL_TOOL,
        description="Propose a replacement for human review. Validates the snapshot; never writes.",
        input_type=PatchProposal,
        output_type=PatchProposal,
        handler=validate,
        permission=Permission.READ,
        side_effect=SideEffect.READ_ONLY,
    )

"""Narrow approved-write capability; never exposed through ordinary tool dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from runveil_core.approvals import PatchProposal
from runveil_core.tools import Permission, ToolError, ToolErrorCode, ToolPolicy

if TYPE_CHECKING:
    from runveil_core.runtime import WorkspaceIdentity

PATCH_PROFILE = "repository-patch-v1"
APPLY_TOOL = "repository.apply_patch"


class PatchOutcomeUnknown(Exception):
    """Replacement may have happened; never retry automatically."""


class PatchWriter(Protocol):
    @property
    def workspace(self) -> WorkspaceIdentity: ...

    def apply(self, proposal: PatchProposal) -> None: ...


def authorize_patch(pinned: ToolPolicy, operator: ToolPolicy) -> None:
    if any(
        APPLY_TOOL not in p.allowed_tools or Permission.WRITE not in p.permissions
        for p in (pinned, operator)
    ):
        raise ToolError(ToolErrorCode.DENIED)

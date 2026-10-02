"""Single-use sandbox mutation contracts, separate from review-only approvals."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import Field, model_validator

from runveil_core.approvals import PatchProposal
from runveil_core.models import Contract
from runveil_core.mutations import APPLY_TOOL, authorize_patch
from runveil_core.sandbox import SandboxIdentity, TestsResult
from runveil_core.sandbox_review import (
    REVIEW_POLICY,
    InspectionResult,
    authorize_review,
    validate_proposal,
)
from runveil_core.tools import Permission, ToolPolicy

SANDBOX_PATCH_PROFILE = "sandbox-patch-v1"
PATCH_POLICY = ToolPolicy(
    allowed_tools=(*REVIEW_POLICY.allowed_tools, APPLY_TOOL),
    permissions=(*REVIEW_POLICY.permissions, Permission.WRITE),
)
PATCH_UNKNOWN = "sandbox_patch_outcome_unknown"
MAX_PATCH_INPUT_BYTES = 32768


class SandboxPatchInput(Contract):
    approval_id: UUID
    proposal: PatchProposal
    inspection: InspectionResult

    @model_validator(mode="after")
    def exact_preimage(self) -> SandboxPatchInput:
        validate_proposal(self.proposal, self.inspection)
        self.postimage()
        if len(self.model_dump_json().encode()) > MAX_PATCH_INPUT_BYTES:
            raise ValueError("Sandbox patch input exceeds its limit")
        return self

    def postimage(self) -> InspectionResult:
        return InspectionResult(
            files=(
                self.inspection.files[0],
                self.inspection.files[1].model_copy(update={"content": self.proposal.after}),
                self.inspection.files[2],
            )
        )


class SandboxPatchObservation(Contract):
    applied: Literal[True] = True
    proposal_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    before_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    after_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    tests: TestsResult

    @model_validator(mode="after")
    def test_status(self) -> SandboxPatchObservation:
        if self.tests.status == "passed" and self.tests.exit_code != 0:
            raise ValueError("Passed tests require exit zero")
        if self.tests.status == "tests_failed" and self.tests.exit_code != 1:
            raise ValueError("Failed tests require exit one")
        return self


class SandboxPatchResult(SandboxPatchObservation):
    approved_diff: Annotated[str, Field(max_length=20000)]
    cleanup_confirmed: Literal[True] = True


class SandboxPatchExecutor(Protocol):
    @property
    def identity(self) -> SandboxIdentity: ...

    async def apply(
        self, invocation_id: UUID, payload: SandboxPatchInput, admit: Callable[[], Awaitable[None]]
    ) -> SandboxPatchResult: ...


def authorize_sandbox_patch(pinned: ToolPolicy, operator: ToolPolicy) -> None:
    authorize_review(pinned, operator)
    authorize_patch(pinned, operator)

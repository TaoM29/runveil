"""Transactional patch-review workflow; never dispatches a tool or writes a file."""

from typing import Literal, cast
from uuid import UUID, uuid4

from runveil_core.approvals import REVIEW_CONFIGURATION, ApprovalRequest, PatchProposal
from runveil_core.errors import InvalidTransition, NotFound, RevisionConflict
from runveil_core.runs import Run, RunStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runveil_persistence.history import HistoryRepository
from runveil_persistence.jobs import database_now
from runveil_persistence.models import ApprovalRow, EventRow, JobRow, RunRow
from runveil_persistence.repositories import AgentRepository, RunRepository


def snapshot(row: ApprovalRow) -> ApprovalRequest:
    proposal = PatchProposal.model_validate(row.proposal)
    if proposal.digest != row.digest:
        raise ValueError("Approval proposal integrity mismatch")
    if row.status not in ("PENDING", "APPROVED", "REJECTED"):
        raise ValueError("Unknown approval status")
    return ApprovalRequest(
        id=row.id,
        run_id=row.run_id,
        proposal=proposal,
        digest=row.digest,
        status=cast(Literal["PENDING", "APPROVED", "REJECTED"], row.status),
        requested_at=row.requested_at,
        decided_at=row.decided_at,
    )


class ApprovalRepository:
    """Trusted local operator API. Caller commits or rolls back the entire operation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, run_id: UUID) -> ApprovalRequest:
        row = await self.session.scalar(
            select(ApprovalRow)
            .where(ApprovalRow.run_id == run_id)
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise NotFound("Approval request not found")
        return snapshot(row)

    async def _lock_review(self, run_id: UUID) -> Run:
        row = await self.session.scalar(
            select(RunRow)
            .where(RunRow.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise NotFound("Run not found")
        version = await AgentRepository(self.session).get_version(row.agent_version_id)
        if (
            version.configuration != REVIEW_CONFIGURATION
            or (await self.session.get(JobRow, run_id)) is not None
        ):
            raise ValueError("Approval requires a dedicated, unenrolled patch-review run")
        return await RunRepository(self.session).get(run_id)

    async def _event(self, run: Run, approval: ApprovalRow, kind: str) -> int:
        event = EventRow(
            run_id=run.id,
            run_revision=run.revision,
            kind=kind,
            payload={"approval_id": str(approval.id), "digest": approval.digest},
        )
        self.session.add(event)
        await self.session.flush()
        return event.sequence

    async def request(self, run_id: UUID, proposal: PatchProposal) -> ApprovalRequest:
        # Revalidate even model_construct/model_copy input before making any writes.
        proposal = PatchProposal.model_validate_json(proposal.model_dump_json(), strict=True)
        run = await self._lock_review(run_id)
        if run.status != RunStatus.QUEUED or run.revision != 0:
            raise InvalidTransition("Review request requires a fresh queued run")
        runs = RunRepository(self.session)
        run = await runs.transition(
            run_id,
            RunStatus.RUNNING,
            expected_revision=0,
            expected_sequence=1,
        )
        row = ApprovalRow(
            id=uuid4(),
            run_id=run_id,
            proposal=proposal.model_dump(mode="json"),
            digest=proposal.digest,
        )
        self.session.add(row)
        await self.session.flush()
        sequence = await self._event(run, row, "approval.requested")
        checkpoint = await HistoryRepository(self.session).record_step(
            run_id,
            kind="approval.requested",
            details={"approval_id": str(row.id)},
            state={
                "workflow": "patch-review-v1",
                "approval_id": str(row.id),
                "digest": row.digest,
                "result": "pending",
                "patch_applied": False,
            },
            expected_revision=run.revision,
            expected_sequence=sequence,
        )
        await runs.transition(
            run_id,
            RunStatus.WAITING_FOR_APPROVAL,
            expected_revision=run.revision,
            expected_sequence=checkpoint.event_sequence,
        )
        return snapshot(row)

    async def resolve(
        self,
        run_id: UUID,
        *,
        decision: Literal["APPROVED", "REJECTED"],
        expected_revision: int,
        expected_digest: str,
    ) -> ApprovalRequest:
        if decision not in ("APPROVED", "REJECTED"):
            raise ValueError("Unknown approval decision")
        run = await self._lock_review(run_id)
        if run.revision != expected_revision:
            raise RevisionConflict("Run changed; inspect before deciding")
        if run.status != RunStatus.WAITING_FOR_APPROVAL:
            raise InvalidTransition("Run is not waiting for approval")
        row = await self.session.scalar(
            select(ApprovalRow)
            .where(ApprovalRow.run_id == run_id)
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise NotFound("Approval request not found")
        request = snapshot(row)
        if request.status != "PENDING" or request.digest != expected_digest:
            raise RevisionConflict("Approval changed; inspect before deciding")
        history = HistoryRepository(self.session)
        checkpoint = await history.latest_checkpoint(run_id)
        if checkpoint is None or checkpoint.state != {
            "workflow": "patch-review-v1",
            "approval_id": str(row.id),
            "digest": row.digest,
            "result": "pending",
            "patch_applied": False,
        }:
            raise ValueError("Invalid approval checkpoint")
        tail = await history.events(run_id, after_sequence=checkpoint.event_sequence, limit=2)
        if (
            len(tail) != 1
            or tail[0].kind != "run.transitioned"
            or tail[0].run_revision != run.revision
            or checkpoint.run_revision + 1 != run.revision
        ):
            raise RevisionConflict("Approval history changed")
        row.status = decision
        row.decided_at = await database_now(self.session)
        sequence = await self._event(run, row, "approval." + decision.lower())
        runs = RunRepository(self.session)
        if decision == "REJECTED":
            await runs.transition(
                run_id,
                RunStatus.FAILED,
                expected_revision=run.revision,
                expected_sequence=sequence,
            )
        else:
            run = await runs.transition(
                run_id,
                RunStatus.RUNNING,
                expected_revision=run.revision,
                expected_sequence=sequence,
            )
            checkpoint = await history.record_step(
                run_id,
                kind="approval.review_completed",
                details={"approval_id": str(row.id)},
                state={
                    "workflow": "patch-review-v1",
                    "approval_id": str(row.id),
                    "digest": row.digest,
                    "result": "approved",
                    "patch_applied": False,
                },
                expected_revision=run.revision,
                expected_sequence=sequence + 1,
            )
            await runs.transition(
                run_id,
                RunStatus.SUCCEEDED,
                expected_revision=run.revision,
                expected_sequence=checkpoint.event_sequence,
            )
        return snapshot(row)

"""Approval boundaries for the pinned review worker; no mutation authorization."""

import json
from typing import Literal
from uuid import UUID

from runveil_core.agents import JsonValue
from runveil_core.approvals import PROPOSAL_TOOL, REVIEW_PROFILE, ApprovalRequest, PatchProposal
from runveil_core.errors import InvalidTransition, NotFound, RevisionConflict
from runveil_core.models import Message, ModelRequest, ModelResponse, ToolAction, validate_response
from runveil_core.mutations import PATCH_PROFILE
from runveil_core.runs import RunStatus
from runveil_core.runtime import Pending, RuntimeConfig, RuntimeState
from runveil_core.sandbox_review import (
    INSPECT_TOOL,
    SANDBOX_REVIEW_PROFILE,
    InspectionResult,
    validate_proposal,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runveil_persistence.approvals import snapshot
from runveil_persistence.history import HistoryRepository
from runveil_persistence.jobs import OwnershipLost, database_now
from runveil_persistence.models import (
    ApprovalRow,
    EventRow,
    JobRow,
    ModelInvocationRow,
    RunRow,
    ToolCallRow,
)
from runveil_persistence.repositories import AgentRepository, RunRepository


def review_profile(config: RuntimeConfig) -> str:
    return {10: REVIEW_PROFILE, 11: PATCH_PROFILE, 13: SANDBOX_REVIEW_PROFILE}[
        config.schema_version
    ]


async def sandbox_preimage(
    session: AsyncSession, call: ToolCallRow, proposal: PatchProposal
) -> InspectionResult:
    inspections = list(
        await session.scalars(
            select(ToolCallRow)
            .where(ToolCallRow.run_id == call.run_id, ToolCallRow.tool_name == INSPECT_TOOL)
            .limit(2)
        )
    )
    source = await session.get(ModelInvocationRow, call.model_invocation_id)
    if (
        len(inspections) != 1
        or source is None
        or source.run_id != call.run_id
        or source.status != "SUCCEEDED"
    ):
        raise ValueError("Proposal requires one recorded sandbox inspection")
    inspected = inspections[0]
    if (
        inspected.status != "SUCCEEDED"
        or inspected.request != {}
        or inspected.result is None
        or inspected.completed_event_sequence is None
        or inspected.completed_event_sequence >= source.requested_event_sequence
    ):
        raise ValueError("Inspection must complete before the proposal model request")
    snapshot = InspectionResult.model_validate_json(json.dumps(inspected.result))
    request = ModelRequest.model_validate_json(json.dumps(source.request))
    observations = [m for m in request.messages if m.role == "tool" and m.tool_name == INSPECT_TOOL]
    if (
        len(observations) != 1
        or InspectionResult.model_validate_json(observations[0].content) != snapshot
    ):
        raise ValueError("Proposal model context differs from recorded inspection")
    validate_proposal(proposal, snapshot)
    return snapshot


async def validate_review_state(
    session: AsyncSession,
    run_id: UUID,
    state: RuntimeState,
    config: RuntimeConfig,
) -> ApprovalRow:
    row = await session.get(ApprovalRow, state.approval_id, populate_existing=True)
    job = await session.get(JobRow, run_id)
    if (
        config.schema_version not in (10, 11, 13)
        or job is None
        or job.profile != review_profile(config)
        or row is None
        or row.run_id != run_id
    ):
        raise ValueError("Invalid worker approval binding")
    request = snapshot(row)
    expected = "APPROVED" if state.approval_resolved else "PENDING"
    if request.status != expected:
        raise ValueError("Approval outcome differs from checkpoint")
    calls = list(
        await session.scalars(
            select(ToolCallRow)
            .where(
                ToolCallRow.run_id == run_id,
                ToolCallRow.tool_name == PROPOSAL_TOOL,
            )
            .limit(2)
        )
    )
    if len(calls) != 1:
        raise ValueError("Approval requires one proposal invocation")
    call = calls[0]
    if (
        call.status != "SUCCEEDED"
        or call.result != request.proposal.model_dump(mode="json")
        or PatchProposal.model_validate(call.request) != request.proposal
        or call.model_invocation_id is None
    ):
        raise ValueError("Approval differs from validated proposal")
    source = await session.get(ModelInvocationRow, call.model_invocation_id)
    if (
        source is None
        or source.run_id != run_id
        or source.status != "SUCCEEDED"
        or source.result is None
    ):
        raise ValueError("Invalid approval model provenance")
    action = validate_response(
        ModelRequest.model_validate_json(json.dumps(source.request)),
        ModelResponse.model_validate_json(json.dumps(source.result)),
    )
    if (
        not isinstance(action, ToolAction)
        or action.tool_name != PROPOSAL_TOOL
        or action.arguments != call.request
    ):
        raise ValueError("Approval differs from model action")
    if config.schema_version == 13:
        await sandbox_preimage(session, call, request.proposal)
    return row


async def prepare_pause(
    session: AsyncSession,
    pending: Pending,
    previous: RuntimeState | None,
    state: RuntimeState,
    config: RuntimeConfig,
    result: dict[str, JsonValue] | None,
) -> ApprovalRow | None:
    if previous is None:
        raise ValueError("Approval boundary requires prior state")
    call = await session.get(ToolCallRow, pending.id) if pending.kind == "tool" else None
    reviewing = (
        config.schema_version in (10, 11, 13)
        and call is not None
        and call.tool_name == PROPOSAL_TOOL
        and result is not None
    )
    if not reviewing:
        if (state.approval_id, state.approval_resolved) != (
            previous.approval_id,
            previous.approval_resolved,
        ):
            raise ValueError("Unexpected approval state change")
        return None
    job = await session.get(JobRow, pending.cursor.run_id)
    if (
        job is None
        or job.profile != review_profile(config)
        or previous.approval_id is not None
        or state.approval_id is None
        or state.approval_resolved
        or state.error_code is not None
        or state.final_result is not None
        or state.next_tool is not None
        or state.source_model_id is not None
        or call is None
        or call.model_invocation_id is None
        or previous.next_tool is None
        or previous.next_tool.tool_name != PROPOSAL_TOOL
        or previous.next_tool.arguments != call.request
        or previous.source_model_id != call.model_invocation_id
        or state.steps_used != previous.steps_used + 1
    ):
        raise ValueError("Invalid approval pause")
    proposal = PatchProposal.model_validate(result)
    if proposal != PatchProposal.model_validate(call.request):
        raise ValueError("Proposal output differs from request")
    if config.schema_version == 13:
        await sandbox_preimage(session, call, proposal)
    row = ApprovalRow(
        id=state.approval_id,
        run_id=pending.cursor.run_id,
        proposal=proposal.model_dump(mode="json"),
        digest=proposal.digest,
    )
    session.add(row)
    await session.flush()
    return row


async def pause_review(session: AsyncSession, row: ApprovalRow, revision: int) -> None:
    event = EventRow(
        run_id=row.run_id,
        kind="approval.requested",
        run_revision=revision,
        payload={"approval_id": str(row.id), "digest": row.digest},
    )
    session.add(event)
    await session.flush()
    await RunRepository(session).transition(
        row.run_id,
        RunStatus.WAITING_FOR_APPROVAL,
        expected_revision=revision,
        expected_sequence=event.sequence,
    )
    job = await session.get(JobRow, row.run_id)
    assert job is not None
    job.token = None
    job.expires_at = None
    await session.flush()


async def resolve_worker_review(
    session: AsyncSession,
    run_id: UUID,
    *,
    decision: Literal["APPROVED", "REJECTED"],
    expected_revision: int,
    expected_digest: str,
    profile: str = REVIEW_PROFILE,
) -> ApprovalRequest:
    if decision not in ("APPROVED", "REJECTED"):
        raise ValueError("Unknown decision")
    run_row = await session.scalar(
        select(RunRow)
        .where(RunRow.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run_row is None:
        raise NotFound("Run not found")
    run = await RunRepository(session).get(run_id)
    if run.revision != expected_revision:
        raise RevisionConflict("Run changed; inspect before deciding")
    if run.status != RunStatus.WAITING_FOR_APPROVAL:
        raise InvalidTransition("Run is not waiting for approval")
    job = await session.get(JobRow, run_id, with_for_update=True, populate_existing=True)
    if (
        profile not in (REVIEW_PROFILE, PATCH_PROFILE, SANDBOX_REVIEW_PROFILE)
        or job is None
        or job.profile != profile
    ):
        raise ValueError("Not a worker review")
    if job.token is not None or job.expires_at is not None:
        raise OwnershipLost("Waiting approval must have released its worker")
    version = await AgentRepository(session).get_version(run.agent_version_id)
    config = RuntimeConfig.model_validate_json(version.configuration_json)
    history = HistoryRepository(session)
    checkpoint = await history.latest_checkpoint(run_id)
    if checkpoint is None or checkpoint.run_revision + 1 != run.revision:
        raise ValueError("Invalid approval checkpoint revision")
    state = RuntimeState.model_validate_json(json.dumps(checkpoint.state))
    if (
        state.approval_id is None
        or state.approval_resolved
        or state.next_tool is not None
        or state.error_code is not None
        or state.final_result is not None
    ):
        raise ValueError("Invalid pending approval checkpoint")
    row = await validate_review_state(session, run_id, state, config)
    if row.digest != expected_digest:
        raise RevisionConflict("Proposal changed; inspect before deciding")
    tail = await history.events(run_id, after_sequence=checkpoint.event_sequence, limit=3)
    if (
        len(tail) != 2
        or tail[0].kind != "approval.requested"
        or tail[0].run_revision != checkpoint.run_revision
        or tail[0].payload != {"approval_id": str(row.id), "digest": row.digest}
        or tail[1].kind != "run.transitioned"
        or tail[1].run_revision != run.revision
        or tail[1].payload.get("status") != "WAITING_FOR_APPROVAL"
        or tail[1].payload.get("from_status") != "RUNNING"
    ):
        raise RevisionConflict("Approval history changed")
    row.status = decision
    row.decided_at = await database_now(session)
    event = EventRow(
        run_id=run_id,
        run_revision=run.revision,
        kind="approval." + decision.lower(),
        payload={"approval_id": str(row.id), "digest": row.digest},
    )
    session.add(event)
    await session.flush()
    run = await RunRepository(session).transition(
        run_id,
        RunStatus.RUNNING if decision == "APPROVED" else RunStatus.FAILED,
        expected_revision=run.revision,
        expected_sequence=event.sequence,
    )
    if decision == "APPROVED":
        state = state.model_copy(
            update={
                "approval_resolved": True,
                "messages": (
                    *state.messages,
                    Message(
                        role="tool",
                        tool_name=PROPOSAL_TOOL,
                        content=json.dumps(
                            {"approval": "APPROVED", "digest": row.digest, "patch_applied": False}
                        ),
                    ),
                ),
            }
        )
        await history.record_step(
            run_id,
            kind="runtime.approval_resolved",
            details={"approval_id": str(row.id)},
            state=state.model_dump(mode="json"),
            expected_revision=run.revision,
            expected_sequence=event.sequence + 1,
        )
    return snapshot(row)

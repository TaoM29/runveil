"""Content-minimized trace projections; callers supply a read-only consistent snapshot."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field
from runveil_core.errors import NotFound, RevisionConflict
from runveil_core.invocations import InvocationStatus
from runveil_core.models import Contract
from runveil_core.runs import RunStatus
from runveil_core.runtime import CostAccounting, TokenAccounting
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from runveil_persistence.models import (
    ApprovalRow,
    CheckpointRow,
    EventRow,
    ModelInvocationRow,
    RunRow,
    ToolCallRow,
)


class TraceInvocation(Contract):
    id: UUID
    kind: Literal["model", "tool"]
    name: str
    provider: str | None = None
    model_invocation_id: UUID | None = None
    status: InvocationStatus
    requested_sequence: int
    completed_sequence: int | None
    requested_at: datetime
    completed_at: datetime | None
    duration_ms: float | None
    error_code: str | None


class TraceEvent(Contract):
    sequence: int
    kind: str
    run_revision: int
    step_number: int | None
    created_at: datetime
    retry_of: UUID | None
    to_status: RunStatus | None
    invocation: TraceInvocation | None = None


class TraceApproval(Contract):
    id: UUID
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    requested_at: datetime
    decided_at: datetime | None


class TraceCheckpoint(Contract):
    event_sequence: int
    schema_version: int | None
    tokens: TokenAccounting | None = None
    cost: CostAccounting | None = None
    retries_scheduled: int | None = None
    error_code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    final_summary: str | None = None
    final_summary_truncated: bool = False


class RunTrace(Contract):
    schema_version: Literal[1] = 1
    run_id: UUID
    agent_version_id: UUID
    status: RunStatus
    revision: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    observed_at: datetime
    elapsed_ms: float | None
    event_sequence: int
    history_complete: bool
    model_calls: int
    tool_calls: int
    checkpoint: TraceCheckpoint | None
    approval: TraceApproval | None
    events: list[TraceEvent]
    next_after_sequence: int | None


def duration(start: datetime | None, end: datetime | None) -> float | None:
    return None if start is None or end is None else max(0.0, (end - start).total_seconds() * 1000)


async def read_trace(
    session: AsyncSession,
    run_id: UUID,
    *,
    after_sequence: int = 0,
    limit: int = 50,
    expected_sequence: int | None = None,
) -> RunTrace:
    if not 0 <= after_sequence <= 2**31 - 1 or not 1 <= limit <= 100:
        raise ValueError("Invalid pagination")
    if after_sequence and expected_sequence is None:
        raise ValueError("Continuation requires a watermark")
    run = await session.get(RunRow, run_id)
    if run is None:
        raise NotFound("Run not found")
    watermark = (
        await session.scalar(select(func.max(EventRow.sequence)).where(EventRow.run_id == run_id))
        or 0
    )
    if expected_sequence is not None and expected_sequence != watermark:
        raise RevisionConflict("Trace changed")
    if after_sequence > watermark:
        raise ValueError("Invalid cursor")
    observed_at = await session.scalar(select(func.clock_timestamp()))
    assert isinstance(observed_at, datetime)
    events = [
        TraceEvent.model_validate(
            dict(row)
            | {
                "retry_of": UUID(row["retry_of"]) if row["retry_of"] else None,
                "to_status": RunStatus(row["to_status"]) if row["to_status"] else None,
            }
        )
        for row in (
            await session.execute(
                select(
                    EventRow.sequence,
                    EventRow.kind,
                    EventRow.run_revision,
                    EventRow.step_number,
                    EventRow.created_at,
                    EventRow.payload["retry_of"].as_string().label("retry_of"),
                    EventRow.payload["status"].as_string().label("to_status"),
                )
                .where(EventRow.run_id == run_id, EventRow.sequence > after_sequence)
                .order_by(EventRow.sequence)
                .limit(limit)
            )
        ).mappings()
    ]
    positions = [event.sequence for event in events]
    invocations: dict[int, TraceInvocation] = {}
    counts: list[int] = []
    for table in (ModelInvocationRow, ToolCallRow):
        counts.append(
            await session.scalar(
                select(func.count()).select_from(table).where(table.run_id == run_id)
            )
            or 0
        )
        # Never fetch request/result JSON, even for administrator-created history.
        columns = [
            table.id,
            table.status,
            table.requested_event_sequence,
            table.completed_event_sequence,
            table.requested_at,
            table.completed_at,
            table.error_code,
        ]
        if table is ModelInvocationRow:
            columns.extend([ModelInvocationRow.model, ModelInvocationRow.provider])
        else:
            columns.extend([ToolCallRow.tool_name, ToolCallRow.model_invocation_id])
        rows = await session.scalars(
            select(table)
            .options(load_only(*columns, raiseload=True))
            .where(
                table.run_id == run_id,
                or_(
                    table.requested_event_sequence.in_(positions),
                    table.completed_event_sequence.in_(positions),
                ),
            )
        )
        for call in rows:
            assert isinstance(call, (ModelInvocationRow, ToolCallRow))
            model = isinstance(call, ModelInvocationRow)
            view = TraceInvocation(
                id=call.id,
                kind="model" if model else "tool",
                name=call.model if isinstance(call, ModelInvocationRow) else call.tool_name,
                provider=call.provider if isinstance(call, ModelInvocationRow) else None,
                model_invocation_id=call.model_invocation_id
                if isinstance(call, ToolCallRow)
                else None,
                status=InvocationStatus(call.status),
                requested_sequence=call.requested_event_sequence,
                completed_sequence=call.completed_event_sequence,
                requested_at=call.requested_at,
                completed_at=call.completed_at,
                duration_ms=duration(call.requested_at, call.completed_at),
                error_code=call.error_code,
            )
            invocations[call.requested_event_sequence] = view
            if call.completed_event_sequence is not None:
                invocations[call.completed_event_sequence] = view
    events = [
        event.model_copy(update={"invocation": invocations.get(event.sequence)}) for event in events
    ]
    state = CheckpointRow.state
    checkpoint_row = (
        (
            await session.execute(
                select(
                    CheckpointRow.event_sequence,
                    state["schema_version"].label("schema_version"),
                    state["tokens"].label("tokens"),
                    state["cost"].label("cost"),
                    state["retries_scheduled"].label("retries_scheduled"),
                    state["error_code"].as_string().label("error_code"),
                    func.left(state["final_result"]["summary"].as_string(), 4097).label("summary"),
                )
                .where(CheckpointRow.run_id == run_id)
                .order_by(CheckpointRow.event_sequence.desc())
                .limit(1)
            )
        )
        .mappings()
        .one_or_none()
    )
    checkpoint = None
    if checkpoint_row is not None:
        version = checkpoint_row["schema_version"]
        supported = type(version) is int and 1 <= version <= 11
        summary = checkpoint_row["summary"] if supported else None
        checkpoint = TraceCheckpoint(
            event_sequence=checkpoint_row["event_sequence"],
            schema_version=version if supported else None,
            tokens=TokenAccounting.model_validate(checkpoint_row["tokens"])
            if supported and version >= 5
            else None,
            cost=CostAccounting.model_validate(checkpoint_row["cost"])
            if supported and version >= 6
            else None,
            retries_scheduled=checkpoint_row["retries_scheduled"]
            if supported and version >= 3
            else None,
            error_code=checkpoint_row["error_code"] if supported else None,
            final_summary=summary[:4096] if summary is not None else None,
            final_summary_truncated=summary is not None and len(summary) > 4096,
        )
    approval_row = (
        (
            await session.execute(
                select(
                    ApprovalRow.id,
                    ApprovalRow.status,
                    ApprovalRow.requested_at,
                    ApprovalRow.decided_at,
                ).where(ApprovalRow.run_id == run_id)
            )
        )
        .mappings()
        .one_or_none()
    )
    baseline = await session.scalar(
        select(EventRow.kind).where(EventRow.run_id == run_id).order_by(EventRow.sequence).limit(1)
    )
    return RunTrace(
        run_id=run.id,
        agent_version_id=run.agent_version_id,
        status=RunStatus(run.status),
        revision=run.revision,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        observed_at=observed_at,
        elapsed_ms=duration(run.started_at, run.finished_at or observed_at),
        event_sequence=watermark,
        history_complete=baseline == "run.created",
        model_calls=counts[0],
        tool_calls=counts[1],
        checkpoint=checkpoint,
        approval=TraceApproval.model_validate(dict(approval_row)) if approval_row else None,
        events=events,
        next_after_sequence=events[-1].sequence
        if events and events[-1].sequence < watermark
        else None,
    )

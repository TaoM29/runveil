"""Real mutation evidence: approval, one intent, fencing and no replay after I/O."""

import asyncio
from pathlib import Path
from typing import Literal
from uuid import UUID

import pytest
from runveil_core.agents import JsonValue
from runveil_core.approvals import PatchProposal
from runveil_core.errors import RevisionConflict
from runveil_core.mutations import APPLY_TOOL, PATCH_PROFILE
from runveil_core.runs import RunStatus
from runveil_core.runtime import Cursor, Pending, RuntimeConfig
from runveil_core.tools import ToolError
from runveil_persistence.approvals import ApprovalRepository
from runveil_persistence.execution import PostgresExecutionStore
from runveil_persistence.history import HistoryRepository
from runveil_persistence.invocations import InvocationRepository
from runveil_persistence.jobs import OwnershipLost
from runveil_persistence.models import ToolCallRow
from runveil_persistence.repositories import RunRepository
from runveil_persistence.worker_approvals import resolve_worker_review
from runveil_tools.patch import SingleFileWriter
from runveil_tools.repository import RepositoryAccess
from runveil_worker.patch_worker import submit_patch, work_patch_once
from runveil_worker.review_worker import submit_review
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_worker import expire

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def approved(sessions: async_sessionmaker[AsyncSession], root: Path) -> UUID:
    run_id = await submit_patch(sessions, root, "a.txt")
    state = await work_patch_once(sessions, root, "a.txt", run_id=run_id)
    assert state is not None and state.approval_id is not None
    async with sessions.begin() as session:
        request = await ApprovalRepository(session).get(run_id)
        with pytest.raises(ValueError):
            await resolve_worker_review(
                session,
                run_id,
                decision="APPROVED",
                expected_revision=2,
                expected_digest=request.digest,
            )
        await resolve_worker_review(
            session,
            run_id,
            decision="APPROVED",
            expected_revision=2,
            expected_digest=request.digest,
            profile=PATCH_PROFILE,
        )
    return run_id


async def test_apply_once_requires_operator_grant_and_new_profile(
    database: AsyncEngine, tmp_path: Path
) -> None:
    target = tmp_path / "a.txt"
    target.write_text("public fixture")
    sessions = async_sessionmaker(database)
    run_id = await approved(sessions, tmp_path)
    assert target.read_text() == "public fixture"
    with pytest.raises(ToolError):
        await work_patch_once(sessions, tmp_path, "a.txt", run_id=run_id)
    async with sessions.begin() as session:
        assert (
            await session.scalar(select(ToolCallRow.id).where(ToolCallRow.tool_name == APPLY_TOOL))
            is None
        )
    await expire(sessions, run_id)
    result = await work_patch_once(sessions, tmp_path, "a.txt", run_id=run_id, allow_write=True)
    assert result is not None and result.final_result is not None and result.steps_used == 5
    assert target.read_text() == "public fixture\nReviewed by Runveil.\n"
    # Terminal duplicates do not recapture an intentionally changed/missing workspace.
    assert (
        await work_patch_once(
            sessions, tmp_path / "missing", "a.txt", run_id=run_id, allow_write=True
        )
        is None
    )
    review = await submit_review(sessions, tmp_path, RepositoryAccess(files=("a.txt",)))
    assert (
        await work_patch_once(sessions, tmp_path, "a.txt", run_id=review, allow_write=True) is None
    )


@pytest.mark.parametrize("cut", ["intent", "after_replace"])
async def test_uncertain_intent_never_replays_even_after_workspace_changes(
    database: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cut: str
) -> None:
    target = tmp_path / "a.txt"
    target.write_text("public fixture")
    sessions = async_sessionmaker(database)
    run_id = await approved(sessions, tmp_path)
    real_request = PostgresExecutionStore.request
    real_apply = SingleFileWriter.apply

    async def interrupted_request(
        self: PostgresExecutionStore,
        cursor: Cursor,
        *,
        kind: Literal["model", "tool"],
        payload: dict[str, JsonValue],
        config: RuntimeConfig,
        model_invocation_id: UUID | None = None,
        tool_name: str | None = None,
    ) -> Pending:
        pending = await real_request(
            self,
            cursor,
            kind=kind,
            payload=payload,
            config=config,
            model_invocation_id=model_invocation_id,
            tool_name=tool_name,
        )
        if tool_name == APPLY_TOOL:
            raise asyncio.CancelledError
        return pending

    def interrupted_write(self: SingleFileWriter, proposal: PatchProposal) -> None:
        real_apply(self, proposal)
        raise asyncio.CancelledError

    with monkeypatch.context() as fault:
        if cut == "intent":
            fault.setattr(PostgresExecutionStore, "request", interrupted_request)
        else:
            fault.setattr(SingleFileWriter, "apply", interrupted_write)
        with pytest.raises(asyncio.CancelledError):
            await work_patch_once(sessions, tmp_path, "a.txt", run_id=run_id, allow_write=True)
    observed = target.read_text()
    assert observed == (
        "public fixture" if cut == "intent" else "public fixture\nReviewed by Runveil.\n"
    )
    async with sessions.begin() as session:
        call = await session.scalar(select(ToolCallRow).where(ToolCallRow.tool_name == APPLY_TOOL))
        assert call is not None and call.status == "REQUESTED"
        run = await RunRepository(session).get(run_id)
        events = await HistoryRepository(session).events(run_id)
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                from uuid import uuid4

                await InvocationRepository(session).request_tool(
                    run_id,
                    tool_call_id=uuid4(),
                    tool_name=APPLY_TOOL,
                    arguments=call.request,
                    expected_revision=run.revision,
                    expected_sequence=events[-1].sequence,
                )
    assert (
        await work_patch_once(sessions, tmp_path, "a.txt", run_id=run_id, allow_write=True) is None
    )
    await expire(sessions, run_id)
    # Recovery requires neither the old snapshot nor a writer grant.
    result = await work_patch_once(sessions, tmp_path / "unavailable", "a.txt", run_id=run_id)
    assert result is not None and result.error_code == "patch_outcome_unknown"
    assert target.read_text() == observed
    async with sessions.begin() as session:
        calls = list(
            await session.scalars(select(ToolCallRow).where(ToolCallRow.tool_name == APPLY_TOOL))
        )
        assert len(calls) == 1 and calls[0].status == "FAILED"
        assert (await RunRepository(session).get(run_id)).status == RunStatus.FAILED


@pytest.mark.parametrize("gate", ["cancel", "lease"])
async def test_final_write_fence_rejects_cancelled_or_stale_owner(
    database: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gate: str
) -> None:
    target = tmp_path / "a.txt"
    target.write_text("public fixture")
    sessions = async_sessionmaker(database)
    run_id = await approved(sessions, tmp_path)
    real_request = PostgresExecutionStore.request

    async def invalidate(
        self: PostgresExecutionStore,
        cursor: Cursor,
        *,
        kind: Literal["model", "tool"],
        payload: dict[str, JsonValue],
        config: RuntimeConfig,
        model_invocation_id: UUID | None = None,
        tool_name: str | None = None,
    ) -> Pending:
        pending = await real_request(
            self,
            cursor,
            kind=kind,
            payload=payload,
            config=config,
            model_invocation_id=model_invocation_id,
            tool_name=tool_name,
        )
        if gate == "cancel":
            async with sessions.begin() as session:
                await RunRepository(session).transition(
                    run_id, RunStatus.CANCELLED, expected_revision=cursor.revision
                )
        else:
            await expire(sessions, run_id)
        return pending

    monkeypatch.setattr(PostgresExecutionStore, "request", invalidate)
    with pytest.raises((RevisionConflict, OwnershipLost)):
        await work_patch_once(sessions, tmp_path, "a.txt", run_id=run_id, allow_write=True)
    assert target.read_text() == "public fixture"


async def test_rejection_and_workspace_drift_never_write(
    database: AsyncEngine, tmp_path: Path
) -> None:
    target = tmp_path / "a.txt"
    target.write_text("public fixture")
    sessions = async_sessionmaker(database)
    rejected = await submit_patch(sessions, tmp_path, "a.txt")
    await work_patch_once(sessions, tmp_path, "a.txt", run_id=rejected, allow_write=True)
    assert target.read_text() == "public fixture"
    async with sessions.begin() as session:
        request = await ApprovalRepository(session).get(rejected)
        await resolve_worker_review(
            session,
            rejected,
            decision="REJECTED",
            expected_revision=2,
            expected_digest=request.digest,
            profile=PATCH_PROFILE,
        )
    assert (
        await work_patch_once(sessions, tmp_path, "a.txt", run_id=rejected, allow_write=True)
        is None
    )
    run_id = await approved(sessions, tmp_path)
    target.write_text("external change")
    with pytest.raises(ValueError, match="worker profile"):
        await work_patch_once(sessions, tmp_path, "a.txt", run_id=run_id, allow_write=True)
    assert target.read_text() == "external change"
    async with sessions.begin() as session:
        assert (
            await session.scalar(select(ToolCallRow.id).where(ToolCallRow.tool_name == APPLY_TOOL))
            is None
        )
